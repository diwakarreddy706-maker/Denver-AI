"""Unit tests for Denver ProviderRouter and fallback orchestration."""

from __future__ import annotations

import unittest

from denver.providers.fake import FakeAIProvider
from denver.providers.models import (
    ProviderRequest,
    ProviderResponse,
    ProviderStatus,
    ProviderType,
    ToolCall,
)
from denver.providers.registry import ProviderRegistry
from denver.providers.router import ProviderRouter
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.events import ProviderFallback, ProviderRequestStarted, ProviderResponseReceived


class TestProviderRouter(unittest.IsolatedAsyncioTestCase):
    """Test suite for local-first provider resolution, fallback, and events."""

    async def asyncSetUp(self) -> None:
        self.bus = DenverEventBus()
        self.registry = ProviderRegistry()

    async def test_local_first_priority_selection(self) -> None:
        """Verify router prioritizes local provider over cloud provider."""
        local_fake = FakeAIProvider(name="ollama", provider_type=ProviderType.LOCAL, default_text="Response from Ollama")
        cloud_fake = FakeAIProvider(name="groq", provider_type=ProviderType.CLOUD, default_text="Response from Groq")

        self.registry.register(local_fake)
        self.registry.register(cloud_fake)

        router = ProviderRouter(
            registry=self.registry,
            event_bus=self.bus,
            priority_order=("ollama", "groq"),
            local_first=True,
        )

        res = await router.generate(ProviderRequest(messages=[{"role": "user", "content": "Hello"}]))
        self.assertTrue(res.success)
        self.assertEqual(res.provider_name, "ollama")
        self.assertEqual(res.text, "Response from Ollama")

    async def test_fallback_on_primary_failure(self) -> None:
        """Verify router falls back to next provider when primary fails and emits ProviderFallback event."""
        events: list[str] = []

        async def _on_event(ev: object) -> None:
            if isinstance(ev, ProviderFallback):
                events.append(f"FALLBACK:{ev.from_provider}->{ev.to_provider}")

        self.bus.subscribe(ProviderFallback, _on_event)

        failing_local = FakeAIProvider(name="ollama", should_fail=True, failure_error="Ollama connection refused")
        healthy_cloud = FakeAIProvider(name="groq", default_text="Response from Groq fallback")

        self.registry.register(failing_local)
        self.registry.register(healthy_cloud)

        router = ProviderRouter(
            registry=self.registry,
            event_bus=self.bus,
            priority_order=("ollama", "groq"),
        )

        res = await router.generate(ProviderRequest(messages=[{"role": "user", "content": "Hello"}]))
        self.assertTrue(res.success)
        self.assertEqual(res.provider_name, "groq")
        self.assertEqual(res.text, "Response from Groq fallback")
        self.assertIn("FALLBACK:ollama->groq", events)

    async def test_all_providers_failing(self) -> None:
        """Verify router returns typed failure response when all providers fail without throwing unhandled exceptions."""
        p1 = FakeAIProvider(name="ollama", should_fail=True, failure_error="Ollama dead")
        p2 = FakeAIProvider(name="lmstudio", should_fail=True, failure_error="LM Studio dead")

        self.registry.register(p1)
        self.registry.register(p2)

        router = ProviderRouter(
            registry=self.registry,
            event_bus=self.bus,
            priority_order=("ollama", "lmstudio"),
        )

        res = await router.generate(ProviderRequest(messages=[{"role": "user", "content": "Hello"}]))
        self.assertFalse(res.success)
        self.assertIn("All available AI providers failed", res.error or "")

    async def test_no_providers_registered(self) -> None:
        """Verify router handles empty registry cleanly."""
        router = ProviderRouter(registry=self.registry, event_bus=self.bus)
        res = await router.generate(ProviderRequest(messages=[{"role": "user", "content": "Hello"}]))
        self.assertFalse(res.success)
        self.assertIn("No AI provider is currently available", res.error or "")

    async def test_custom_priority_order(self) -> None:
        """Verify priority order can be customized via tuple config."""
        p1 = FakeAIProvider(name="ollama", default_text="Ollama")
        p2 = FakeAIProvider(name="lmstudio", default_text="LMStudio")

        self.registry.register(p1)
        self.registry.register(p2)

        # Reverse priority: LM Studio first
        router = ProviderRouter(
            registry=self.registry,
            event_bus=self.bus,
            priority_order=("lmstudio", "ollama"),
        )

        ordered = router.get_ordered_providers()
        self.assertEqual(ordered[0].name, "lmstudio")
        self.assertEqual(ordered[1].name, "ollama")

        res = await router.generate(ProviderRequest(messages=[{"role": "user", "content": "Hi"}]))
        self.assertEqual(res.provider_name, "lmstudio")


if __name__ == "__main__":
    unittest.main()
