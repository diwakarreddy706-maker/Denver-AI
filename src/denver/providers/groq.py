"""Groq Cloud AI Provider for Denver AI Assistant."""

from __future__ import annotations

import asyncio
import json
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
from denver.providers.privacy import sanitize_messages_for_cloud, sanitize_text_for_cloud
from denver.providers.prompts import build_system_prompt
from denver.security.vault import DenverVault, get_vault

logger = get_logger("providers.groq")


class GroqProvider(AIProvider):
    """High-speed cloud fallback provider powered by Groq."""

    def __init__(
        self,
        vault: DenverVault | None = None,
        base_url: str = "https://api.groq.com/openai/v1",
        default_model: str = "llama-3.1-8b-instant",
        enabled: bool = True,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.vault = vault or get_vault()
        self.base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._enabled = enabled
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "groq"

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.CLOUD

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def default_model(self) -> str:
        return self._default_model

    def _get_api_key(self) -> str | None:
        """Retrieve Groq API key securely from Denver Vault."""
        return self.vault.get_secret("GROQ_API_KEY")

    async def check_health(self) -> ProviderHealth:
        """Check if Groq API key is configured in Vault and test connectivity."""
        if not self._enabled:
            return ProviderHealth(
                provider_name=self.name,
                status=ProviderStatus.NOT_CONFIGURED,
                provider_type=self.provider_type,
                model_name=self.default_model,
                error="Provider disabled in configuration",
            )

        api_key = self._get_api_key()
        if not api_key:
            return ProviderHealth(
                provider_name=self.name,
                status=ProviderStatus.NOT_CONFIGURED,
                provider_type=self.provider_type,
                model_name=self.default_model,
                error="GROQ_API_KEY not found in Denver Vault",
            )

        start = time.perf_counter()
        try:
            url = f"{self.base_url}/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            await asyncio.to_thread(_http_request, url, None, headers, 3.0)
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
            logger.debug("Groq endpoint connection check failed: %s", exc)
            return ProviderHealth(
                provider_name=self.name,
                status=ProviderStatus.UNAVAILABLE,
                provider_type=self.provider_type,
                model_name=self.default_model,
                latency_ms=elapsed_ms,
                error=f"Groq API connection error: {exc}",
            )

    async def list_models(self) -> list[ModelInfo]:
        """List models supported on Groq."""
        api_key = self._get_api_key()
        if not api_key:
            return []
        try:
            url = f"{self.base_url}/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            data = await asyncio.to_thread(_http_request, url, None, headers, 3.0)
            models = []
            for item in data.get("data", []):
                model_id = item.get("id", "")
                models.append(ModelInfo(model_id=model_id, name=model_id))
            return models
        except Exception:
            return []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Send chat completion to Groq cloud endpoint with privacy sanitization."""
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not configured in Denver Vault.")

        start = time.perf_counter()

        # Sanitize prompt before sending to external cloud API
        raw_system_prompt = request.system_prompt or build_system_prompt(
            context_summary=request.context_summary,
            available_tools=None if request.tools else request.tools,
            is_cloud=True,
        )
        system_prompt = sanitize_text_for_cloud(raw_system_prompt)
        sanitized_messages = sanitize_messages_for_cloud(request.messages)

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        model_name = self.default_model

        if request.images and sanitized_messages:
            import base64
            import os
            # If using standard text model, route vision requests to Groq vision model
            if "vision" not in model_name.lower():
                model_name = "llama-3.2-11b-vision-preview"

            for i, msg in enumerate(sanitized_messages):
                if i == len(sanitized_messages) - 1 and msg.get("role") == "user":
                    content_parts: list[dict[str, Any]] = [{"type": "text", "text": msg.get("content", "")}]
                    for img_item in request.images:
                        clean_data = img_item
                        if clean_data.startswith("data:image/"):
                            data_url = clean_data
                        elif os.path.exists(clean_data):
                            with open(clean_data, "rb") as f:
                                b64 = base64.b64encode(f.read()).decode("utf-8")
                            data_url = f"data:image/png;base64,{b64}"
                        else:
                            data_url = f"data:image/png;base64,{clean_data}"
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        })
                    messages.append({"role": "user", "content": content_parts})
                else:
                    messages.append(msg)
        else:
            messages.extend(sanitized_messages)

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.tools:
            payload["tools"] = [t.to_schema() for t in request.tools]
            payload["tool_choice"] = "auto"

        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            res_data = await asyncio.to_thread(_http_request, url, payload, headers, self.timeout_seconds)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

            choices = res_data.get("choices", [])
            content = ""
            tool_calls = []

            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content", "").strip()

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

            if not tool_calls and content:
                for m in _TOOL_JSON_PATTERN.findall(content):
                    try:
                        d = json.loads(m)
                        if isinstance(d, dict) and "action" in d:
                            tool_calls.append(ToolCall(name=d["action"], arguments=d.get("params", {})))
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
            logger.error("Groq generation request failed: %s", exc)
            raise RuntimeError(f"Groq API error: {exc}") from exc
