"""Unit tests for WindowsAppScanner and apps.json catalog."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from denver.automation.apps_scanner import AppShortcut, WindowsAppScanner


class TestWindowsAppScanner(unittest.TestCase):
    """Test suite for Windows app discovery and catalog management."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_file = Path(self.temp_dir.name) / "test_apps.json"
        self.scanner = WindowsAppScanner(output_file=self.output_file)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_scan_creates_apps_json(self) -> None:
        """Verify scan_all populates and saves apps."""
        apps = self.scanner.scan_all()
        self.assertGreater(len(apps), 0)
        self.assertTrue(self.output_file.exists())

    def test_shortcut_matching(self) -> None:
        """Verify alias and name matching on AppShortcut."""
        shortcut = AppShortcut(
            name="Visual Studio Code",
            aliases=["vscode", "code", "coding editor"],
            type="executable",
            path="C:\\Program Files\\VSCode\\code.exe",
        )
        self.assertTrue(shortcut.matches("vscode"))
        self.assertTrue(shortcut.matches("coding editor"))
        self.assertTrue(shortcut.matches("Visual Studio Code"))
        self.assertFalse(shortcut.matches("spotify"))


if __name__ == "__main__":
    unittest.main()
