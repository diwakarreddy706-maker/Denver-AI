"""Safe Window Management for Denver Desktop Automation."""

from __future__ import annotations

from typing import Any

from denver.automation.models import AutomationResult, AutomationRisk, WindowInfo
from denver.automation.windows import (
    SW_MAXIMIZE,
    SW_MINIMIZE,
    SW_RESTORE,
    WindowsNativeAPI,
)
from denver.logging.logger import get_logger

logger = get_logger("automation.windows_manager")


class WindowManager:
    """Manages window state transitions and focus without hardcoded screen coordinates."""

    def __init__(self, native_api: WindowsNativeAPI | None = None) -> None:
        self.api = native_api or WindowsNativeAPI()

    def find_windows(self, query: str) -> list[WindowInfo]:
        """Search top-level visible windows by substring match against title."""
        if not self.api.is_available:
            return []
        q = query.strip().lower()
        if not q:
            return []
        all_windows = self.api.enumerate_windows()
        return [w for w in all_windows if q in w.title.lower()]

    def minimize_window(self, query: str) -> AutomationResult:
        """Minimize a target window by title match."""
        windows = self.find_windows(query)
        if not windows:
            return AutomationResult(
                success=False,
                action="minimize_window",
                target=query,
                message=f"No window found matching '{query}'.",
                risk_level=AutomationRisk.MEDIUM,
                error="WindowNotFound",
            )

        target = windows[0]
        ok = self.api.set_window_state(target.handle, SW_MINIMIZE)
        if ok:
            logger.info("Minimized window: '%s' (HWND: %s)", target.title, target.handle)
            return AutomationResult(
                success=True,
                action="minimize_window",
                target=target.title,
                message=f"Minimized window '{target.title}'.",
                data={"hwnd": target.handle, "title": target.title},
                risk_level=AutomationRisk.MEDIUM,
            )

        return AutomationResult(
            success=False,
            action="minimize_window",
            target=target.title,
            message=f"Failed to minimize window '{target.title}'.",
            risk_level=AutomationRisk.MEDIUM,
            error="SetWindowStateFailed",
        )

    def maximize_window(self, query: str) -> AutomationResult:
        """Maximize a target window by title match."""
        windows = self.find_windows(query)
        if not windows:
            return AutomationResult(
                success=False,
                action="maximize_window",
                target=query,
                message=f"No window found matching '{query}'.",
                risk_level=AutomationRisk.MEDIUM,
                error="WindowNotFound",
            )

        target = windows[0]
        ok = self.api.set_window_state(target.handle, SW_MAXIMIZE)
        if ok:
            logger.info("Maximized window: '%s' (HWND: %s)", target.title, target.handle)
            return AutomationResult(
                success=True,
                action="maximize_window",
                target=target.title,
                message=f"Maximized window '{target.title}'.",
                data={"hwnd": target.handle, "title": target.title},
                risk_level=AutomationRisk.MEDIUM,
            )

        return AutomationResult(
            success=False,
            action="maximize_window",
            target=target.title,
            message=f"Failed to maximize window '{target.title}'.",
            risk_level=AutomationRisk.MEDIUM,
            error="SetWindowStateFailed",
        )

    def restore_window(self, query: str) -> AutomationResult:
        """Restore a minimized or maximized window to standard layout."""
        windows = self.find_windows(query)
        if not windows:
            return AutomationResult(
                success=False,
                action="restore_window",
                target=query,
                message=f"No window found matching '{query}'.",
                risk_level=AutomationRisk.MEDIUM,
                error="WindowNotFound",
            )

        target = windows[0]
        ok = self.api.set_window_state(target.handle, SW_RESTORE)
        if ok:
            logger.info("Restored window: '%s' (HWND: %s)", target.title, target.handle)
            return AutomationResult(
                success=True,
                action="restore_window",
                target=target.title,
                message=f"Restored window '{target.title}'.",
                data={"hwnd": target.handle, "title": target.title},
                risk_level=AutomationRisk.MEDIUM,
            )

        return AutomationResult(
            success=False,
            action="restore_window",
            target=target.title,
            message=f"Failed to restore window '{target.title}'.",
            risk_level=AutomationRisk.MEDIUM,
            error="SetWindowStateFailed",
        )

    def focus_window(self, query: str) -> AutomationResult:
        """Bring a target window to foreground."""
        windows = self.find_windows(query)
        if not windows:
            return AutomationResult(
                success=False,
                action="focus_window",
                target=query,
                message=f"No window found matching '{query}'.",
                risk_level=AutomationRisk.MEDIUM,
                error="WindowNotFound",
            )

        target = windows[0]
        ok = self.api.focus_window(target.handle)
        if ok:
            logger.info("Focused window: '%s' (HWND: %s)", target.title, target.handle)
            return AutomationResult(
                success=True,
                action="focus_window",
                target=target.title,
                message=f"Focused window '{target.title}'.",
                data={"hwnd": target.handle, "title": target.title},
                risk_level=AutomationRisk.MEDIUM,
            )

        return AutomationResult(
            success=False,
            action="focus_window",
            target=target.title,
            message=f"Failed to focus window '{target.title}'.",
            risk_level=AutomationRisk.MEDIUM,
            error="FocusWindowFailed",
        )

    def show_desktop(self) -> AutomationResult:
        """Minimize all windows to expose the desktop."""
        ok = self.api.minimize_all_windows()
        if ok:
            return AutomationResult(
                success=True,
                action="show_desktop",
                message="Showing desktop.",
                risk_level=AutomationRisk.MEDIUM,
            )
        return AutomationResult(
            success=False,
            action="show_desktop",
            message="Could not show desktop.",
            risk_level=AutomationRisk.MEDIUM,
            error="ShowDesktopFailed",
        )
