"""Unit tests for Window Management Controller."""

from __future__ import annotations

import unittest
from denver.automation.fake import FakeWindowController
from denver.automation.models import WindowInfo
from denver.automation.windows_manager import WindowManager


class TestWindowManager(unittest.TestCase):
    """Test suite for WindowManager and FakeWindowController."""

    def setUp(self) -> None:
        self.fake = FakeWindowController()

    def test_fake_minimize_maximize_restore_focus(self) -> None:
        """Verify fake window controller tracks window state changes."""
        res = self.fake.minimize_window("Notepad")
        self.assertTrue(res.success)
        self.assertEqual(res.data.get("state"), "minimized")

        res = self.fake.maximize_window("Notepad")
        self.assertTrue(res.success)
        self.assertEqual(res.data.get("state"), "maximized")

        res = self.fake.restore_window("Notepad")
        self.assertTrue(res.success)
        self.assertEqual(res.data.get("state"), "restored")

        res = self.fake.focus_window("Notepad")
        self.assertTrue(res.success)
        self.assertEqual(res.data.get("state"), "focused")

    def test_fake_show_desktop(self) -> None:
        """Verify fake show desktop."""
        res = self.fake.show_desktop()
        self.assertTrue(res.success)
        self.assertEqual(self.fake.state["desktop_shown"], True)

    def test_real_window_manager_with_fake_api(self) -> None:
        """Verify WindowManager handles empty window query gracefully."""
        mgr = WindowManager()
        res = mgr.minimize_window("")
        self.assertFalse(res.success)
        self.assertIn("WindowNotFound", str(res.error))


if __name__ == "__main__":
    unittest.main()
