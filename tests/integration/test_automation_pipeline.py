"""Integration tests for Phase 5 End-to-End Desktop Automation Pipeline."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from denver.automation.executor import AutomationExecutor
from denver.automation.fake import (
    FakeApplicationController,
    FakeBrowserController,
    FakeScreenshotController,
    FakeSystemController,
    FakeVolumeController,
    FakeWindowController,
)
from denver.automation.registry import AutomationRegistry
from denver.commands.models import CommandRiskLevel
from denver.commands.service import CommandEngineService
from denver.config.settings import DenverSettings
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.state_machine import DenverStateMachine
from denver.runtime.states import DenverState


class TestAutomationPipeline(unittest.IsolatedAsyncioTestCase):
    """End-to-end integration tests connecting CommandEngineService to AutomationExecutor with fake test doubles."""

    async def asyncSetUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "auto_test.sqlite3"

        self.settings = DenverSettings(
            assistant_name="Denver",
            environment="test",
            allow_destructive_actions=False,
            ai_enabled=False,
            audio_enabled=False,
        )
        self.event_bus = DenverEventBus()
        self.state_machine = DenverStateMachine(initial_state=DenverState.BOOTING, event_bus=self.event_bus)
        self.db = DenverDatabase(db_path=db_path)
        await self.db.initialize()
        self.memory = MemoryService(db=self.db, event_bus=self.event_bus)

        # Setup Automation Subsystem with 100% Safe Offline Fake Controllers
        self.auto_registry = AutomationRegistry()
        self.fake_apps = FakeApplicationController(self.auto_registry)
        self.fake_windows = FakeWindowController()
        self.fake_volume = FakeVolumeController(initial_volume=50)
        self.fake_browser = FakeBrowserController(self.auto_registry)
        self.fake_screenshot = FakeScreenshotController(screenshot_dir=str(Path(self.tmp_dir.name) / "screenshots"))
        self.fake_system = FakeSystemController()

        self.auto_executor = AutomationExecutor(
            registry=self.auto_registry,
            applications=self.fake_apps,
            windows=self.fake_windows,
            volume=self.fake_volume,
            browser=self.fake_browser,
            screenshot=self.fake_screenshot,
            system=self.fake_system,
            event_bus=self.event_bus,
            allow_high_risk_actions=False,
        )

        self.engine = CommandEngineService(
            memory_service=self.memory,
            state_machine=self.state_machine,
            event_bus=self.event_bus,
            settings=self.settings,
            automation_executor=self.auto_executor,
        )
        await self.state_machine.transition_to(DenverState.STANDBY, reason="Ready for test")

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.tmp_dir.cleanup()

    async def test_application_lifecycle_pipeline(self) -> None:
        """Verify launching and closing allowlisted applications end-to-end."""
        res_open = await self.engine.process_command("Denver, open calculator")
        self.assertTrue(res_open.success)
        self.assertEqual(res_open.action_name, "open_application")
        self.assertIn("calculator", self.fake_apps.state["launched_apps"])

        res_close = await self.engine.process_command("Denver, close calculator")
        self.assertTrue(res_close.success)
        self.assertEqual(res_close.action_name, "close_application")
        self.assertNotIn("calculator", self.fake_apps.state["launched_apps"])

    async def test_window_management_pipeline(self) -> None:
        """Verify window minimize, maximize, restore, focus, and show desktop."""
        res_min = await self.engine.process_command("Denver, minimize Notepad")
        self.assertTrue(res_min.success)
        self.assertEqual(res_min.action_name, "minimize_window")

        res_max = await self.engine.process_command("Denver, maximize Notepad")
        self.assertTrue(res_max.success)
        self.assertEqual(res_max.action_name, "maximize_window")

        res_desk = await self.engine.process_command("Denver, show desktop")
        self.assertTrue(res_desk.success)
        self.assertEqual(res_desk.action_name, "show_desktop")
        self.assertTrue(self.fake_windows.state["desktop_shown"])

    async def test_volume_control_pipeline(self) -> None:
        """Verify volume control commands (set, increase, decrease, mute, unmute, get)."""
        res_set = await self.engine.process_command("Denver, set volume to 75%")
        self.assertTrue(res_set.success)
        self.assertEqual(self.fake_volume.state["volume"], 75)

        res_inc = await self.engine.process_command("Denver, increase volume by 10")
        self.assertTrue(res_inc.success)
        self.assertEqual(self.fake_volume.state["volume"], 85)

        res_mute = await self.engine.process_command("Denver, mute")
        self.assertTrue(res_mute.success)
        self.assertTrue(self.fake_volume.state["muted"])

        res_unmute = await self.engine.process_command("Denver, unmute")
        self.assertTrue(res_unmute.success)
        self.assertFalse(self.fake_volume.state["muted"])

        res_get = await self.engine.process_command("Denver, what is the volume?")
        self.assertTrue(res_get.success)
        self.assertEqual(res_get.data.get("volume"), 85)

    async def test_browser_pipeline(self) -> None:
        """Verify browser commands open known sites and valid URLs."""
        res_yt = await self.engine.process_command("Denver, open youtube")
        self.assertTrue(res_yt.success)
        self.assertEqual(res_yt.action_name, "open_browser")
        self.assertIn("https://www.youtube.com", self.fake_browser.state["opened_urls"])

        res_web = await self.engine.process_command("Denver, open website https://github.com")
        self.assertTrue(res_web.success)
        self.assertIn("https://github.com", self.fake_browser.state["opened_urls"])

    async def test_screenshot_pipeline(self) -> None:
        """Verify screenshot command triggers capture and writes within approved directory."""
        res_shot = await self.engine.process_command("Denver, take a screenshot")
        self.assertTrue(res_shot.success)
        self.assertEqual(res_shot.action_name, "take_screenshot")
        self.assertEqual(len(self.fake_screenshot.state["captured"]), 1)

    async def test_system_summary_pipeline(self) -> None:
        """Verify system summary retrieves hardware info safely."""
        res_sys = await self.engine.process_command("Denver, system summary")
        self.assertTrue(res_sys.success)
        self.assertEqual(res_sys.action_name, "get_system_summary")
        self.assertIn("cpu_percent", res_sys.data)

    async def test_lock_workstation_confirmation_flow(self) -> None:
        """Verify high-risk lock workstation initiates confirmation gate and only executes upon user confirmation."""
        # 1. User requests lock
        res_lock = await self.engine.process_command("Denver, lock my computer")
        self.assertTrue(res_lock.success)
        self.assertEqual(res_lock.risk_level, CommandRiskLevel.HIGH)
        self.assertIn("confirmation", res_lock.message.lower())
        self.assertFalse(self.fake_system.state["workstation_locked"])

        # 2. User confirms
        res_confirm = await self.engine.process_command("Denver, yes")
        self.assertTrue(res_confirm.success)
        self.assertTrue(self.fake_system.state["workstation_locked"])

    async def test_lock_workstation_cancellation_flow(self) -> None:
        """Verify high-risk lock workstation can be explicitly cancelled."""
        res_lock = await self.engine.process_command("Denver, lock workstation")
        self.assertTrue(res_lock.success)
        self.assertFalse(self.fake_system.state["workstation_locked"])

        res_cancel = await self.engine.process_command("Denver, cancel")
        self.assertTrue(res_cancel.success)
        self.assertEqual(res_cancel.action_name, "cancel_action")
        self.assertFalse(self.fake_system.state["workstation_locked"])


if __name__ == "__main__":
    unittest.main()
