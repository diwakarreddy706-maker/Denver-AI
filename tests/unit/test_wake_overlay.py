"""Unit tests for Denver wake HUD overlay and system tray."""

from __future__ import annotations

import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from denver.ui.tray import DenverTrayIcon
from denver.ui.widgets.wake_overlay import (
    WakeOverlay,
    get_wake_overlay,
    notify_wake_overlay,
    read_system,
)


def _get_qapp() -> QApplication:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication(["pytest", "-platform", "offscreen"])
    return app


def test_wake_overlay_initialization_and_flags() -> None:
    _get_qapp()
    overlay = get_wake_overlay()

    assert overlay is not None
    flags = overlay.windowFlags()
    assert bool(flags & Qt.WindowType.FramelessWindowHint)
    assert bool(flags & Qt.WindowType.WindowStaysOnTopHint)
    assert bool(flags & Qt.WindowType.WindowDoesNotAcceptFocus)


def test_wake_overlay_state_machine() -> None:
    _get_qapp()
    overlay = get_wake_overlay()

    overlay.show_listening()
    overlay.set_state("PROCESSING")
    assert overlay._state == "PROCESSING"

    overlay.set_state("SPEAKING")
    assert overlay._state == "SPEAKING"

    overlay.set_state("STANDBY")
    assert overlay._state == "STANDBY"

    overlay.hide_overlay()
    assert overlay._target_opacity == 0.0


def test_notify_wake_overlay_function() -> None:
    _get_qapp()
    # Ensure notify_wake_overlay is thread-safe and non-raising
    notify_wake_overlay("LISTENING")
    notify_wake_overlay("PROCESSING")
    notify_wake_overlay("SPEAKING")
    notify_wake_overlay("STANDBY")
    notify_wake_overlay("HIDE")


def test_read_system_metrics() -> None:
    sys_metrics = read_system()
    assert "cpu" in sys_metrics
    assert "mem" in sys_metrics
    assert "batt" in sys_metrics
    assert "plugged" in sys_metrics
    assert isinstance(sys_metrics["cpu"], (int, float))
    assert isinstance(sys_metrics["mem"], (int, float))


def test_denver_tray_icon_and_muting() -> None:
    _get_qapp()

    class FakeCapture:
        def __init__(self):
            self.is_muted = False

        def mute(self):
            self.is_muted = True

        def unmute(self):
            self.is_muted = False

        def toggle_mute(self):
            self.is_muted = not self.is_muted
            return self.is_muted

    class FakePipeline:
        def __init__(self):
            self.capture = FakeCapture()

        @property
        def is_muted(self):
            return self.capture.is_muted

        def toggle_mute(self):
            return self.capture.toggle_mute()

    class FakeApp:
        def __init__(self):
            self.voice_pipeline = FakePipeline()

    fake_app = FakeApp()
    tray = DenverTrayIcon(denver_app=fake_app)

    # Initial state is unmuted
    assert not tray._is_muted

    # Toggle to muted
    muted = tray.toggle_microphone_mute()
    assert muted
    assert fake_app.voice_pipeline.is_muted
    assert tray._action_mute is not None
    assert tray._action_mute.text() == "Unmute Microphone"

    # Toggle back to unmuted
    muted = tray.toggle_microphone_mute()
    assert not muted
    assert not fake_app.voice_pipeline.is_muted
    assert tray._action_mute is not None
    assert tray._action_mute.text() == "Mute Microphone"


def test_wake_overlay_themes() -> None:
    _get_qapp()
    overlay = get_wake_overlay()

    from denver.ui.widgets.wake_overlay import THEMES, notify_wake_overlay_theme

    assert "JARVIS" in THEMES
    assert "CYBERPUNK" in THEMES
    assert "MATRIX" in THEMES
    assert "STEALTH" in THEMES
    assert "CRIMSON" in THEMES

    overlay.set_theme("CYBERPUNK")
    assert overlay._theme_name == "CYBERPUNK"

    notify_wake_overlay_theme("MATRIX")
    # Verify theme switch handles valid palettes
    overlay.set_theme("MATRIX")
    assert overlay._theme_name == "MATRIX"


def test_wake_overlay_adaptive_modes() -> None:
    _get_qapp()
    overlay = get_wake_overlay()

    from denver.ui.widgets.wake_overlay import notify_wake_overlay_mode

    overlay.set_mode("compact")
    assert overlay._mode == "compact"
    assert overlay.width() == overlay.W_COMPACT
    assert overlay.height() == overlay.H_COMPACT

    overlay.set_mode("expanded")
    assert overlay._mode == "expanded"
    assert overlay.width() == overlay.W_EXPANDED
    assert overlay.height() == overlay.H_EXPANDED

    overlay.toggle_mode()
    assert overlay._mode == "compact"
    overlay.toggle_mode()
    assert overlay._mode == "expanded"


def test_wake_overlay_audio_reactivity() -> None:
    _get_qapp()
    overlay = get_wake_overlay()

    from denver.ui.widgets.wake_overlay import notify_wake_overlay_audio

    overlay.set_audio_level(0.75)
    assert overlay._target_audio_level == 0.75

    # Clamping boundaries
    overlay.set_audio_level(1.5)
    assert overlay._target_audio_level == 1.0

    overlay.set_audio_level(-0.5)
    assert overlay._target_audio_level == 0.0

    notify_wake_overlay_audio(0.6)


def test_wake_overlay_subtitles_and_receipts() -> None:
    _get_qapp()
    overlay = get_wake_overlay()

    from denver.ui.widgets.wake_overlay import (
        notify_wake_overlay_receipt,
        notify_wake_overlay_subtitle,
    )

    overlay.set_subtitle("> Turn on notepad and write hi")
    assert overlay._subtitle == "> Turn on notepad and write hi"

    overlay.show_receipt("🚀", "Notepad Launched", "PID 20420")
    assert overlay._receipt is not None
    assert overlay._receipt["icon"] == "🚀"
    assert overlay._receipt["title"] == "Notepad Launched"
    assert overlay._receipt["detail"] == "PID 20420"

    notify_wake_overlay_subtitle("> Testing subtitle notification")
    notify_wake_overlay_receipt("🌤", "Weather Updated", "31C")


def test_scifi_audio_player() -> None:
    from denver.ui.widgets.wake_overlay import SciFiAudioPlayer

    player = SciFiAudioPlayer(enabled=True)
    assert player is not None
    # Verify synthesize and play do not raise
    player.play("wake")
    player.play("success")
    player.play("standby")


def test_acrylic_glass_helper() -> None:
    from denver.ui.widgets.wake_overlay import apply_windows_acrylic_glass

    # Safe call with invalid hwnd shouldn't crash
    res = apply_windows_acrylic_glass(0)
    assert isinstance(res, bool)

