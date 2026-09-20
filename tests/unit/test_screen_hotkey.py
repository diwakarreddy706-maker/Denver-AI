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


@pytest.mark.asyncio
async def test_screen_capture_triggered_event_subscription_and_ui_bridge():
    """Confirm that ScreenCaptureTriggered published on EventBus dispatches via UIController to the GUI bridge."""
    from denver.ui.controller import UIController, QtEventBridge

    event_bus = DenverEventBus()
    mock_app = MagicMock()
    mock_app.event_bus = event_bus

    bridge = MagicMock(spec=QtEventBridge)
    bridge.screen_capture_triggered = MagicMock()

    controller = UIController(app_instance=mock_app, bridge=bridge)
    controller.bind_event_bus()

    # Publish ScreenCaptureTriggered event
    evt = ScreenCaptureTriggered(source="hotkey", hotkey="ctrl+alt+s")
    await event_bus.publish(evt)
    await asyncio.sleep(0.05)

    # Confirm bridge signal was emitted with event parameters
    bridge.screen_capture_triggered.emit.assert_called_once_with("hotkey", "ctrl+alt+s")


def test_ui_trigger_screen_awareness_dialog_declined():
    """Verify that declining the CloudVisionDisclosureDialog cancels the screen capture completely."""
    from denver.ui.window import MainWindow
    from denver.ui.controller import UIController

    mock_controller = MagicMock(spec=UIController)
    mock_app = MagicMock()
    mock_app.provider_router.air_gapped_mode = False
    mock_controller.app = mock_app

    with patch.object(MainWindow, "__init__", return_value=None):
        win = MainWindow(controller=mock_controller)
        win.controller = mock_controller
        win._cloud_screen_disclosure_acknowledged = False
        win.show_capture_toast = MagicMock()

        with patch("denver.automation.hotkey.play_capture_sound"):
            with patch("denver.ui.widgets.confirmation_dialog.CloudVisionDisclosureDialog") as mock_dlg_cls:
                mock_dlg = MagicMock()
                mock_dlg.exec.return_value = 0  # User clicked Cancel
                mock_dlg_cls.return_value = mock_dlg

                win._trigger_screen_awareness()

                # Verify dialog was instantiated with parent and exec'd
                mock_dlg_cls.assert_called_once_with(parent=win)
                mock_dlg.exec.assert_called_once()

                # Verify capture was cancelled: command was never submitted
                mock_controller.submit_command.assert_not_called()
                assert win._cloud_screen_disclosure_acknowledged is False


def test_ui_trigger_screen_awareness_dialog_allowed():
    """Verify that allowing the CloudVisionDisclosureDialog acknowledges disclosure and submits command."""
    from denver.ui.window import MainWindow
    from denver.ui.controller import UIController

    mock_controller = MagicMock(spec=UIController)
    mock_app = MagicMock()
    mock_app.provider_router.air_gapped_mode = False
    mock_app.vision_engine = MagicMock()
    mock_controller.app = mock_app

    with patch.object(MainWindow, "__init__", return_value=None):
        win = MainWindow(controller=mock_controller)
        win.controller = mock_controller
        win._cloud_screen_disclosure_acknowledged = False
        win.show_capture_toast = MagicMock()

        with patch("denver.automation.hotkey.play_capture_sound"):
            with patch("denver.ui.widgets.confirmation_dialog.CloudVisionDisclosureDialog") as mock_dlg_cls:
                mock_dlg = MagicMock()
                mock_dlg.exec.return_value = 1  # User clicked Allow
                mock_dlg_cls.return_value = mock_dlg

                win._trigger_screen_awareness()

                # Verify dialog was shown
                mock_dlg_cls.assert_called_once_with(parent=win)
                mock_dlg.exec.assert_called_once()

                # Verify vision engine was acknowledged
                mock_app.vision_engine.acknowledge_cloud_disclosure.assert_called_once_with(True)
                assert win._cloud_screen_disclosure_acknowledged is True

                # Verify command was submitted
                mock_controller.submit_command.assert_called_once_with(
                    "Denver, look at my screen and describe what you see and diagnose any errors"
                )


