"""Unit tests for Denver Health Service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from denver.health.health_service import DenverHealthService
from denver.memory.database import DenverDatabase
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.state_machine import DenverStateMachine
from denver.runtime.states import DenverState


class TestDenverHealthService(unittest.IsolatedAsyncioTestCase):
    """Test suite for health reports and subsystem telemetry."""

    async def asyncSetUp(self) -> None:
        self.bus = DenverEventBus()
        self.sm = DenverStateMachine(initial_state=DenverState.BOOTING, event_bus=self.bus)
        self.health = DenverHealthService(state_machine=self.sm, event_bus=self.bus)

    async def test_health_report_structure(self) -> None:
        """Verify health report contains required metadata and telemetry keys."""
        report = self.health.get_health_report()
        self.assertEqual(report["assistant"], "Denver")
        self.assertEqual(report["product"], "Denver AI Assistant")
        self.assertEqual(report["status"], "HEALTHY")
        self.assertEqual(report["current_state"], "BOOTING")
        self.assertIn("uptime_seconds", report)
        self.assertIn("system_info", report)
        self.assertIn("telemetry", report)
        self.assertIn("subsystems", report)

    async def test_subsystems_reporting(self) -> None:
        """Verify subsystem status accuracy (NOT_CONFIGURED for unattached db/ai, NOT_IMPLEMENTED for unbuilt subsystems)."""
        subsystems = self.health.get_subsystems_status()
        self.assertEqual(subsystems["core_runtime"], "READY")
        self.assertEqual(subsystems["event_bus"], "READY")
        self.assertEqual(subsystems["database"], "NOT_CONFIGURED")
        self.assertEqual(subsystems["audio"], "NOT_CONFIGURED")
        self.assertEqual(subsystems["ai_providers"], "NOT_CONFIGURED")
        self.assertEqual(subsystems["automation"], "NOT_CONFIGURED")
        self.assertEqual(subsystems["plugins"], "NOT_IMPLEMENTED")
        self.assertEqual(subsystems["ui"], "NOT_IMPLEMENTED")

    async def test_database_health_reporting_when_attached(self) -> None:
        """Verify database reports READY and details when attached."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "health_test.sqlite3"
            db = DenverDatabase(db_path=db_path)
            await db.initialize()
            health_with_db = DenverHealthService(state_machine=self.sm, event_bus=self.bus, database=db)

            subsystems = health_with_db.get_subsystems_status()
            self.assertEqual(subsystems["database"], "READY")

            report = health_with_db.get_health_report()
            self.assertIn("database", report)
            self.assertEqual(report["database"]["status"], "READY")
            self.assertEqual(report["database"]["journal_mode"].lower(), "wal")
            await db.close()

    async def test_degraded_status_on_error_state(self) -> None:
        """Verify health report status degrades when state machine is in ERROR."""
        await self.sm.transition_to(DenverState.ERROR, reason="Simulated subsystem failure")
        report = self.health.get_health_report()
        self.assertEqual(report["status"], "DEGRADED")
        self.assertEqual(report["current_state"], "ERROR")


if __name__ == "__main__":
    unittest.main()
