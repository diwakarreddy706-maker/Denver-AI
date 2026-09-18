"""Unit tests for AI fallback and structured tool calling safety validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from denver.commands.models import CommandCategory, CommandRiskLevel
from denver.commands.registry import ActionDefinition
from denver.commands.service import CommandEngineService
from denver.config.settings import DenverSettings
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.providers.fake import FakeAIProvider
from denver.providers.models import ToolCall
from denver.providers.registry import ProviderRegistry
from denver.providers.router import ProviderRouter
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.state_machine import DenverStateMachine
from denver.runtime.states import DenverState


class TestAIToolCallingAndFallback(unittest.IsolatedAsyncioTestCase):
    """Test suite ensuring AI responses and tool proposals respect the Denver ActionRegistry and SafetyValidator."""

    async def asyncSetUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "tool_test.sqlite3"
        self.db = DenverDatabase(db_path=self.db_path)
        await self.db.initialize()

        self.bus = DenverEventBus()
        self.sm = DenverStateMachine(initial_state=DenverState.STANDBY, event_bus=self.bus)
        self.memory = MemoryService(db=self.db, event_bus=self.bus, privacy_mode=False)

        self.provider_registry = ProviderRegistry()
        self.fake_provider = FakeAIProvider(name="ollama", default_text="I am Denver's local AI model.")
        self.provider_registry.register(self.fake_provider)

        self.router = ProviderRouter(registry=self.provider_registry, event_bus=self.bus)
        self.service = CommandEngineService(
            memory_service=self.memory,
            state_machine=self.sm,
            event_bus=self.bus,
            provider_router=self.router,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.tmp_dir.cleanup()

    async def test_deterministic_command_bypasses_ai(self) -> None:
        """Verify recognized commands go directly through Tier 1 deterministic pipeline without calling AI provider."""
        resp = await self.service.process_command("Denver, what time is it?")
        self.assertTrue(resp.success)
        self.assertEqual(resp.action_name, "get_time")
        # Ensure fake provider was never called
        self.assertEqual(len(self.fake_provider.call_history), 0)

    async def test_conversational_query_routes_to_ai(self) -> None:
        """Verify conversational/complex questions route to AI provider."""
        self.fake_provider.default_text = "TCP uses SYN, SYN-ACK, and ACK packets to establish a reliable stream."
        resp = await self.service.process_command("Denver, explain how TCP three-way handshake works")
        self.assertTrue(resp.success)
        self.assertIn("TCP uses SYN", resp.message)
        self.assertEqual(len(self.fake_provider.call_history), 1)

    async def test_ai_proposes_safe_registered_action(self) -> None:
        """Verify AI proposed registered tool is executed safely through ActionRegistry & ActionExecutor."""
        # Model proposes get_system_status
        self.fake_provider.simulated_tool_calls = [
            ToolCall(action_name="get_system_status", parameters={})
        ]

        resp = await self.service.process_command("Denver, check if the system is running okay")
        self.assertTrue(resp.success)
        self.assertEqual(resp.action_name, "get_system_status")
        self.assertIn("Denver is operational", resp.message)
        self.assertTrue(resp.data.get("ai_proposed", False))

    async def test_ai_proposes_unregistered_action_blocked(self) -> None:
        """Verify AI proposed unregistered action (e.g. execute_shell, del_system32) is blocked with BLOCKED risk level."""
        self.fake_provider.simulated_tool_calls = [
            ToolCall(action_name="execute_shell", parameters={"cmd": "del /f /s /q C:\\*"})
        ]

        resp = await self.service.process_command("Denver, wipe my hard drive")
        self.assertFalse(resp.success)
        self.assertEqual(resp.risk_level, CommandRiskLevel.BLOCKED)
        self.assertIn("not recognized or registered", resp.message)
        self.assertEqual(resp.error, "ActionNotFound")

    async def test_ai_proposes_action_violating_safety(self) -> None:
        """Verify registered action with dangerous injection parameters is blocked by SafetyValidator."""
        # close_application is registered, but model returns dangerous payload
        self.fake_provider.simulated_tool_calls = [
            ToolCall(action_name="close_application", parameters={"application": "calc; rm -rf /"})
        ]

        resp = await self.service.process_command("Denver, please clean up my running apps and run maintenance")
        self.assertFalse(resp.success)
        self.assertEqual(resp.risk_level, CommandRiskLevel.BLOCKED)
        self.assertIn("blocked", resp.message)

    async def test_ai_fallback_when_providers_unavailable(self) -> None:
        """Verify system returns truthful unavailable message if AI provider fails."""
        self.fake_provider.should_fail = True
        self.fake_provider.failure_error = "Local AI daemon unreachable"

        resp = await self.service.process_command("Denver, what is the meaning of life?")
        self.assertFalse(resp.success)
        self.assertIn("No AI provider is currently available", resp.message)
        self.assertIn("Local AI daemon unreachable", resp.data.get("error", ""))


if __name__ == "__main__":
    unittest.main()
