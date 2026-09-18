"""Unit & End-to-End Tests for Denver Command Engine."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from denver.commands.models import CommandRiskLevel
from denver.commands.service import CommandEngineService
from denver.config.settings import DenverSettings
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.events import (
    CommandExecutionCompleted,
    CommandNormalized,
    CommandReceived,
    CommandRouted,
)
from denver.runtime.state_machine import DenverStateMachine
from denver.runtime.states import DenverState


class TestDenverCommandEngine(unittest.IsolatedAsyncioTestCase):
    """Comprehensive test suite for end-to-end command pipeline processing."""

    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "cmd_test.sqlite3"
        self.db = DenverDatabase(db_path=self.db_path)
        await self.db.initialize()

        self.event_bus = DenverEventBus()
        self.state_machine = DenverStateMachine(initial_state=DenverState.STANDBY, event_bus=self.event_bus)
        self.memory = MemoryService(db=self.db, event_bus=self.event_bus, privacy_mode=False)
        self.settings = DenverSettings(assistant_name="Denver", allow_destructive_actions=False)

        self.engine = CommandEngineService(
            memory_service=self.memory,
            state_machine=self.state_machine,
            event_bus=self.event_bus,
            settings=self.settings,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()
        await self.event_bus.shutdown()
        self.temp_dir.cleanup()

    async def test_time_and_date_commands(self) -> None:
        """Verify time and date queries execute successfully and return to STANDBY."""
        res_time = await self.engine.process_command("Denver, what time is it?")
        self.assertTrue(res_time.success)
        self.assertEqual(res_time.action_name, "get_time")
        self.assertIn("The current time is", res_time.message)
        self.assertEqual(self.state_machine.current_state, DenverState.STANDBY)

        res_date = await self.engine.process_command("Denver, what's today's date?")
        self.assertTrue(res_date.success)
        self.assertEqual(res_date.action_name, "get_date")
        self.assertIn("Today's date is", res_date.message)

    async def test_system_telemetry_commands(self) -> None:
        """Verify system status and cpu/ram commands."""
        res_status = await self.engine.process_command("system status")
        self.assertTrue(res_status.success)
        self.assertEqual(res_status.action_name, "get_system_status")

        res_cpu = await self.engine.process_command("get cpu")
        self.assertTrue(res_cpu.success)
        self.assertEqual(res_cpu.action_name, "get_cpu")

        res_ram = await self.engine.process_command("memory usage")
        self.assertTrue(res_ram.success)
        self.assertEqual(res_ram.action_name, "get_ram")

    async def test_note_lifecycle_commands(self) -> None:
        """Verify create note, list notes, search notes end-to-end."""
        # 1. Create note
        res_create = await self.engine.process_command("Denver, create note Project: Build AI desktop assistant")
        self.assertTrue(res_create.success)
        self.assertEqual(res_create.action_name, "create_note")

        # 2. List notes
        res_list = await self.engine.process_command("show notes")
        self.assertTrue(res_list.success)
        self.assertEqual(len(res_list.data["notes"]), 1)

        # 3. Search notes
        res_search = await self.engine.process_command("search notes for desktop")
        self.assertTrue(res_search.success)
        self.assertEqual(len(res_search.data["notes"]), 1)

    async def test_task_lifecycle_commands(self) -> None:
        """Verify create task, list tasks, complete task end-to-end."""
        # 1. Create task
        res_create = await self.engine.process_command("create task Finish Phase 2 Command Engine")
        self.assertTrue(res_create.success)
        task_id = res_create.data["task"]["id"]

        # 2. List tasks
        res_list = await self.engine.process_command("list tasks")
        self.assertTrue(res_list.success)
        self.assertEqual(len(res_list.data["tasks"]), 1)

        # 3. Complete task
        res_done = await self.engine.process_command(f"complete task {task_id}")
        self.assertTrue(res_done.success)

        # Verify active tasks count is now 0
        res_list_after = await self.engine.process_command("list tasks")
        self.assertEqual(len(res_list_after.data["tasks"]), 0)

    async def test_memory_and_preference_commands(self) -> None:
        """Verify preferences and memory storage/recall."""
        # 1. Set Preference
        res_pref = await self.engine.process_command("my favorite editor is VSCode")
        self.assertTrue(res_pref.success)

        # 2. Get Preference
        res_get_pref = await self.engine.process_command("what is my favorite editor")
        self.assertTrue(res_get_pref.success)
        self.assertEqual(res_get_pref.data["value"], "vscode")

        # 3. Remember
        res_rem = await self.engine.process_command("remember that Denver runs locally on Windows")
        self.assertTrue(res_rem.success)

        # 4. Recall
        res_rec = await self.engine.process_command("what do you remember about Denver")
        self.assertTrue(res_rec.success)
        self.assertGreaterEqual(len(res_rec.data["memories"]), 1)

    async def test_unknown_command_behavior(self) -> None:
        """Verify unrecognized command returns truthful response without throwing."""
        res = await self.engine.process_command("make me a sandwich")
        self.assertFalse(res.success)
        self.assertIsNone(res.action_name)
        self.assertEqual(res.message, "I don't know how to do that yet.")
        self.assertEqual(self.state_machine.current_state, DenverState.STANDBY)

    async def test_dangerous_command_blocked_by_safety(self) -> None:
        """Verify prohibited dangerous input is blocked before execution."""
        res = await self.engine.process_command("open cmd.exe /c del /f /q C:\\")
        self.assertFalse(res.success)
        self.assertEqual(res.risk_level, CommandRiskLevel.BLOCKED)
        self.assertIn("blocked", res.message)
        self.assertEqual(self.state_machine.current_state, DenverState.STANDBY)

    async def test_events_published_during_pipeline(self) -> None:
        """Verify event bus receives granular command lifecycle events."""
        events_captured = []

        async def _capture(e):
            events_captured.append(e.__class__.__name__)

        self.event_bus.subscribe(CommandReceived, _capture)
        self.event_bus.subscribe(CommandNormalized, _capture)
        self.event_bus.subscribe(CommandRouted, _capture)
        self.event_bus.subscribe(CommandExecutionCompleted, _capture)

        await self.engine.process_command("Denver, what time is it?")

        self.assertIn("CommandReceived", events_captured)
        self.assertIn("CommandNormalized", events_captured)
        self.assertIn("CommandRouted", events_captured)
        self.assertIn("CommandExecutionCompleted", events_captured)


if __name__ == "__main__":
    unittest.main()
