"""Deterministic Fake AI Provider for Testing."""

from __future__ import annotations

import asyncio
from typing import Any

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


class FakeAIProvider(AIProvider):
    """Deterministic, offline fake provider used for reliable unit & integration tests."""

    def __init__(
        self,
        name: str = "fake",
        provider_type: ProviderType = ProviderType.LOCAL,
        default_model: str = "fake-model-v1",
        enabled: bool = True,
        status: ProviderStatus = ProviderStatus.READY,
        canned_text: str = "This is a deterministic fake response.",
        canned_tool_calls: list[ToolCall] | None = None,
        should_fail: bool = False,
        failure_message: str = "Simulated provider failure",
        default_text: str | None = None,
        failure_error: str | None = None,
        simulated_tool_calls: list[ToolCall] | None = None,
    ) -> None:
        self._name = name
        self._provider_type = provider_type
        self._default_model = default_model
        self._enabled = enabled
        self._status = status
        self.canned_text = default_text if default_text is not None else canned_text
        self.canned_tool_calls = (
            simulated_tool_calls if simulated_tool_calls is not None else (canned_tool_calls or [])
        )
        self.should_fail = should_fail
        self.failure_message = failure_error if failure_error is not None else failure_message
        self.requests_received: list[ProviderRequest] = []

    @property
    def call_history(self) -> list[ProviderRequest]:
        return self.requests_received

    @property
    def default_text(self) -> str:
        return self.canned_text

    @default_text.setter
    def default_text(self, value: str) -> None:
        self.canned_text = value

    @property
    def simulated_tool_calls(self) -> list[ToolCall]:
        return self.canned_tool_calls

    @simulated_tool_calls.setter
    def simulated_tool_calls(self, value: list[ToolCall]) -> None:
        self.canned_tool_calls = value

    @property
    def failure_error(self) -> str:
        return self.failure_message

    @failure_error.setter
    def failure_error(self, value: str) -> None:
        self.failure_message = value

    @property
    def name(self) -> str:
        return self._name

    @property
    def provider_type(self) -> ProviderType:
        return self._provider_type

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def default_model(self) -> str:
        return self._default_model

    async def check_health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_name=self.name,
            status=self._status,
            provider_type=self.provider_type,
            model_name=self.default_model,
            latency_ms=1.0,
            error=self.failure_message if self._status == ProviderStatus.ERROR else None,
        )

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(model_id=self.default_model, name=self.default_model)]

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests_received.append(request)
        if self.should_fail:
            raise RuntimeError(self.failure_message)

        return ProviderResponse(
            text=self.canned_text,
            tool_calls=list(self.canned_tool_calls),
            model_name=self.default_model,
            provider_name=self.name,
            latency_ms=5.0,
            token_usage={"prompt_tokens": 10, "completion_tokens": 15, "total_tokens": 25},
        )
