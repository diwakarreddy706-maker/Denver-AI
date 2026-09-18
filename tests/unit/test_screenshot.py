"""Unit tests for Screenshot Capture and Filesystem Containment."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from denver.automation.errors import PathTraversalError
from denver.automation.fake import FakeScreenshotController
from denver.automation.screenshot import ScreenshotController


class TestScreenshotController(unittest.TestCase):
    """Test suite for screenshot capture and strict directory path containment."""

    def test_fake_screenshot_capture(self) -> None:
        """Verify fake controller produces simulated screenshot metadata inside approved directory."""
        fake = FakeScreenshotController(screenshot_dir="data/screenshots")
        res = fake.capture("test_shot.png")
        self.assertTrue(res.success)
        self.assertIn("screenshots", res.data.get("file_path"))
        self.assertEqual(res.data.get("width"), 1920)
        self.assertEqual(res.data.get("height"), 1080)
        self.assertEqual(len(fake.state["captured"]), 1)

    def test_real_screenshot_rejects_path_traversal(self) -> None:
        """Verify screenshot controller prevents directory traversal attempts."""
        with tempfile.TemporaryDirectory() as tmp:
            ctrl = ScreenshotController(screenshot_dir=tmp)
            res = ctrl.capture("../../evil.png")
            self.assertFalse(res.success)
            self.assertEqual(res.error, "PathTraversalError")

    def test_real_screenshot_rejects_absolute_path_escape(self) -> None:
        """Verify screenshot controller rejects filenames attempting to escape into root or other drives."""
        with tempfile.TemporaryDirectory() as tmp:
            ctrl = ScreenshotController(screenshot_dir=tmp)
            res = ctrl.capture("C:/Windows/System32/hacked.png")
            # If C: path escapes tmp directory, must be blocked
            if not str(Path("C:/Windows/System32/hacked.png").resolve()).startswith(str(Path(tmp).resolve())):
                self.assertFalse(res.success)
                self.assertEqual(res.error, "PathTraversalError")


if __name__ == "__main__":
    unittest.main()
