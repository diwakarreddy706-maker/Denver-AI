"""Global Hotkey Manager for Denver Desktop Automation.

Provides unified, system-wide Windows hotkey registration via ctypes user32.RegisterHotKey,
supporting multiple hotkeys on a single message pump with mandatory audio/visual disclosure.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from denver.audio.push_to_talk import KEY_MAP, parse_hotkey_string
from denver.logging.logger import get_logger
from denver.runtime.event_bus import DenverEventBus, get_event_bus
from denver.runtime.events import DenverEvent

logger = get_logger("automation.hotkey")

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


@dataclass(frozen=True)
class ScreenCaptureTriggered(DenverEvent):
    """Event published whenever a screen capture is triggered via hotkey or GUI."""

    source: str = "hotkey"
    hotkey: str = "ctrl+alt+s"
    event_name: str = "screen.capture_triggered"


@dataclass
class RegisteredHotkey:
    name: str
    hotkey_str: str
    modifiers: int
    vk_code: int
    hotkey_id: int
    callback: Callable[[], Any]
    mandatory_audio: bool = True
    mandatory_visual: bool = True


def play_capture_sound() -> None:
    """Mandatory audible feedback whenever screen awareness is triggered."""
    if sys.platform == "win32":
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            return
        except Exception as exc:
            logger.debug("winsound.MessageBeep failed: %s", exc)
    logger.info("[AUDIO_DISCLOSURE] Screen capture trigger chime sounded.")


class GlobalHotkeyManager:
    """Manages system-wide Windows hotkeys on a dedicated message-pump thread."""

    def __init__(
        self,
        event_bus: DenverEventBus | None = None,
        enabled: bool = True,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self.event_bus = event_bus or get_event_bus()
        self.enabled = enabled
        self.loop = loop
        self._hotkeys: dict[int, RegisteredHotkey] = {}
        self._next_hotkey_id = 300
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._is_running = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._is_running

    def register_hotkey(
        self,
        name: str,
        hotkey_str: str,
        callback: Callable[[], Any],
        mandatory_audio: bool = True,
        mandatory_visual: bool = True,
    ) -> int | None:
        """Register a new global hotkey. Returns hotkey_id or None if disabled/failed."""
        if not self.enabled:
            logger.info("Global hotkey registration skipped ('%s'): hotkeys disabled by configuration.", name)
            return None

        try:
            modifiers, vk = parse_hotkey_string(hotkey_str)
        except Exception as exc:
            logger.warning("Failed to parse hotkey string '%s' for '%s': %s", hotkey_str, name, exc)
            return None

        with self._lock:
            hotkey_id = self._next_hotkey_id
            self._next_hotkey_id += 1
            entry = RegisteredHotkey(
                name=name,
                hotkey_str=hotkey_str,
                modifiers=modifiers,
                vk_code=vk,
                hotkey_id=hotkey_id,
                callback=callback,
                mandatory_audio=mandatory_audio,
                mandatory_visual=mandatory_visual,
            )
            self._hotkeys[hotkey_id] = entry
            logger.info("Configured hotkey '%s' ('%s', ID=%d)", name, hotkey_str, hotkey_id)
            return hotkey_id

    def start(self) -> bool:
        """Start the background Windows message pump thread."""
        if not self.enabled:
            logger.info("GlobalHotkeyManager not started: disabled by configuration.")
            return False

        if self._is_running:
            return True

        if not self._hotkeys:
            logger.debug("No hotkeys registered; GlobalHotkeyManager waiting for registrations.")
            return False

        if sys.platform != "win32":
            logger.info("Non-Windows platform; GlobalHotkeyManager running in software trigger mode.")
            self._is_running = True
            return True

        ready_event = threading.Event()
        self._is_running = True
        self._thread = threading.Thread(
            target=self._worker,
            args=(ready_event,),
            daemon=True,
            name="DenverGlobalHotkeyThread",
        )
        self._thread.start()
        ready_event.wait(timeout=2.0)
        return True

    def stop(self) -> None:
        """Stop background message pump and unregister all hotkeys."""
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
                logger.debug("Error posting WM_QUIT to hotkey thread: %s", exc)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        logger.info("GlobalHotkeyManager stopped.")

    def trigger(self, hotkey_id: int) -> None:
        """Execute a hotkey action with mandatory disclosure indicators."""
        entry = self._hotkeys.get(hotkey_id)
        if not entry:
            return

        logger.info("Global hotkey triggered: '%s' ('%s')", entry.name, entry.hotkey_str)

        # 1. Mandatory Audio Disclosure
        if entry.mandatory_audio:
            play_capture_sound()

        # 2. Mandatory Visual Disclosure
        if entry.mandatory_visual and self.event_bus:
            evt = ScreenCaptureTriggered(source="hotkey", hotkey=entry.hotkey_str)
            try:
                # Publish synchronously or threadsafe
                if self.loop and self.loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.event_bus.publish(evt), self.loop)
                else:
                    asyncio.create_task(self.event_bus.publish(evt))
            except Exception as exc:
                logger.debug("Could not publish ScreenCaptureTriggered event: %s", exc)

        # 3. Execute Callback
        try:
            res = entry.callback()
            if asyncio.iscoroutine(res):
                if self.loop and self.loop.is_running():
                    asyncio.run_coroutine_threadsafe(res, self.loop)
                else:
                    try:
                        cur_loop = asyncio.get_running_loop()
                        cur_loop.create_task(res)
                    except RuntimeError:
                        asyncio.run(res)
        except Exception as exc:
            logger.error("Error executing callback for hotkey '%s': %s", entry.name, exc)

    def _worker(self, ready_event: threading.Event) -> None:
        """Windows message pump registering all hotkeys."""
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        user32 = ctypes.windll.user32

        registered_ids = []
        for hid, entry in list(self._hotkeys.items()):
            ok = user32.RegisterHotKey(
                None,
                hid,
                entry.modifiers,
                entry.vk_code,
            )
            if ok:
                registered_ids.append(hid)
                logger.info("Registered global hotkey '%s' ('%s', ID=%d)", entry.name, entry.hotkey_str, hid)
            else:
                last_err = ctypes.windll.kernel32.GetLastError()
                logger.warning(
                    "Failed to register global hotkey '%s' ('%s', Error %d). Combo may be reserved.",
                    entry.name,
                    entry.hotkey_str,
                    last_err,
                )

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

                if msg.message == WM_HOTKEY and msg.wParam in self._hotkeys:
                    self.trigger(int(msg.wParam))

                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            for hid in registered_ids:
                user32.UnregisterHotKey(None, hid)
