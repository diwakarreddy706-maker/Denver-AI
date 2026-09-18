"""Unit tests for Denver Automation Allowlist Registry."""

from __future__ import annotations

import unittest
from denver.automation.models import ApplicationTarget, BrowserTarget
from denver.automation.registry import AutomationRegistry


class TestAutomationRegistry(unittest.TestCase):
    """Test suite for allowlisted application and known website catalog registry."""

    def setUp(self) -> None:
        self.registry = AutomationRegistry()

    def test_default_applications_registered(self) -> None:
        """Verify standard Windows applications are pre-registered and allowlisted."""
        apps = self.registry.list_applications()
        app_ids = {a.app_id for a in apps}
        self.assertIn("notepad", app_ids)
        self.assertIn("calculator", app_ids)
        self.assertIn("explorer", app_ids)
        self.assertIn("task_manager", app_ids)
        self.assertIn("settings", app_ids)
        self.assertIn("cmd", app_ids)
        self.assertIn("browser", app_ids)

    def test_resolve_application_by_name_and_aliases(self) -> None:
        """Verify alias and fuzzy matching resolution for allowlisted apps."""
        calc = self.registry.get_application("calc")
        self.assertIsNotNone(calc)
        self.assertEqual(calc.app_id, "calculator")

        np = self.registry.get_application("text editor")
        self.assertIsNotNone(np)
        self.assertEqual(np.app_id, "notepad")

        exp = self.registry.get_application("file explorer")
        self.assertIsNotNone(exp)
        self.assertEqual(exp.app_id, "explorer")

    def test_unknown_application_returns_none(self) -> None:
        """Verify unallowlisted or malicious application identifiers return None."""
        self.assertIsNone(self.registry.get_application("malware.exe"))
        self.assertIsNone(self.registry.get_application("powershell_backdoor"))
        self.assertIsNone(self.registry.get_application("random_unregistered_app"))

    def test_register_custom_application(self) -> None:
        """Verify dynamic registration of safe applications."""
        target = ApplicationTarget(
            app_id="vlc",
            display_name="VLC Media Player",
            executable_name="vlc.exe",
            aliases=["vlc player", "media player"],
            is_allowlisted=True,
            category="media",
        )
        self.registry.register_application(target)
        resolved = self.registry.get_application("vlc player")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.app_id, "vlc")

    def test_duplicate_application_registration_rejected(self) -> None:
        """Verify duplicate registration of existing app_id raises ValueError."""
        dup = ApplicationTarget(
            app_id="notepad",
            display_name="Duplicate Notepad",
            executable_name="notepad.exe",
        )
        with self.assertRaises(ValueError):
            self.registry.register_application(dup)

    def test_known_sites_catalog(self) -> None:
        """Verify known website shortcuts resolve to secure HTTPS destinations."""
        yt = self.registry.get_known_site("youtube")
        self.assertIsNotNone(yt)
        self.assertEqual(yt.url, "https://www.youtube.com")

        gh = self.registry.get_known_site("github")
        self.assertIsNotNone(gh)
        self.assertEqual(gh.url, "https://www.github.com")

        gm = self.registry.get_known_site("gmail")
        self.assertIsNotNone(gm)
        self.assertEqual(gm.url, "https://mail.google.com")

    def test_register_custom_known_site(self) -> None:
        """Verify dynamic registration of known websites."""
        site = BrowserTarget(url="https://news.ycombinator.com", site_name="Hacker News", aliases=["hn", "hackernews"])
        self.registry.register_known_site(site)
        resolved = self.registry.get_known_site("hn")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.url, "https://news.ycombinator.com")


if __name__ == "__main__":
    unittest.main()
