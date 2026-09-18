"""Unit tests for Denver Desktop Automation Models and Typed Contracts."""

from __future__ import annotations

import unittest
from denver.automation.models import (
    ApplicationTarget,
    AutomationAction,
    AutomationRequest,
    AutomationResult,
    AutomationRisk,
    BrowserTarget,
    ConfirmationRequirement,
    ScreenshotResult,
    VolumeCommand,
    WindowInfo,
    WindowTarget,
)


class TestAutomationModels(unittest.TestCase):
    """Test suite for typed automation request, result, and target contracts."""

    def test_automation_risk_enum_values(self) -> None:
        """Verify risk classifications are defined."""
        self.assertEqual(AutomationRisk.LOW.value, "LOW")
        self.assertEqual(AutomationRisk.MEDIUM.value, "MEDIUM")
        self.assertEqual(AutomationRisk.HIGH.value, "HIGH")
        self.assertEqual(AutomationRisk.BLOCKED.value, "BLOCKED")

    def test_application_target_defaults(self) -> None:
        """Verify application target model properties."""
        target = ApplicationTarget(
            app_id="calc",
            display_name="Calculator",
            executable_name="calc.exe",
            is_allowlisted=True,
            category="utility",
        )
        self.assertEqual(target.app_id, "calc")
        self.assertTrue(target.is_allowlisted)
        d = target.to_dict()
        self.assertEqual(d["app_id"], "calc")
        self.assertEqual(d["display_name"], "Calculator")

    def test_window_info_and_target(self) -> None:
        """Verify window info and target models."""
        info = WindowInfo(hwnd=12345, title="Untitled - Notepad", process_name="notepad.exe", is_visible=True)
        self.assertEqual(info.hwnd, 12345)
        self.assertEqual(info.title, "Untitled - Notepad")
        d = info.to_dict()
        self.assertEqual(d["process_name"], "notepad.exe")

        target = WindowTarget(title_query="notepad", operation="minimize")
        self.assertEqual(target.operation, "minimize")

    def test_volume_command_model(self) -> None:
        """Verify volume command model."""
        cmd = VolumeCommand(action="set", level_percent=75, step_percent=10)
        self.assertEqual(cmd.action, "set")
        self.assertEqual(cmd.level_percent, 75)
        d = cmd.to_dict()
        self.assertEqual(d["level_percent"], 75)

    def test_browser_target_model(self) -> None:
        """Verify browser target model."""
        target = BrowserTarget(url="https://youtube.com", site_name="YouTube", is_allowlisted=True)
        self.assertEqual(target.url, "https://youtube.com")
        self.assertTrue(target.is_allowlisted)

    def test_screenshot_result_model(self) -> None:
        """Verify screenshot result model."""
        res = ScreenshotResult(file_path="data/screenshots/screen_1.png", file_size_bytes=1024, width=1920, height=1080)
        self.assertEqual(res.width, 1920)
        self.assertEqual(res.height, 1080)
        d = res.to_dict()
        self.assertEqual(d["file_size_bytes"], 1024)

    def test_automation_action_and_request_result(self) -> None:
        """Verify action definition and execution request/result models."""
        action = AutomationAction(
            action_id="act_calc",
            action_type="open_application",
            target="calculator",
            risk_level=AutomationRisk.LOW,
            requires_confirmation=False,
            description="Opens Calculator",
        )
        self.assertEqual(action.action_id, "act_calc")
        self.assertFalse(action.requires_confirmation)

        req = AutomationRequest(
            action_name="open_application",
            target="notepad",
            params={"application": "notepad"},
        )
        self.assertEqual(req.action_name, "open_application")
        self.assertEqual(req.target, "notepad")

        res = AutomationResult(
            success=True,
            action="open_application",
            target="notepad",
            message="Notepad opened successfully.",
            data={"pid": 999},
        )
        self.assertTrue(res.success)
        d = res.to_dict()
        self.assertEqual(d["action"], "open_application")
        self.assertEqual(d["message"], "Notepad opened successfully.")


if __name__ == "__main__":
    unittest.main()
