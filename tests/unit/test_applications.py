"""Unit tests for Allowlisted Application Launcher and Process Closer."""

from __future__ import annotations

import unittest
from unittest.mock import patch
from denver.automation.applications import ApplicationController
from denver.automation.errors import ApplicationLaunchError, ApplicationNotFoundError
from denver.automation.fake import FakeApplicationController
from denver.automation.registry import AutomationRegistry


class TestApplications(unittest.TestCase):
    """Test suite for application controller and fake double."""

    def setUp(self) -> None:
        self.registry = AutomationRegistry()
        self.fake = FakeApplicationController(self.registry)

    def test_fake_launch_allowlisted_application(self) -> None:
        """Verify fake controller safely simulates launching allowlisted app."""
        res = self.fake.launch("notepad")
        self.assertTrue(res.success)
        self.assertEqual(res.target, "Notepad")
        self.assertIn("launched_apps", self.fake.state)
        self.assertIn("notepad", self.fake.state["launched_apps"])

    def test_fake_launch_unknown_application_fails(self) -> None:
        """Verify fake controller rejects unknown application."""
        res = self.fake.launch("nonexistent_binary")
        self.assertFalse(res.success)
        self.assertEqual(res.error, "ApplicationNotFound")

    def test_fake_close_application(self) -> None:
        """Verify fake controller safely simulates closing allowlisted app."""
        self.fake.launch("calculator")
        res = self.fake.close("calculator")
        self.assertTrue(res.success)
        self.assertEqual(res.data.get("terminated_instances"), 1)
        self.assertNotIn("calculator", self.fake.state["launched_apps"])

    def test_real_controller_rejects_unregistered_app(self) -> None:
        """Verify real application controller returns ApplicationNotAllowlisted for unallowlisted apps."""
        ctrl = ApplicationController(self.registry)
        res = ctrl.launch("malicious_hax.exe")
        self.assertFalse(res.success)
        self.assertEqual(res.error, "ApplicationNotAllowlisted")

    def test_real_controller_launch_mocked(self) -> None:
        """Verify real application controller launches allowlisted executable via subprocess when mocked."""
        ctrl = ApplicationController(self.registry)
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 4321
            res = ctrl.launch("notepad")
            self.assertTrue(res.success)
            self.assertEqual(res.target, "Notepad")
            self.assertTrue(mock_popen.called)
            called_args, called_kwargs = mock_popen.call_args
            self.assertTrue(called_args[0][0].lower().endswith("notepad.exe"))
            self.assertEqual(called_kwargs.get("shell"), False)


if __name__ == "__main__":
    unittest.main()
