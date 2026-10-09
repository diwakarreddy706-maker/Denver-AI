"""Abstract Base Class for Denver AI Providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from denver.providers.models import (
    ModelInfo,
    ProviderHealth,
    ProviderRequest,
    ProviderResponse,
    ProviderStatus,
    ProviderType,
)


class AIProvider(ABC):
    """Abstract interface contract for all local and cloud AI providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier of the provider (e.g. 'ollama', 'groq')."""

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType:
        """Whether this provider runs locally or in the cloud."""

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Whether this provider is currently enabled in configuration."""

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Name of the default model utilized by this provider."""

    @abstractmethod
    async def check_health(self) -> ProviderHealth:
        """Probe provider availability and return status without throwing."""

    @abstractmethod
    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Execute chat completion / inference request."""

    async def stream_generate(self, request: ProviderRequest):
        """Yield text tokens incrementally. Falls back to generate() if streaming is not overridden."""
        import logging
        logging.getLogger("provider_base").info(
            "Provider '%s' does not implement native token streaming; falling back to whole-response generation.",
            self.name,
        )
        response = await self.generate(request)
        if response.text:
            yield response.text

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """List models available on this provider."""
