"""Global Push-to-Talk (PTT) Hotkey Controller for Denver AI Assistant.

Provides system-wide Windows hotkey registration via ctypes user32.RegisterHotKey,
enabling instant voice command activation from any application without wake words.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import sys
import threading
from collections.abc import Callable
from typing import Any

from denver.logging.logger import get_logger

logger = get_logger("audio.push_to_talk")

# Windows Virtual Keys and Modifier Constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

# Key name to Windows Virtual Key mapping
KEY_MAP: dict[str, int] = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "escape": 0x1B,
    "esc": 0x1B,
    "tab": 0x09,
    "backspace": 0x08,
    "capslock": 0x14,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
}

# F1 - F12
for i in range(1, 13):
    KEY_MAP[f"f{i}"] = 0x70 + (i - 1)


def parse_hotkey_string(hotkey_str: str) -> tuple[int, int]:
    """Parse hotkey description like 'ctrl+space', 'alt+d', 'ctrl+shift+f1' into (modifiers, vk_code)."""
    parts = [p.strip().lower() for p in hotkey_str.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"Invalid hotkey specification: '{hotkey_str}'")

    modifiers = MOD_NOREPEAT
    vk_code = 0

    for part in parts:
        if part in ("ctrl", "control"):
            modifiers |= MOD_CONTROL
        elif part == "alt":
            modifiers |= MOD_ALT
        elif part == "shift":
            modifiers |= MOD_SHIFT
        elif part in ("win", "windows", "super", "cmd"):
            modifiers |= MOD_WIN
        elif part in KEY_MAP:
            vk_code = KEY_MAP[part]
        elif len(part) == 1 and (part.isalnum()):
            vk_code = ord(part.upper())
        else:
            raise ValueError(f"Unknown key in hotkey: '{part}'")

    if vk_code == 0:
        raise ValueError(f"No valid non-modifier key specified in hotkey: '{hotkey_str}'")

    return modifiers, vk_code


class PushToTalkListener:
    """Windows Global Hotkey Listener managing background message pump and callback execution."""

    def __init__(
        self,
        hotkey: str = "ctrl+space",
        on_trigger: Callable[[], Any] | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self.hotkey_str = hotkey
        self.on_trigger = on_trigger
        self.loop = loop
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._is_running = False
        self._hotkey_id = 101
        self._registered = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self) -> bool:
        """Start listening for the global hotkey in a background thread."""
        if self._is_running:
            return True

        if sys.platform != "win32":
            logger.info("Non-Windows platform detected; Push-to-Talk running in software-trigger mode.")
            self._is_running = True
            return True

        try:
            modifiers, vk = parse_hotkey_string(self.hotkey_str)
        except Exception as exc:
            logger.warning("Could not parse Push-to-Talk hotkey '%s': %s", self.hotkey_str, exc)
            return False

        ready_event = threading.Event()
        self._is_running = True
        self._thread = threading.Thread(
            target=self._hotkey_worker,
            args=(modifiers, vk, ready_event),
            daemon=True,
            name="DenverPushToTalkThread",
        )
        self._thread.start()
        ready_event.wait(timeout=2.0)
        return self._registered

    def stop(self) -> None:
        """Stop the background listener thread and unregister the hotkey."""
        if not self._is_running:
            return

        self._is_running = False
        if sys.platform == "win32" and self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(
                    self._thread_id,
                    WM_QUIT,
                    0,
                    0,
                )
            except Exception as exc:
                logger.debug("Error posting WM_QUIT to PTT thread: %s", exc)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        self._registered = False
        logger.info("Push-to-Talk listener stopped.")

    def trigger(self) -> None:
        """Manually trigger the Push-to-Talk action."""
        logger.info("Push-to-Talk triggered ('%s')", self.hotkey_str)
        if not self.on_trigger:
            return

        try:
            result = self.on_trigger()
            if asyncio.iscoroutine(result):
                if self.loop and self.loop.is_running():
                    asyncio.run_coroutine_threadsafe(result, self.loop)
                else:
                    try:
                        cur_loop = asyncio.get_running_loop()
                        cur_loop.create_task(result)
                    except RuntimeError:
                        asyncio.run(result)
        except Exception as exc:
            logger.error("Error executing Push-to-Talk callback: %s", exc)

    def _hotkey_worker(self, modifiers: int, vk: int, ready_event: threading.Event) -> None:
        """Windows message pump thread registering the global hotkey."""
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        user32 = ctypes.windll.user32

        success = user32.RegisterHotKey(
            None,
            self._hotkey_id,
            modifiers,
            vk,
        )

        if not success:
            last_err = ctypes.windll.kernel32.GetLastError()
            logger.warning(
                "Failed to register global hotkey '%s' (Error %d). Key combination may be reserved by another app.",
                self.hotkey_str,
                last_err,
            )
            self._registered = False
            ready_event.set()
            return

        self._registered = True
        logger.info("Global Push-to-Talk hotkey registered: '%s'", self.hotkey_str)
        ready_event.set()

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p),
                ("message", ctypes.c_uint),
                ("wParam", ctypes.c_void_p),
                ("lParam", ctypes.c_void_p),
                ("time", ctypes.c_ulong),
                ("pt_x", ctypes.c_long),
                ("pt_y", ctypes.c_long),
            ]

        msg = MSG()
        try:
            while self._is_running:
                res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if res == 0 or res == -1:
                    break

                if msg.message == WM_HOTKEY and msg.wParam == self._hotkey_id:
                    self.trigger()

                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            user32.UnregisterHotKey(None, self._hotkey_id)
            self._registered = False
