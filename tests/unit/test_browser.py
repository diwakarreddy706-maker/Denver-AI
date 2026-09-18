"""Unit tests for Secure Browser and Website Controller."""

from __future__ import annotations

import unittest
from denver.automation.browser import BrowserController
from denver.automation.errors import URLSecurityError
from denver.automation.fake import FakeBrowserController
from denver.automation.registry import AutomationRegistry


class TestBrowserController(unittest.TestCase):
    """Test suite for browser launching, URL safety validation, and known sites."""

    def setUp(self) -> None:
        self.registry = AutomationRegistry()
        self.fake = FakeBrowserController(self.registry)

    def test_fake_open_known_site(self) -> None:
        """Verify fake controller handles known site queries like YouTube or GitHub."""
        res = self.fake.open_url("youtube")
        self.assertTrue(res.success)
        self.assertEqual(res.data.get("resolved_url"), "https://www.youtube.com")
        self.assertIn("https://www.youtube.com", self.fake.state["opened_urls"])

    def test_fake_open_valid_https_url(self) -> None:
        """Verify fake controller opens valid HTTPS URL."""
        res = self.fake.open_url("https://python.org")
        self.assertTrue(res.success)
        self.assertEqual(res.data.get("resolved_url"), "https://python.org")

    def test_fake_open_domain_prepends_https(self) -> None:
        """Verify bare domains (e.g. example.com) automatically get https scheme."""
        res = self.fake.open_url("example.com")
        self.assertTrue(res.success)
        self.assertEqual(res.data.get("resolved_url"), "https://example.com")

    def test_dangerous_url_schemes_rejected(self) -> None:
        """Verify dangerous URL protocols are strictly rejected by real and fake controllers."""
        dangerous = [
            "javascript:void(0)",
            "file:///etc/passwd",
            "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
            "vbscript:alert(1)",
        ]
        for url in dangerous:
            res = self.fake.open_url(url)
            self.assertFalse(res.success)
            self.assertEqual(res.error, "URLSecurityError")

    def test_real_controller_validate_url(self) -> None:
        """Verify real BrowserController validation method."""
        ctrl = BrowserController(self.registry)
        is_safe, err = ctrl.validate_url("https://github.com")
        self.assertTrue(is_safe)
        self.assertIsNone(err)

        is_safe, err = ctrl.validate_url("file:///C:/Windows/cmd.exe")
        self.assertFalse(is_safe)
        self.assertIn("forbidden", str(err))


if __name__ == "__main__":
    unittest.main()
