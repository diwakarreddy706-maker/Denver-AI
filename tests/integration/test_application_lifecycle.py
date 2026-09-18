"""Integration tests for Denver Application Lifecycle and Bootstrap."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from denver import __version__, assistant_name, product_name
from denver.app.application import DenverApplication
from denver.app.bootstrap import main
from denver.config.settings import DenverSettings
from denver.runtime.events import ApplicationStarted, ApplicationStopping, StateChanged
from denver.runtime.states import DenverState


class TestDenverApplicationLifecycle(unittest.IsolatedAsyncioTestCase):
    """Integration test suite for end-to-end application lifecycle orchestration."""

    async def test_full_application_lifecycle(self) -> None:
        """Verify BOOTING -> STANDBY -> SHUTTING_DOWN -> STOPPED sequence with event emissions."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "lifecycle_test.sqlite3"
            settings = DenverSettings(
                environment="test",
                log_level="DEBUG",
                log_file_path=None,  # Suppress file writes in test
                database_path=db_path,
            )
            app = DenverApplication(settings=settings)

            events_received: list[str] = []

            app.event_bus.subscribe(ApplicationStarted, lambda _: events_received.append("STARTED"))
            app.event_bus.subscribe(ApplicationStopping, lambda _: events_received.append("STOPPING"))
            app.event_bus.subscribe(StateChanged, lambda e: events_received.append(f"{e.from_state}->{e.to_state}"))

            self.assertEqual(app.state_machine.current_state, DenverState.BOOTING)

            # 1. Start application
            await app.start()
            self.assertEqual(app.state_machine.current_state, DenverState.STANDBY)
            self.assertIn("BOOTING->STANDBY", events_received)
            self.assertIn("STARTED", events_received)

            # 2. Check health service state
            health = app.health_service.get_health_report()
            self.assertEqual(health["current_state"], "STANDBY")
            self.assertEqual(health["status"], "HEALTHY")
            self.assertEqual(health["subsystems"]["database"], "READY")

            # 3. Test memory creation through app
            item = await app.memory_service.create_memory("lifecycle", "test_key", "Lifecycle value")
            self.assertIsNotNone(item)

            # 4. Test command processing through app
            cmd_res = await app.process_command("Denver, what time is it?")
            self.assertTrue(cmd_res.success)
            self.assertEqual(cmd_res.action_name, "get_time")

            # 5. Stop application
            await app.stop(reason="test_completion")
            self.assertEqual(app.state_machine.current_state, DenverState.STOPPED)
            self.assertIn("STOPPING", events_received)
            self.assertIn("STANDBY->SHUTTING_DOWN", events_received)
            self.assertIn("SHUTTING_DOWN->STOPPED", events_received)

    def test_cli_version_flag(self) -> None:
        """Verify python -m denver --version outputs identity and exits 0."""
        stdout_buf = io.StringIO()
        with redirect_stdout(stdout_buf):
            exit_code = main(["--version"])
        self.assertEqual(exit_code, 0)
        output = stdout_buf.getvalue()
        self.assertIn(product_name, output)
        self.assertIn(assistant_name, output)
        self.assertIn(__version__, output)

    def test_cli_health_flag(self) -> None:
        """Verify python -m denver --health outputs valid JSON health report with real database status."""
        stdout_buf = io.StringIO()
        with redirect_stdout(stdout_buf):
            exit_code = main(["--health"])
        self.assertEqual(exit_code, 0)
        report = json.loads(stdout_buf.getvalue())
        self.assertEqual(report["assistant"], "Denver")
        self.assertIn("uptime_seconds", report)
        self.assertEqual(report["subsystems"]["database"], "READY")
        self.assertIn("database", report)
        self.assertEqual(report["database"]["status"], "READY")
        self.assertEqual(report["database"]["journal_mode"].lower(), "wal")

    def test_cli_check_config_flag(self) -> None:
        """Verify python -m denver --check-config outputs sanitized JSON configuration."""
        stdout_buf = io.StringIO()
        with redirect_stdout(stdout_buf):
            exit_code = main(["--check-config"])
        self.assertEqual(exit_code, 0)
        config = json.loads(stdout_buf.getvalue())
        self.assertEqual(config["assistant_name"], "Denver")
        self.assertIn("ai_mode", config)
        self.assertIn("database_path", config)

    def test_cli_command_flag(self) -> None:
        """Verify python -m denver --command executes a text command and outputs structured JSON."""
        stdout_buf = io.StringIO()
        with redirect_stdout(stdout_buf):
            exit_code = main(["--command", "Denver, what time is it?"])
        self.assertEqual(exit_code, 0)
        res = json.loads(stdout_buf.getvalue())
        self.assertTrue(res["success"])
        self.assertEqual(res["action"], "get_time")
        self.assertIn("The current time is", res["message"])


if __name__ == "__main__":
    unittest.main()
