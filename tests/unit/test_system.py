"""Unit tests for System Telemetry and Workstation Controller."""

from __future__ import annotations

import unittest
from denver.automation.fake import FakeSystemController
from denver.automation.system import SystemController


class TestSystemController(unittest.TestCase):
    """Test suite for system hardware summary telemetry and workstation lock."""

    def setUp(self) -> None:
        self.fake = FakeSystemController()

    def test_fake_get_system_summary(self) -> None:
        """Verify fake system summary returns safe telemetry."""
        res = self.fake.get_system_summary()
        self.assertTrue(res.success)
        self.assertIn("cpu_percent", res.data)
        self.assertIn("ram_percent", res.data)
        self.assertIn("os", res.data)
        self.assertIn("hostname", res.data)

    def test_fake_lock_workstation(self) -> None:
        """Verify fake lock workstation updates state without locking real OS."""
        res = self.fake.lock_workstation()
        self.assertTrue(res.success)
        self.assertTrue(self.fake.state["workstation_locked"])

    def test_real_system_controller_summary(self) -> None:
        """Verify real SystemController retrieves CPU, RAM, and OS telemetry safely."""
        ctrl = SystemController()
        res = ctrl.get_system_summary()
        self.assertTrue(res.success)
        self.assertIn("cpu_percent", res.data)
        self.assertIn("ram_percent", res.data)
        self.assertIn("os", res.data)
        # Ensure no sensitive tokens or environment secrets are exposed in summary
        for key in res.data:
            self.assertNotIn("token", key.lower())
            self.assertNotIn("password", key.lower())
            self.assertNotIn("secret", key.lower())


if __name__ == "__main__":
    unittest.main()
