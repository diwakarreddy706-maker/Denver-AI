"""Provider Registry for Denver AI Providers."""

from __future__ import annotations

import asyncio
from typing import Any

from denver.logging.logger import get_logger
from denver.providers.base import AIProvider
from denver.providers.models import ProviderHealth, ProviderStatus, ProviderType

logger = get_logger("providers.registry")


class ProviderRegistry:
    """Central catalog of registered AI providers."""

    def __init__(self) -> None:
        self._providers: dict[str, AIProvider] = {}

    def register(self, provider: AIProvider) -> None:
        """Register a provider instance. Rejects duplicates."""
        name = provider.name.strip().lower()
        if not name:
            raise ValueError("Provider name cannot be empty.")
        if name in self._providers:
            raise ValueError(f"Provider '{name}' is already registered in ProviderRegistry.")

        self._providers[name] = provider
        logger.debug("Registered AI provider '%s' [%s, model=%s]", name, provider.provider_type.value, provider.default_model)

    def unregister(self, name: str) -> bool:
        """Unregister a provider."""
        name = name.strip().lower()
        if name in self._providers:
            del self._providers[name]
            logger.debug("Unregistered AI provider '%s'", name)
            return True
        return False

    def get(self, name: str) -> AIProvider | None:
        """Retrieve provider by name."""
        return self._providers.get(name.strip().lower())

    def list_providers(self) -> list[AIProvider]:
        """List all registered providers."""
        return list(self._providers.values())

    async def check_health_all(self) -> dict[str, ProviderHealth]:
        """Query health of all registered providers concurrently."""
        tasks = [provider.check_health() for provider in self._providers.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        health_map = {}
        for provider, res in zip(self._providers.values(), results):
            if isinstance(res, ProviderHealth):
                health_map[provider.name] = res
            else:
                health_map[provider.name] = ProviderHealth(
                    provider_name=provider.name,
                    status=ProviderStatus.ERROR,
                    provider_type=provider.provider_type,
                    model_name=provider.default_model,
                    error=str(res),
                )
        return health_map

    def clear(self) -> None:
        """Clear all registered providers."""
        self._providers.clear()
