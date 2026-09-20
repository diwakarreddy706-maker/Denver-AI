"""Unit tests for GlobalHotkeyManager and Screen Awareness hotkey disclosure."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from denver.automation.hotkey import (
    GlobalHotkeyManager,
    ScreenCaptureTriggered,
    play_capture_sound,
)
from denver.config.settings import DenverSettings
from denver.runtime.event_bus import DenverEventBus


def test_hotkey_string_parsing():
    """Verify that hotkey strings like 'ctrl+alt+s' parse into valid modifiers and VK codes."""
    from denver.audio.push_to_talk import parse_hotkey_string, MOD_CONTROL, MOD_ALT

    modifiers, vk = parse_hotkey_string("ctrl+alt+s")
    assert (modifiers & MOD_CONTROL) != 0
    assert (modifiers & MOD_ALT) != 0
    assert vk == ord("S")

    # Invalid hotkeys should raise ValueError
    with pytest.raises(ValueError):
        parse_hotkey_string("")


def test_hotkey_disabled_via_settings():
    """Confirm that when screen_awareness_hotkey_enabled is False, RegisterHotKey is NOT called."""
    settings = DenverSettings(
        screen_awareness_hotkey_enabled=False,
        screen_awareness_hotkey="ctrl+alt+s",
    )

    event_bus = DenverEventBus()
    manager = GlobalHotkeyManager(event_bus=event_bus, enabled=settings.screen_awareness_hotkey_enabled)

    callback_mock = MagicMock()
    # Registering while disabled returns None and does not store hotkey
    hid = manager.register_hotkey("screen_awareness", settings.screen_awareness_hotkey, callback_mock)
    assert hid is None

    with patch("ctypes.windll.user32.RegisterHotKey", create=True) as mock_reg:
        started = manager.start()
        assert started is False
        mock_reg.assert_not_called()


@pytest.mark.asyncio
async def test_hotkey_mandatory_indicators_and_trigger():
    """Verify mandatory audio disclosure and visual event publication when hotkey triggers."""
    event_bus = DenverEventBus()
    published_events = []

    def listener(evt):
        published_events.append(evt)

    event_bus.subscribe(ScreenCaptureTriggered, listener)

    manager = GlobalHotkeyManager(event_bus=event_bus, enabled=True)
    called = []

    def on_hotkey():
        called.append(True)

    hid = manager.register_hotkey(
        name="screen_awareness",
        hotkey_str="ctrl+alt+s",
        callback=on_hotkey,
        mandatory_audio=True,
        mandatory_visual=True,
    )
    assert hid is not None

    with patch("denver.automation.hotkey.play_capture_sound") as mock_sound:
        manager.trigger(hid)
        assert len(called) == 1
        mock_sound.assert_called_once()

    # Allow event bus dispatch
    await asyncio.sleep(0.05)
    assert len(published_events) == 1
    assert isinstance(published_events[0], ScreenCaptureTriggered)
    assert published_events[0].source == "hotkey"
    assert published_events[0].hotkey == "ctrl+alt+s"


def test_play_capture_sound_disclosure():
    """Ensure capture sound function executes without raising on any platform."""
    with patch("winsound.MessageBeep", create=True) as mock_beep:
        with patch("sys.platform", "win32"):
            play_capture_sound()
            mock_beep.assert_called_once()
