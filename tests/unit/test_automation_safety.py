"""Unit tests for Phase 5 Desktop Automation Safety Enforcement."""

from __future__ import annotations

import unittest
from denver.automation.errors import ApplicationNotFoundError, PathTraversalError, URLSecurityError
from denver.automation.registry import AutomationRegistry
from denver.commands.models import ActionRequest, CommandRiskLevel
from denver.commands.safety import SafetyValidator


class TestAutomationSafety(unittest.TestCase):
    """Rigorous security test suite ensuring no arbitrary OS commands or injections execute."""

    def setUp(self) -> None:
        self.validator = SafetyValidator(allow_destructive_actions=False)
        self.registry = AutomationRegistry()

    def test_arbitrary_executable_path_rejected(self) -> None:
        """Verify arbitrary file paths in application parameters are rejected."""
        malicious_paths = [
            "C:\\Windows\\System32\\cmd.exe /c calc",
            "C:\\Users\\Public\\malware.exe",
            "powershell.exe -ExecutionPolicy Bypass",
            "../../etc/passwd",
            "\\\\attacker-server\\share\\exploit.exe",
        ]
        for path in malicious_paths:
            req = ActionRequest(
                action_name="open_application",
                params={"application": path},
                risk_level=CommandRiskLevel.LOW,
            )
            is_safe, err = self.validator.validate(req)
            self.assertFalse(is_safe, f"Path was not caught by safety validator: {path}")

    def test_url_scheme_security_enforcement(self) -> None:
        """Verify dangerous URL protocols (file, javascript, data, vbscript) are blocked."""
        dangerous_urls = [
            "javascript:alert(document.cookie)",
            "file:///C:/Windows/System32/cmd.exe",
            "data:text/html,<script>alert(1)</script>",
            "vbscript:msgbox(1)",
            "powershell:Start-Process calc",
        ]
        for url in dangerous_urls:
            is_valid, err = self.validator.validate_url(url)
            self.assertFalse(is_valid, f"Dangerous URL scheme was not blocked: {url}")
            self.assertIsNotNone(err)

    def test_allowlist_registry_blocks_unknown_apps(self) -> None:
        """Verify application registry strictly rejects unallowlisted binaries."""
        self.assertIsNone(self.registry.get_application("powershell.exe"))
        self.assertIsNone(self.registry.get_application("regedit.exe"))
        self.assertIsNone(self.registry.get_application("format.com"))

    def test_url_command_injection_rejected(self) -> None:
        """Verify URL string command injection attempts are blocked."""
        injection_urls = [
            "https://google.com; cmd.exe /c calc",
            "https://youtube.com | powershell -enc abc",
            "https://example.com && format c:",
        ]
        for url in injection_urls:
            req = ActionRequest(
                action_name="open_browser",
                params={"url": url},
                risk_level=CommandRiskLevel.LOW,
            )
            is_safe, err = self.validator.validate(req)
            self.assertFalse(is_safe, f"Injection URL was not blocked: {url}")


if __name__ == "__main__":
    unittest.main()
