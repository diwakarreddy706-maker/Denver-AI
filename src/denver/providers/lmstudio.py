"""LM Studio Local AI Provider for Denver AI Assistant."""

from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

from denver.logging.logger import get_logger
from denver.providers.base import AIProvider
from denver.providers.models import (
    ModelInfo,
    ProviderHealth,
    ProviderRequest,
    ProviderResponse,
    ProviderStatus,
    ProviderType,
    ToolCall,
)
from denver.providers.ollama import _TOOL_JSON_PATTERN, _http_request
from denver.providers.prompts import build_system_prompt

logger = get_logger("providers.lmstudio")


class LMStudioProvider(AIProvider):
    """Local OpenAI-compatible AI provider for LM Studio local server."""

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        default_model: str = "local-model",
        enabled: bool = True,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._enabled = enabled
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "lmstudio"

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.LOCAL

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def default_model(self) -> str:
        return self._default_model

    async def check_health(self) -> ProviderHealth:
        """Probe LM Studio /v1/models endpoint."""
        if not self._enabled:
            return ProviderHealth(
                provider_name=self.name,
                status=ProviderStatus.NOT_CONFIGURED,
                provider_type=self.provider_type,
                model_name=self.default_model,
                error="Provider disabled in configuration",
            )

        start = time.perf_counter()
        try:
            url = f"{self.base_url}/models"
            data = await asyncio.to_thread(_http_request, url, None, None, 1.5)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            return ProviderHealth(
                provider_name=self.name,
                status=ProviderStatus.READY,
                provider_type=self.provider_type,
                model_name=self.default_model,
                latency_ms=elapsed_ms,
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.debug("LM Studio is unavailable at '%s': %s", self.base_url, exc)
            return ProviderHealth(
                provider_name=self.name,
                status=ProviderStatus.UNAVAILABLE,
                provider_type=self.provider_type,
                model_name=self.default_model,
                latency_ms=elapsed_ms,
                error=f"Cannot connect to LM Studio: {exc}",
            )

    async def list_models(self) -> list[ModelInfo]:
        """List models loaded in LM Studio."""
        try:
            url = f"{self.base_url}/models"
            data = await asyncio.to_thread(_http_request, url, None, None, 3.0)
            models = []
            for item in data.get("data", []):
                model_id = item.get("id", "")
                models.append(ModelInfo(model_id=model_id, name=model_id))
            return models
        except Exception:
            return []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Send chat completion request to LM Studio OpenAI-compatible endpoint."""
        start = time.perf_counter()
        system_prompt = request.system_prompt or build_system_prompt(
            context_summary=request.context_summary,
            available_tools=None if request.tools else request.tools,
            is_cloud=False,
        )

        messages = [{"role": "system", "content": system_prompt}] + request.messages
        payload: dict[str, Any] = {
            "model": self.default_model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.tools:
            payload["tools"] = [t.to_schema() for t in request.tools]
            payload["tool_choice"] = "auto"

        url = f"{self.base_url}/chat/completions"
        try:
            res_data = await asyncio.to_thread(_http_request, url, payload, None, self.timeout_seconds)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

            choices = res_data.get("choices", [])
            content = ""
            tool_calls = []

            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content", "").strip()

                # Native tool_calls if returned
                if "tool_calls" in msg and msg["tool_calls"]:
                    for tc in msg["tool_calls"]:
                        fn = tc.get("function", {})
                        args = fn.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}
                        tool_calls.append(ToolCall(name=fn.get("name", ""), arguments=args))

            # Fallback tool extraction if native tool_calls not present
            if not tool_calls and content:
                # 1. Search markdown code fences
                for m in _TOOL_JSON_PATTERN.findall(content):
                    try:
                        d = json.loads(m)
                        if isinstance(d, dict):
                            act_name = d.get("action") or d.get("name")
                            act_args = d.get("params") or d.get("parameters") or d.get("arguments") or {}
                            if act_name:
                                tool_calls.append(ToolCall(name=act_name, arguments=act_args))
                    except json.JSONDecodeError:
                        pass

                # 2. Search direct JSON objects in text
                if not tool_calls:
                    for s in re.findall(r"(\{[^{}]*\"(?:name|action)\"[^{}]*\})", content):
                        try:
                            d = json.loads(s)
                            if isinstance(d, dict):
                                act_name = d.get("action") or d.get("name")
                                act_args = d.get("params") or d.get("parameters") or d.get("arguments") or {}
                                if act_name:
                                    tool_calls.append(ToolCall(name=act_name, arguments=act_args))
                        except json.JSONDecodeError:
                            pass

            usage = res_data.get("usage", {})
            return ProviderResponse(
                text=content,
                tool_calls=tool_calls,
                model_name=self.default_model,
                provider_name=self.name,
                latency_ms=elapsed_ms,
                token_usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                raw_response=res_data,
            )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error("LM Studio generate failed: %s", exc)
            raise RuntimeError(f"LM Studio generation failed: {exc}") from exc
