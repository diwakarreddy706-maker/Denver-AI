"""Google Gemini Cloud AI Provider for Denver AI Assistant."""

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

logger = get_logger("providers.gemini")


class GeminiProvider(AIProvider):
    """Google Gemini AI cloud provider."""

    def __init__(
        self,
        vault: DenverVault | None = None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        default_model: str = "gemini-flash-latest",
        enabled: bool = True,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.vault = vault or get_vault()
        self.base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._enabled = enabled
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "gemini"

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
        """Retrieve Gemini API key securely from Denver Vault."""
        return self.vault.get_secret("GEMINI_API_KEY")

    async def check_health(self) -> ProviderHealth:
        """Check if GEMINI_API_KEY is configured in Vault and probe connectivity."""
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
                error="GEMINI_API_KEY not found in Denver Vault",
            )

        start = time.perf_counter()
        try:
            url = f"{self.base_url}/models?key={api_key}"
            await asyncio.to_thread(_http_request, url, None, None, 3.0)
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
            logger.debug("Gemini connection probe failed: %s", exc)
            return ProviderHealth(
                provider_name=self.name,
                status=ProviderStatus.UNAVAILABLE,
                provider_type=self.provider_type,
                model_name=self.default_model,
                latency_ms=elapsed_ms,
                error=f"Gemini API connection error: {exc}",
            )

    async def list_models(self) -> list[ModelInfo]:
        """List models available on Gemini."""
        api_key = self._get_api_key()
        if not api_key:
            return []
        try:
            url = f"{self.base_url}/models?key={api_key}"
            data = await asyncio.to_thread(_http_request, url, None, None, 3.0)
            models = []
            for item in data.get("models", []):
                name = item.get("name", "").replace("models/", "")
                models.append(ModelInfo(model_id=name, name=name))
            return models
        except Exception:
            return []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Send chat generation request to Google Gemini API."""
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured in Denver Vault.")

        start = time.perf_counter()

        raw_system_prompt = request.system_prompt or build_system_prompt(
            context_summary=request.context_summary,
            available_tools=request.tools,
            is_cloud=True,
        )
        system_prompt = sanitize_text_for_cloud(raw_system_prompt)
        sanitized_messages = sanitize_messages_for_cloud(request.messages)

        # Structure Gemini contents
        contents = []
        for msg in sanitized_messages:
            role = "user" if msg.get("role") in {"user", "system"} else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg.get("content", "")}],
            })

        # Attach multimodal images to the last user message
        if request.images and contents:
            import base64
            import os
            for img_item in request.images:
                clean_data = img_item
                mime_type = "image/png"
                if clean_data.startswith("data:image/"):
                    header, clean_data = clean_data.split(",", 1)
                    if "image/jpeg" in header or "image/jpg" in header:
                        mime_type = "image/jpeg"
                elif os.path.exists(clean_data):
                    with open(clean_data, "rb") as f:
                        clean_data = base64.b64encode(f.read()).decode("utf-8")
                contents[-1]["parts"].append({
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": clean_data,
                    }
                })

        payload = {
            "systemInstruction": {
                "parts": [{"text": system_prompt}],
            },
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }

        url = f"{self.base_url}/models/{self.default_model}:generateContent?key={api_key}"

        try:
            res_data = await asyncio.to_thread(_http_request, url, payload, None, self.timeout_seconds)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

            candidates = res_data.get("candidates", [])
            content = ""
            tool_calls = []

            if candidates:
                cand = candidates[0]
                parts = cand.get("content", {}).get("parts", [])
                text_chunks = []
                for p in parts:
                    if "text" in p:
                        text_chunks.append(p["text"])
                    if "functionCall" in p:
                        fc = p["functionCall"]
                        tool_calls.append(ToolCall(name=fc.get("name", ""), arguments=fc.get("args", {})))
                content = "".join(text_chunks).strip()

            if not tool_calls and content:
                for m in _TOOL_JSON_PATTERN.findall(content):
                    try:
                        d = json.loads(m)
                        if isinstance(d, dict) and "action" in d:
                            tool_calls.append(ToolCall(name=d["action"], arguments=d.get("params", {})))
                    except json.JSONDecodeError:
                        pass

            meta = res_data.get("usageMetadata", {})
            return ProviderResponse(
                text=content,
                tool_calls=tool_calls,
                model_name=self.default_model,
                provider_name=self.name,
                latency_ms=elapsed_ms,
                token_usage={
                    "prompt_tokens": meta.get("promptTokenCount", 0),
                    "completion_tokens": meta.get("candidatesTokenCount", 0),
                    "total_tokens": meta.get("totalTokenCount", 0),
                },
                raw_response=res_data,
            )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error("Gemini generate failed: %s", exc)
            raise RuntimeError(f"Gemini API error: {exc}") from exc
