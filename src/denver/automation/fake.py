"""Deterministic Fake Test Doubles for Denver Desktop Automation Subsystems."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from denver.automation.applications import ApplicationController
from denver.automation.browser import BrowserController
from denver.automation.confirmation import ConfirmationManager
from denver.automation.models import (
    ApplicationTarget,
    AutomationResult,
    AutomationRisk,
    ScreenshotResult,
    WindowInfo,
)
from denver.automation.registry import AutomationRegistry
from denver.automation.screenshot import ScreenshotController
from denver.automation.system import SystemController
from denver.automation.volume import VolumeController
from denver.automation.windows_manager import WindowManager


class FakeApplicationController(ApplicationController):
    """Deterministic application controller test double."""

    def __init__(self, registry: AutomationRegistry | None = None) -> None:
        super().__init__(registry or AutomationRegistry())
        self.launched_apps: list[str] = []
        self.closed_apps: list[str] = []
        self.should_fail = False

    @property
    def state(self) -> dict[str, Any]:
        return {
            "launched_apps": self.launched_apps,
            "closed_apps": self.closed_apps,
        }

    def launch(self, app_query: str) -> AutomationResult:
        app = self.registry.find_application(app_query)
        if not app:
            return AutomationResult(
                success=False,
                action="open_application",
                target=app_query,
                message=f"Application '{app_query}' is not in allowlist.",
                risk_level=AutomationRisk.LOW,
                error="ApplicationNotFound",
            )

        if self.should_fail:
            return AutomationResult(
                success=False,
                action="open_application",
                target=app.display_name,
                message=f"Simulated launch failure for {app.display_name}.",
                risk_level=AutomationRisk.LOW,
                error="SimulatedFailure",
            )

        self.launched_apps.append(app.app_id)
        return AutomationResult(
            success=True,
            action="open_application",
            target=app.display_name,
            message=f"Opened {app.display_name}.",
            data={"app_id": app.app_id, "pid": 12345},
            risk_level=AutomationRisk.LOW,
        )

    def close(self, app_query: str) -> AutomationResult:
        app = self.registry.find_application(app_query)
        if not app:
            return AutomationResult(
                success=False,
                action="close_application",
                target=app_query,
                message=f"Application '{app_query}' is not in allowlist.",
                risk_level=AutomationRisk.MEDIUM,
                error="ApplicationNotFound",
            )

        if app.app_id in self.launched_apps:
            self.launched_apps.remove(app.app_id)
        self.closed_apps.append(app.app_id)
        return AutomationResult(
            success=True,
            action="close_application",
            target=app.display_name,
            message=f"Closed {app.display_name}.",
            data={"app_id": app.app_id, "terminated_instances": 1},
            risk_level=AutomationRisk.MEDIUM,
        )


class FakeWindowController(WindowManager):
    """Deterministic window manager test double."""

    def __init__(self) -> None:
        super().__init__()
        self.minimized_windows: list[str] = []
        self.maximized_windows: list[str] = []
        self.restored_windows: list[str] = []
        self.focused_windows: list[str] = []
        self.desktop_shown = False
        self.active_windows = [
            WindowInfo(handle=1001, title="Untitled - Notepad", process_id=5001, process_name="notepad.exe"),
            WindowInfo(handle=1002, title="Calculator", process_id=5002, process_name="calc.exe"),
        ]

    @property
    def state(self) -> dict[str, Any]:
        return {
            "minimized": self.minimized_windows,
            "maximized": self.maximized_windows,
            "restored": self.restored_windows,
            "focused": self.focused_windows,
            "desktop_shown": self.desktop_shown,
        }

    def find_windows(self, query: str) -> list[WindowInfo]:
        q = query.strip().lower()
        return [w for w in self.active_windows if q in w.title.lower()]

    def minimize_window(self, query: str) -> AutomationResult:
        wins = self.find_windows(query)
        if not wins:
            return AutomationResult(success=False, action="minimize_window", target=query, error="WindowNotFound")
        self.minimized_windows.append(wins[0].title)
        return AutomationResult(
            success=True,
            action="minimize_window",
            target=wins[0].title,
            message=f"Minimized {wins[0].title}.",
            data={"state": "minimized"},
        )

    def maximize_window(self, query: str) -> AutomationResult:
        wins = self.find_windows(query)
        if not wins:
            return AutomationResult(success=False, action="maximize_window", target=query, error="WindowNotFound")
        self.maximized_windows.append(wins[0].title)
        return AutomationResult(
            success=True,
            action="maximize_window",
            target=wins[0].title,
            message=f"Maximized {wins[0].title}.",
            data={"state": "maximized"},
        )

    def restore_window(self, query: str) -> AutomationResult:
        wins = self.find_windows(query)
        if not wins:
            return AutomationResult(success=False, action="restore_window", target=query, error="WindowNotFound")
        self.restored_windows.append(wins[0].title)
        return AutomationResult(
            success=True,
            action="restore_window",
            target=wins[0].title,
            message=f"Restored {wins[0].title}.",
            data={"state": "restored"},
        )

    def focus_window(self, query: str) -> AutomationResult:
        wins = self.find_windows(query)
        if not wins:
            return AutomationResult(success=False, action="focus_window", target=query, error="WindowNotFound")
        self.focused_windows.append(wins[0].title)
        return AutomationResult(
            success=True,
            action="focus_window",
            target=wins[0].title,
            message=f"Focused {wins[0].title}.",
            data={"state": "focused"},
        )

    def show_desktop(self) -> AutomationResult:
        self.desktop_shown = True
        return AutomationResult(success=True, action="show_desktop", message="Showing desktop.")


class FakeVolumeController(VolumeController):
    """Deterministic volume controller test double."""

    def __init__(self, initial_volume: int = 50, initial_muted: bool = False) -> None:
        super().__init__()
        self.current_volume = initial_volume
        self.is_muted = initial_muted

    @property
    def state(self) -> dict[str, Any]:
        return {
            "volume": self.current_volume,
            "muted": self.is_muted,
        }

    def get_volume(self) -> AutomationResult:
        return AutomationResult(
            success=True,
            action="get_volume",
            message=f"Volume is at {self.current_volume}%.",
            data={"volume": self.current_volume, "approx_volume": self.current_volume, "is_muted": self.is_muted},
        )

    def set_volume(self, value_pct: int) -> AutomationResult:
        self.current_volume = max(0, min(100, int(value_pct)))
        return AutomationResult(
            success=True,
            action="set_volume",
            message=f"Volume set to {self.current_volume} percent.",
            data={"volume": self.current_volume},
        )

    def increase_volume(self, step: int = 10) -> AutomationResult:
        self.current_volume = min(100, self.current_volume + step)
        return AutomationResult(
            success=True,
            action="increase_volume",
            message=f"Increased volume to {self.current_volume}%.",
            data={"step": step, "volume": self.current_volume, "approx_volume": self.current_volume},
        )

    def decrease_volume(self, step: int = 10) -> AutomationResult:
        self.current_volume = max(0, self.current_volume - step)
        return AutomationResult(
            success=True,
            action="decrease_volume",
            message=f"Decreased volume to {self.current_volume}%.",
            data={"step": step, "volume": self.current_volume, "approx_volume": self.current_volume},
        )

    def mute(self) -> AutomationResult:
        self.is_muted = True
        return AutomationResult(
            success=True,
            action="mute_volume",
            message="Muted audio.",
            data={"is_muted": True},
        )

    def unmute(self) -> AutomationResult:
        self.is_muted = False
        return AutomationResult(
            success=True,
            action="unmute_volume",
            message="Unmuted audio.",
            data={"is_muted": False},
        )


class FakeBrowserController(BrowserController):
    """Deterministic browser controller test double."""

    def __init__(self, registry: AutomationRegistry | None = None) -> None:
        super().__init__(registry or AutomationRegistry())
        self.opened_urls: list[str] = []

    @property
    def state(self) -> dict[str, Any]:
        return {
            "opened_urls": self.opened_urls,
        }

    def open_url(self, target: str) -> AutomationResult:
        target_str = target.strip()
        # Check security violations
        for forbidden in ["javascript:", "data:", "file:", "vbscript:"]:
            if forbidden in target_str.lower():
                return AutomationResult(
                    success=False,
                    action="open_browser",
                    target=target_str,
                    message=f"Security violation: {forbidden}",
                    error="URLSecurityError",
                )

        site = self.registry.get_known_site(target_str)
        if site:
            dest = site.url
        elif target_str.startswith("http://") or target_str.startswith("https://"):
            dest = target_str
        else:
            dest = f"https://{target_str}"

        self.opened_urls.append(dest)
        return AutomationResult(
            success=True,
            action="open_browser",
            target=dest,
            message=f"Opened {dest}.",
            data={"url": dest, "resolved_url": dest},
        )


class FakeScreenshotController(ScreenshotController):
    """Deterministic screenshot test double."""

    def __init__(self, output_dir: Path | str = "data/screenshots", screenshot_dir: Path | str | None = None) -> None:
        chosen_dir = screenshot_dir if screenshot_dir is not None else output_dir
        super().__init__(chosen_dir)
        self.captured_files: list[str] = []

    @property
    def state(self) -> dict[str, Any]:
        return {
            "captured": self.captured_files,
        }

    def capture(self, custom_name: str | None = None) -> AutomationResult:
        target_file = self._generate_safe_filepath(custom_name)
        self.captured_files.append(str(target_file))
        res = ScreenshotResult(
            file_path=target_file,
            file_size_bytes=1024,
            width=1920,
            height=1080,
            format="PNG",
        )
        return AutomationResult(
            success=True,
            action="take_screenshot",
            target=str(target_file),
            message=f"Screenshot captured: {target_file.name}",
            data=res.to_dict(),
            risk_level=AutomationRisk.MEDIUM,
        )


class FakeSystemController(SystemController):
    """Deterministic system controller test double."""

    def __init__(self) -> None:
        super().__init__()
        self.locked = False

    @property
    def state(self) -> dict[str, Any]:
        return {
            "workstation_locked": self.locked,
        }

    def get_system_summary(self) -> AutomationResult:
        return AutomationResult(
            success=True,
            action="get_system_summary",
            message="System is operating smoothly.",
            data={"cpu_percent": 15.0, "ram_percent": 45.0, "os": "Windows", "hostname": "TEST-PC"},
            risk_level=AutomationRisk.LOW,
        )

    def lock_workstation(self) -> AutomationResult:
        self.locked = True
        return AutomationResult(
            success=True,
            action="lock_workstation",
            message="Workstation locked successfully.",
            risk_level=AutomationRisk.HIGH,
        )
