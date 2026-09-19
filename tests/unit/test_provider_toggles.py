"""Unit tests for Denver Local-First Air-Gapped Mode & AI Provider Toggles."""

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, MagicMock

from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.memory.memory_service import MemoryService
from denver.providers.base import AIProvider
from denver.providers.models import (
    ModelInfo,
    ProviderHealth,
    ProviderRequest,
    ProviderResponse,
    ProviderStatus,
    ProviderType,
)
from denver.providers.registry import ProviderRegistry
from denver.providers.router import ProviderRouter
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.events import AirGappedModeChanged, ProviderModeChanged


class MockLocalProvider(AIProvider):
    def __init__(self, name: str = "ollama"):
        self._name = name
        self._enabled = True
        self._provider_type = ProviderType.LOCAL
        self._default_model = "llama3.2"
        self.generate_mock = AsyncMock(
            return_value=ProviderResponse(text="Local response", model_name="llama3.2", success=True)
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def provider_type(self) -> ProviderType:
        return self._provider_type

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, val: bool) -> None:
        self._enabled = val

    @property
    def default_model(self) -> str:
        return self._default_model

    async def check_health(self) -> ProviderHealth:
        return ProviderHealth(provider_name=self._name, status=ProviderStatus.READY)

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(model_id="llama3.2", name="Llama 3.2")]

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        return await self.generate_mock(request)


class MockCloudProvider(AIProvider):
    def __init__(self, name: str = "groq"):
        self._name = name
        self._enabled = True
        self._provider_type = ProviderType.CLOUD
        self._default_model = "llama-3.1-8b-instant"
        self.generate_mock = AsyncMock(
            return_value=ProviderResponse(text="Cloud response", model_name="llama-3.1-8b-instant", success=True)
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def provider_type(self) -> ProviderType:
        return self._provider_type

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, val: bool) -> None:
        self._enabled = val

    @property
    def default_model(self) -> str:
        return self._default_model

    async def check_health(self) -> ProviderHealth:
        return ProviderHealth(provider_name=self._name, status=ProviderStatus.READY)

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(model_id="llama-3.1-8b-instant", name="Llama 3.1 8B")]

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        return await self.generate_mock(request)


class TestProviderRouterToggles(unittest.IsolatedAsyncioTestCase):
    """Test suite for ProviderRouter dynamic toggles and air-gapped restrictions."""

    async def asyncSetUp(self) -> None:
        self.event_bus = DenverEventBus()
        self.registry = ProviderRegistry()
        self.local_prov = MockLocalProvider("ollama")
        self.cloud_prov = MockCloudProvider("groq")
        self.gemini_prov = MockCloudProvider("gemini")

        self.registry.register(self.local_prov)
        self.registry.register(self.cloud_prov)
        self.registry.register(self.gemini_prov)

        self.router = ProviderRouter(
            registry=self.registry,
            event_bus=self.event_bus,
            priority_order=("ollama", "groq", "gemini"),
            air_gapped_mode=False,
            cloud_fallback_enabled=True,
        )

    async def asyncTearDown(self) -> None:
        await self.event_bus.shutdown()

    def test_default_ordering(self) -> None:
        providers = self.router.get_ordered_providers()
        self.assertEqual(len(providers), 3)
        self.assertEqual(providers[0].name, "ollama")
        self.assertEqual(providers[1].name, "groq")
        self.assertEqual(providers[2].name, "gemini")

    def test_set_active_provider_reordering(self) -> None:
        self.assertTrue(self.router.set_active_provider("gemini"))
        providers = self.router.get_ordered_providers()
        self.assertEqual(providers[0].name, "gemini")
        self.assertEqual(providers[1].name, "ollama")
        self.assertEqual(providers[2].name, "groq")

    def test_air_gapped_mode_filters_cloud_providers(self) -> None:
        self.router.set_air_gapped_mode(True)
        providers = self.router.get_ordered_providers()
        self.assertEqual(len(providers), 1)
        self.assertEqual(providers[0].name, "ollama")
        self.assertEqual(providers[0].provider_type, ProviderType.LOCAL)

    async def test_air_gapped_mode_generation_blocks_cloud(self) -> None:
        self.local_prov.enabled = False
        self.router.set_air_gapped_mode(True)

        req = ProviderRequest(messages=[{"role": "user", "content": "Hello Denver"}])
        res = await self.router.generate(req)
        self.assertFalse(res.success)
        self.assertIn("Air-Gapped mode active", res.error)


class TestProviderCommandRouter(unittest.TestCase):
    """Test suite for regex pattern routing of provider commands."""

    def setUp(self) -> None:
        self.router = IntentRouter()

    def test_air_gapped_commands(self) -> None:
        for phrase in [
            "switch to local only mode",
            "air-gapped mode",
            "go offline",
            "disconnect cloud",
            "enable air gap mode",
        ]:
            intent = self.router.route(phrase)
            self.assertEqual(intent.action_name, "set_air_gap_mode", f"Failed for: {phrase}")
            self.assertTrue(intent.params.get("enabled"))

    def test_cloud_enable_commands(self) -> None:
        for phrase in [
            "switch to cloud mode",
            "go online",
            "connect cloud",
            "disable air-gapped mode",
        ]:
            intent = self.router.route(phrase)
            self.assertEqual(intent.action_name, "set_air_gap_mode", f"Failed for: {phrase}")
            self.assertFalse(intent.params.get("enabled"))

    def test_switch_provider_commands(self) -> None:
        cases = [
            ("switch to groq", "groq"),
            ("switch provider to gemini", "gemini"),
            ("use ollama", "ollama"),
            ("set provider to lmstudio", "lmstudio"),
        ]
        for phrase, expected_prov in cases:
            intent = self.router.route(phrase)
            self.assertEqual(intent.action_name, "switch_llm_provider", f"Failed for: {phrase}")
            self.assertEqual(intent.params.get("provider"), expected_prov)


class TestProviderServiceIntegration(unittest.IsolatedAsyncioTestCase):
    """Test suite for CommandEngineService execution and event emission."""

    async def asyncSetUp(self) -> None:
        os.environ["DENVER_MOCK_AUTOMATION"] = "true"
        self.event_bus = DenverEventBus()
        self.memory_service = MagicMock(spec=MemoryService)
        self.registry = ProviderRegistry()
        self.local_prov = MockLocalProvider("ollama")
        self.cloud_prov = MockCloudProvider("groq")
        self.registry.register(self.local_prov)
        self.registry.register(self.cloud_prov)

        self.provider_router = ProviderRouter(
            registry=self.registry,
            event_bus=self.event_bus,
            priority_order=("groq", "ollama"),
        )

        self.service = CommandEngineService(
            memory_service=self.memory_service,
            event_bus=self.event_bus,
            provider_router=self.provider_router,
        )

    async def asyncTearDown(self) -> None:
        os.environ.pop("DENVER_MOCK_AUTOMATION", None)
        await self.event_bus.shutdown()

    async def test_set_air_gap_mode_command(self) -> None:
        events: list[AirGappedModeChanged] = []

        async def on_event(ev: AirGappedModeChanged) -> None:
            events.append(ev)

        self.event_bus.subscribe(AirGappedModeChanged, on_event)

        res = await self.service.process_command("Denver, switch to local only mode")
        self.assertTrue(res.success)
        self.assertEqual(res.action_name, "set_air_gap_mode")
        self.assertTrue(self.provider_router.air_gapped_mode)

        await asyncio.sleep(0.05)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].enabled)

    async def test_switch_llm_provider_command(self) -> None:
        events: list[ProviderModeChanged] = []

        async def on_event(ev: ProviderModeChanged) -> None:
            events.append(ev)

        self.event_bus.subscribe(ProviderModeChanged, on_event)

        res = await self.service.process_command("Denver, switch provider to ollama")
        self.assertTrue(res.success)
        self.assertEqual(res.action_name, "switch_llm_provider")
        self.assertEqual(self.provider_router.active_provider, "ollama")

        await asyncio.sleep(0.05)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].active_provider, "ollama")


if __name__ == "__main__":
    unittest.main()
