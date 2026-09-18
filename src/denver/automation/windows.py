"""Windows Native API Abstractions via ctypes for Denver Desktop Automation."""

from __future__ import annotations

import ctypes
import platform
import subprocess
from ctypes import wintypes
from typing import Callable

from denver.automation.models import WindowInfo
from denver.logging.logger import get_logger

logger = get_logger("automation.windows")

_IS_WINDOWS = platform.system() == "Windows"

# Window Show Commands (Win32)
SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_MAXIMIZE = 3
SW_SHOWNOACTIVATE = 4
SW_SHOW = 5
SW_MINIMIZE = 6
SW_SHOWMINNOACTIVE = 7
SW_SHOWNA = 8
SW_RESTORE = 9

# Virtual-Key Codes for Multimedia / Volume
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
KEYEVENTF_KEYUP = 0x0002

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class WindowsNativeAPI:
    """Encapsulates safe, non-destructive Win32 system calls using ctypes."""

    def __init__(self) -> None:
        if _IS_WINDOWS:
            self._user32 = ctypes.windll.user32
            self._kernel32 = ctypes.windll.kernel32
        else:
            self._user32 = None
            self._kernel32 = None

    @property
    def is_available(self) -> bool:
        return bool(_IS_WINDOWS and self._user32)

    def enumerate_windows(self) -> list[WindowInfo]:
        """Scan top-level visible desktop windows."""
        if not self.is_available:
            return []

        windows: list[WindowInfo] = []

        def _enum_callback(hwnd: int, lparam: int) -> bool:
            if not self._user32.IsWindowVisible(hwnd):
                return True

            length = self._user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True

            buff = ctypes.create_unicode_buffer(length + 1)
            self._user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip()

            if not title:
                return True

            pid = wintypes.DWORD()
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            is_min = bool(self._user32.IsIconic(hwnd))
            is_max = bool(self._user32.IsZoomed(hwnd))

            windows.append(
                WindowInfo(
                    handle=hwnd,
                    title=title,
                    process_id=pid.value,
                    process_name="",
                    is_visible=True,
                    is_minimized=is_min,
                    is_maximized=is_max,
                )
            )
            return True

        cb = WNDENUMPROC(_enum_callback)
        self._user32.EnumWindows(cb, 0)
        return windows

    def set_window_state(self, hwnd: int, command: int) -> bool:
        """Modify window display state (minimize, maximize, restore)."""
        if not self.is_available or not hwnd:
            return False
        try:
            return bool(self._user32.ShowWindow(hwnd, command))
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to set window state for hwnd %s: %s", hwnd, exc)
            return False

    def focus_window(self, hwnd: int) -> bool:
        """Bring window to foreground and assign input focus."""
        if not self.is_available or not hwnd:
            return False
        try:
            self._user32.ShowWindow(hwnd, SW_RESTORE)
            return bool(self._user32.SetForegroundWindow(hwnd))
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to focus window hwnd %s: %s", hwnd, exc)
            return False

    def minimize_all_windows(self) -> bool:
        """Simulate Win+D / Minimize all windows to show desktop."""
        if not self.is_available:
            return False
        try:
            # Post command to desktop or toggle
            self._user32.keybd_event(0x5B, 0, 0, 0)  # Left Win Key Down
            self._user32.keybd_event(0x44, 0, 0, 0)  # 'D' Key Down
            self._user32.keybd_event(0x44, 0, KEYEVENTF_KEYUP, 0)  # 'D' Key Up
            self._user32.keybd_event(0x5B, 0, KEYEVENTF_KEYUP, 0)  # Win Key Up
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to show desktop: %s", exc)
            return False

    def send_volume_key(self, vk_code: int, times: int = 1) -> bool:
        """Dispatch hardware multimedia key event for volume manipulation."""
        if not self.is_available:
            return False
        try:
            for _ in range(max(1, times)):
                self._user32.keybd_event(vk_code, 0, 0, 0)
                self._user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to send volume key event: %s", exc)
            return False

    def lock_workstation(self) -> bool:
        """Lock the active Windows desktop session."""
        if not self.is_available:
            return False
        try:
            logger.info("Executing Windows workstation lock (LockWorkStation).")
            return bool(self._user32.LockWorkStation())
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to execute LockWorkStation: %s", exc)
            return False
