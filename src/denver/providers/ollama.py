"""Ollama Local AI Provider for Denver AI Assistant."""

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
from denver.providers.prompts import build_system_prompt

logger = get_logger("providers.ollama")

_TOOL_JSON_PATTERN = re.compile(r"```(?:json)?\s*(\{\s*\"action\"[\s\S]*?\})\s*```", re.IGNORECASE)


def _http_request(url: str, data: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: float = 10.0) -> dict[str, Any]:
    """Execute synchronous HTTP request safely via urllib."""
    req_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Denver/1.0 (Windows NT 10.0; Win64; x64)",
    }
    if headers:
        req_headers.update(headers)

    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=req_headers, method="POST" if data is not None else "GET")

    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw_bytes = response.read()
        return json.loads(raw_bytes.decode("utf-8"))


class OllamaProvider(AIProvider):
    """Local-first AI provider using Ollama daemon."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = "llama3.2",
        enabled: bool = True,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._enabled = enabled
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "ollama"

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
        """Probe Ollama /api/tags endpoint to check if daemon is active."""
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
            url = f"{self.base_url}/api/tags"
            data = await asyncio.to_thread(_http_request, url, None, None, 1.5)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            models = data.get("models", [])
            return ProviderHealth(
                provider_name=self.name,
                status=ProviderStatus.READY,
                provider_type=self.provider_type,
                model_name=self.default_model,
                latency_ms=elapsed_ms,
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.debug("Ollama is unavailable at '%s': %s", self.base_url, exc)
            return ProviderHealth(
                provider_name=self.name,
                status=ProviderStatus.UNAVAILABLE,
                provider_type=self.provider_type,
                model_name=self.default_model,
                latency_ms=elapsed_ms,
                error=f"Cannot connect to Ollama: {exc}",
            )

    async def list_models(self) -> list[ModelInfo]:
        """List local models installed in Ollama."""
        try:
            url = f"{self.base_url}/api/tags"
            data = await asyncio.to_thread(_http_request, url, None, None, 3.0)
            models = []
            for item in data.get("models", []):
                name = item.get("name", "")
                models.append(ModelInfo(model_id=name, name=name, family=item.get("details", {}).get("family")))
            return models
        except Exception:
            return []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Send chat generation request to Ollama."""
        start = time.perf_counter()
        system_prompt = request.system_prompt or build_system_prompt(
            context_summary=request.context_summary,
            available_tools=request.tools,
            is_cloud=False,
        )

        messages = [{"role": "system", "content": system_prompt}] + [dict(m) for m in request.messages]
        if request.images and messages:
            import base64
            import os
            clean_images = []
            for img_item in request.images:
                clean_data = img_item
                if clean_data.startswith("data:image/"):
                    _, clean_data = clean_data.split(",", 1)
                elif os.path.exists(clean_data):
                    with open(clean_data, "rb") as f:
                        clean_data = base64.b64encode(f.read()).decode("utf-8")
                clean_images.append(clean_data)
            messages[-1]["images"] = clean_images

        payload = {
            "model": self.default_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        url = f"{self.base_url}/api/chat"
        try:
            res_data = await asyncio.to_thread(_http_request, url, payload, None, self.timeout_seconds)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

            message_obj = res_data.get("message", {})
            content = message_obj.get("content", "").strip()

            # Parse tool calls from markdown codeblocks or JSON text if present
            tool_calls = self._extract_tool_calls(content)

            return ProviderResponse(
                text=content,
                tool_calls=tool_calls,
                model_name=self.default_model,
                provider_name=self.name,
                latency_ms=elapsed_ms,
                token_usage={
                    "prompt_eval_count": res_data.get("prompt_eval_count", 0),
                    "eval_count": res_data.get("eval_count", 0),
                },
                raw_response=res_data,
            )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error("Ollama generate failed: %s", exc)
            raise RuntimeError(f"Ollama generation failed: {exc}") from exc

    def _extract_tool_calls(self, content: str) -> list[ToolCall]:
        """Extract structured JSON tool calls from model output."""
        calls = []
        matches = _TOOL_JSON_PATTERN.findall(content)
        for m in matches:
            try:
                data = json.loads(m)
                if isinstance(data, dict) and "action" in data:
                    calls.append(ToolCall(name=data["action"], arguments=data.get("params", {})))
            except json.JSONDecodeError:
                pass
        return calls
