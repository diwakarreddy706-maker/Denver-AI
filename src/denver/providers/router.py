"""Local-First AI Provider Router with Intelligent Fallback and Task Complexity Routing."""

from __future__ import annotations

import time
from enum import Enum
from typing import Any

from denver.logging.logger import get_logger
from denver.providers.base import AIProvider
from denver.providers.models import (
    ProviderHealth,
    ProviderRequest,
    ProviderResponse,
    ProviderStatus,
    ProviderType,
)
from denver.providers.registry import ProviderRegistry
from denver.runtime.event_bus import DenverEventBus, get_event_bus
from denver.providers.privacy import sanitize_messages_for_cloud
from denver.runtime.events import (
    AirGappedModeChanged,
    ProviderFailed,
    ProviderFallback,
    ProviderModeChanged,
    ProviderRequestStarted,
    ProviderResponseReceived,
    ProviderUnavailable,
)

logger = get_logger("providers.router")


class TaskComplexity(str, Enum):
    """Complexity classification for AI tasks."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def classify_complexity(
    prompt: str,
    has_tools: bool = False,
    has_memories: bool = False,
) -> TaskComplexity:
    """Classify prompt into LOW, MEDIUM, or HIGH complexity."""
    if not prompt:
        return TaskComplexity.LOW

    clean = prompt.strip().lower()
    length = len(clean)

    high_signals = [
        "explain in detail",
        "step by step",
        "architecture",
        "debug",
        "refactor",
        "compare",
        "synthesize",
        "analyze",
        "write a script",
        "implement",
    ]

    if length > 300 or any(s in clean for s in high_signals):
        return TaskComplexity.HIGH

    if length > 60 or has_memories or has_tools:
        return TaskComplexity.MEDIUM

    return TaskComplexity.LOW


class ProviderRouter:
    """Orchestrates local-first inference routing, complexity classification, and graceful fallback."""

    def __init__(
        self,
        registry: ProviderRegistry,
        event_bus: DenverEventBus | None = None,
        priority_order: tuple[str, ...] = ("ollama", "lmstudio", "groq", "gemini"),
        local_first: bool = True,
        cloud_fallback_enabled: bool = False,
        air_gapped_mode: bool = False,
        active_provider: str | None = None,
    ) -> None:
        self.registry = registry
        self.event_bus = event_bus or get_event_bus()
        self.priority_order = tuple(priority_order)
        self.local_first = local_first
        self.cloud_fallback_enabled = cloud_fallback_enabled
        self.air_gapped_mode = air_gapped_mode
        self.active_provider = active_provider
        if active_provider:
            self.set_active_provider(active_provider)

    def set_air_gapped_mode(self, enabled: bool) -> None:
        """Toggle air-gapped / local-only mode. When True, all cloud providers are strictly blocked."""
        self.air_gapped_mode = enabled
        logger.info("Air-Gapped Mode set to: %s", enabled)

    def set_active_provider(self, provider_name: str) -> bool:
        """Set primary preferred LLM provider. Reorders priority queue so this provider is tried first."""
        clean_name = provider_name.strip().lower()
        provider = self.registry.get(clean_name)
        if not provider:
            logger.warning("Provider '%s' not registered in ProviderRegistry.", clean_name)
            return False

        self.active_provider = clean_name
        current_list = list(self.priority_order)
        if clean_name in current_list:
            current_list.remove(clean_name)
        self.priority_order = tuple([clean_name] + current_list)
        logger.info("Active LLM provider set to '%s'. Priority order: %s", clean_name, self.priority_order)
        return True

    def get_ordered_providers(self, complexity: TaskComplexity = TaskComplexity.LOW) -> list[AIProvider]:
        """Resolve ordered list of providers based on priority configuration, air-gapped constraints, and complexity."""
        ordered = []
        for name in self.priority_order:
            provider = self.registry.get(name)
            if provider and provider.enabled:
                if self.air_gapped_mode and provider.provider_type == ProviderType.CLOUD:
                    continue
                ordered.append(provider)

        # Append any other registered providers not listed in priority
        for provider in self.registry.list_providers():
            if provider.enabled and provider not in ordered:
                if self.air_gapped_mode and provider.provider_type == ProviderType.CLOUD:
                    continue
                ordered.append(provider)

        return ordered

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Execute request using local-first priority fallback and complexity classification."""
        # Extract prompt text for complexity classification
        prompt_text = ""
        if request.messages:
            prompt_text = " ".join(m.get("content", "") for m in request.messages if isinstance(m, dict))

        complexity = classify_complexity(
            prompt=prompt_text,
            has_tools=bool(request.tools),
            has_memories=bool(request.context_summary),
        )
        logger.debug("Task complexity classified as: %s", complexity.value)

        providers = self.get_ordered_providers(complexity=complexity)
        if not providers:
            err_msg = (
                "No AI provider is currently available (Air-Gapped mode active; cloud providers blocked)."
                if self.air_gapped_mode
                else "No AI provider is currently available."
            )
            return ProviderResponse(
                text="",
                success=False,
                error=err_msg,
            )

        last_error: Exception | None = None
        attempted_providers = []

        for i, provider in enumerate(providers):
            # If cloud provider and cloud fallback is disabled
            if provider.provider_type == ProviderType.CLOUD:
                if self.air_gapped_mode:
                    logger.debug("Skipping cloud provider '%s': air-gapped mode is active.", provider.name)
                    continue
                if not self.cloud_fallback_enabled and self.active_provider != provider.name:
                    logger.debug("Skipping cloud provider '%s': cloud fallback is disabled.", provider.name)
                    continue

            attempted_providers.append(provider.name)
            is_cloud = (provider.provider_type == ProviderType.CLOUD)

            await self.event_bus.publish(
                ProviderRequestStarted(
                    provider_name=provider.name,
                    model_name=provider.default_model,
                    is_cloud=is_cloud,
                )
            )

            start = time.perf_counter()
            try:
                # Execute inference
                response = await provider.generate(request)
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

                await self.event_bus.publish(
                    ProviderResponseReceived(
                        provider_name=provider.name,
                        model_name=response.model_name,
                        latency_ms=elapsed_ms,
                        has_tool_calls=bool(response.tool_calls),
                    )
                )
                logger.info("AI completion succeeded via provider '%s' (%s) in %.2fms (complexity=%s)", provider.name, response.model_name, elapsed_ms, complexity.value)
                return response

            except Exception as exc:
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                last_error = exc
                logger.warning("Provider '%s' failed (%.2fms): %s", provider.name, elapsed_ms, exc)

                await self.event_bus.publish(
                    ProviderFailed(
                        provider_name=provider.name,
                        model_name=provider.default_model,
                        error=str(exc),
                    )
                )

                # If there is another provider in queue, publish fallback event
                if i + 1 < len(providers):
                    next_provider = providers[i + 1]
                    await self.event_bus.publish(
                        ProviderFallback(
                            from_provider=provider.name,
                            to_provider=next_provider.name,
                            reason=str(exc),
                        )
                    )

        return ProviderResponse(
            text="",
            success=False,
            error=f"All available AI providers failed ({', '.join(attempted_providers)}): {last_error}",
        )

    def get_health_status(self) -> dict[str, Any]:
        """Collect instantaneous health diagnostics across all configured providers."""
        providers_status: dict[str, str] = {}
        for p in self.registry.list_providers():
            if not p.enabled:
                providers_status[p.name] = "NOT_CONFIGURED"
            elif hasattr(p, "_get_api_key") and not p._get_api_key():
                providers_status[p.name] = "NOT_CONFIGURED"
            elif hasattr(p, "_last_status"):
                providers_status[p.name] = getattr(p, "_last_status").value
            elif hasattr(p, "_get_api_key") and p._get_api_key():
                providers_status[p.name] = "READY"
            elif p.provider_type == ProviderType.LOCAL and hasattr(p, "base_url") and p.base_url:
                try:
                    import urllib.request
                    url = f"{p.base_url.rstrip('/')}/api/tags" if p.name == "ollama" else f"{p.base_url.rstrip('/')}/models"
                    req = urllib.request.Request(url, headers={"User-Agent": "Denver/0.1.0"})
                    with urllib.request.urlopen(req, timeout=0.1):
                        providers_status[p.name] = "READY"
                except Exception:
                    providers_status[p.name] = "UNAVAILABLE"
            else:
                providers_status[p.name] = "UNAVAILABLE" if p.provider_type == ProviderType.LOCAL else "NOT_CONFIGURED"

        ready_count = sum(1 for s in providers_status.values() if s == "READY")
        if ready_count > 0:
            overall = "READY"
        elif any(s == "DEGRADED" for s in providers_status.values()):
            overall = "DEGRADED"
        elif any(s == "UNAVAILABLE" for s in providers_status.values()):
            overall = "UNAVAILABLE"
        else:
            overall = "NOT_CONFIGURED"

        return {
            "status": overall,
            "ready_providers": ready_count,
            "total_providers": len(providers_status),
            "providers": providers_status,
        }

    async def check_live_health(self) -> dict[str, Any]:
        """Collect live asynchronous health diagnostics across all configured providers."""
        health_map = await self.registry.check_health_all()
        ready_count = sum(1 for h in health_map.values() if h.status == ProviderStatus.READY)
        overall_status = "READY" if ready_count > 0 else "NOT_CONFIGURED"
        return {
            "status": overall_status,
            "ready_providers": ready_count,
            "total_providers": len(health_map),
            "providers": {k: v.to_dict() for k, v in health_map.items()},
        }
