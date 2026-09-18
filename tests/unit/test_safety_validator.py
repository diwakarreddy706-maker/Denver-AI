"""Unit tests for SafetyValidator."""

from __future__ import annotations

import unittest
from denver.commands.models import ActionRequest, CommandRiskLevel
from denver.commands.safety import SafetyValidator


class TestSafetyValidator(unittest.TestCase):
    """Test suite for safety gates, dangerous command rejection, and URL checks."""

    def setUp(self) -> None:
        self.validator = SafetyValidator(allow_destructive_actions=False)

    def test_safe_action_passes(self) -> None:
        """Verify safe read-only actions pass without violations."""
        req = ActionRequest(action_name="get_time", params={}, risk_level=CommandRiskLevel.SAFE)
        is_safe, err = self.validator.validate(req)
        self.assertTrue(is_safe)
        self.assertIsNone(err)

    def test_dangerous_shell_injection_blocked(self) -> None:
        """CRITICAL SECURITY TEST: Verify dangerous shell commands are intercepted."""
        dangerous_payloads = [
            "cmd.exe /c format c:",
            "powershell -enc aGVsbG8=",
            "bash -c 'rm -rf /'",
            "eval('import os; os.system(\"calc\")')",
            "del /f /q C:\\Windows",
            "vssadmin delete shadows",
        ]
        for payload in dangerous_payloads:
            req = ActionRequest(
                action_name="open_application",
                params={"application": payload},
                risk_level=CommandRiskLevel.LOW,
            )
            is_safe, err = self.validator.validate(req)
            self.assertFalse(is_safe, f"Payload was not blocked: {payload}")
            self.assertIsNotNone(err)

    def test_directory_traversal_blocked(self) -> None:
        """Verify directory traversal attempts are blocked."""
        req = ActionRequest(
            action_name="open_application",
            params={"path": "../../Windows/System32/calc.exe"},
            risk_level=CommandRiskLevel.LOW,
        )
        is_safe, err = self.validator.validate(req)
        self.assertFalse(is_safe)
        self.assertIn("Directory traversal", str(err))

    def test_url_scheme_validation(self) -> None:
        """Verify only http/https schemes are allowed for URL parameters."""
        valid_req = ActionRequest(
            action_name="open_web",
            params={"url": "https://github.com"},
            risk_level=CommandRiskLevel.LOW,
        )
        is_safe, _ = self.validator.validate(valid_req)
        self.assertTrue(is_safe)

        invalid_schemes = [
            "file:///C:/Windows/System32/cmd.exe",
            "javascript:alert(1)",
            "ms-settings:privacy",
            "shell:startup",
        ]
        for bad_url in invalid_schemes:
            req = ActionRequest(
                action_name="open_web",
                params={"url": bad_url},
                risk_level=CommandRiskLevel.LOW,
            )
            is_safe, err = self.validator.validate(req)
            self.assertFalse(is_safe, f"Bad URL was not blocked: {bad_url}")

    def test_blocked_risk_level_rejected(self) -> None:
        """Verify actions classified as BLOCKED fail automatically."""
        req = ActionRequest(action_name="unauthorized_op", params={}, risk_level=CommandRiskLevel.BLOCKED)
        is_safe, err = self.validator.validate(req)
        self.assertFalse(is_safe)
        self.assertIn("BLOCKED", str(err))

    def test_destructive_action_requires_confirmation(self) -> None:
        """Verify actions requiring confirmation are blocked when allow_destructive is False."""
        req = ActionRequest(
            action_name="shutdown",
            params={},
            risk_level=CommandRiskLevel.HIGH,
            requires_confirmation=True,
        )
        # Blocked when allow_destructive_actions = False
        is_safe, err = self.validator.validate(req, allow_destructive=False)
        self.assertFalse(is_safe)
        self.assertIn("confirmation", str(err))

        # Allowed when explicitly confirmed
        is_safe_confirmed, _ = self.validator.validate(req, allow_destructive=True)
        self.assertTrue(is_safe_confirmed)


if __name__ == "__main__":
    unittest.main()
