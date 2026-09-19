"""Unit tests for Denver Home Dashboard Overlay widgets."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from denver.runtime.states import DenverState
from denver.ui.widgets.home_dashboard import (
    AIStatusCard,
    BottomBarWidget,
    CyberCard,
    DenverDashboardOverlay,
    LiveClockCard,
    QuickActionsCard,
    QuickStatusCard,
    SystemPerformanceCard,
    WeatherCard,
    _get_hardware_temperature,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["-platform", "offscreen"])
    return app


def test_cyber_card_base(qapp):
    card = CyberCard()
    assert card.objectName() == "CyberCard"


def test_weather_card_update_and_fallback(qapp):
    card = WeatherCard()
    # Test live update
    card.update_weather(
        city="Denver, CO",
        temp_c=21.4,
        condition="Partly Cloudy",
        humidity=45,
        wind_kph=14.2,
        visibility_km=10.0,
        pressure_hpa=1015,
    )
    assert card.location_lbl.text() == "Denver, CO"
    assert card.temp_lbl.text() == "21°C"
    assert card.cond_lbl.text() == "Partly Cloudy"
    assert "45%" in card.humidity_chip.text()
    assert "14.2 km/h" in card.wind_chip.text()

    # Test graceful degradation fallback (network failure, API error, or no location)
    card.set_weather_unavailable()
    assert card.location_lbl.text() == "Location unavailable"
    assert card.temp_lbl.text() == "--°C"
    assert card.cond_lbl.text() == "Weather Unavailable"
    assert card.feels_lbl.text() == "Offline / Connection required"
    assert "--%" in card.humidity_chip.text()


def test_system_performance_card_formatting(qapp):
    card = SystemPerformanceCard()
    card.update_telemetry(cpu_pct=34.567, mem_pct=62.891, storage_pct=45.123)

    assert card.cpu_lbl.text() == "34.6%"
    assert card.mem_lbl.text() == "62.9%"
    assert card.storage_lbl.text() == "45.1%"
    assert card.cpu_bar.value() == 34
    assert card.mem_bar.value() == 62
    assert card.storage_bar.value() == 45

    # Test None handling
    card.update_telemetry(cpu_pct=None, mem_pct=None, storage_pct=None)
    assert card.cpu_lbl.text() == "N/A"
    assert card.mem_lbl.text() == "N/A"


def test_quick_status_battery_desktop_hardware_none(qapp):
    """Test explicit None handling when psutil.sensors_battery() is None (desktop PC)."""
    with patch("psutil.sensors_battery", return_value=None):
        card = QuickStatusCard()
        card.refresh_quick_status()
        assert card.battery_lbl.text() == "🔋 Battery: N/A (AC)"


def test_quick_status_battery_laptop_present(qapp):
    """Test battery display when battery hardware is present."""
    mock_battery = MagicMock()
    mock_battery.percent = 84.2
    mock_battery.power_plugged = True

    with patch("psutil.sensors_battery", return_value=mock_battery):
        card = QuickStatusCard()
        card.refresh_quick_status()
        assert card.battery_lbl.text() == "🔋 Battery: 84% (AC)"


def test_quick_status_temperature_windows_unsupported(qapp):
    """Test explicit Temp: N/A when hardware temperature is unsupported on Windows."""
    with patch("psutil.sensors_temperatures", create=True, return_value={}):
        temp = _get_hardware_temperature()
        assert temp is None

    card = QuickStatusCard()
    card.refresh_quick_status()
    assert card.temp_lbl.text() == "Temp: N/A"


def test_quick_status_temperature_hardware_sensor(qapp):
    """Test temperature reading when supported hardware sensor is available."""
    mock_sensor = MagicMock()
    mock_sensor.current = 48.7
    with patch("psutil.sensors_temperatures", create=True, return_value={"coretemp": [mock_sensor]}):
        temp = _get_hardware_temperature()
        assert temp == 48.7

        card = QuickStatusCard()
        card.refresh_quick_status()
        assert card.temp_lbl.text() == "Temp: 48.7°C"


def test_quick_status_network_and_disk(qapp):
    card = QuickStatusCard()
    with patch("denver.ui.widgets.home_dashboard._check_network_connectivity", return_value=True):
        card.refresh_quick_status()
        assert "Online" in card.network_lbl.text()

    with patch("denver.ui.widgets.home_dashboard._check_network_connectivity", return_value=False):
        card.refresh_quick_status()
        assert "Offline" in card.network_lbl.text()


def test_live_clock_card(qapp):
    card = LiveClockCard()
    assert len(card.time_lbl.text()) > 5
    assert len(card.date_lbl.text()) > 5


def test_quick_actions_card_signals(qapp):
    mock_controller = MagicMock()
    card = QuickActionsCard(controller=mock_controller)

    emitted = []
    card.action_triggered.connect(lambda act: emitted.append(act))

    # Trigger New Task
    card.btn_task.click()
    assert "new_task" in emitted
    mock_controller.submit_command.assert_called_with("create task New Task")

    # Trigger Reminder
    card.btn_reminder.click()
    assert "reminder" in emitted
    assert any("create reminder" in str(call) for call in mock_controller.submit_command.call_args_list)

    # Trigger Notes
    card.btn_notes.click()
    assert "notes" in emitted
    assert any("create note" in str(call) for call in mock_controller.submit_command.call_args_list)

    # Trigger Calendar (TODO action)
    card.btn_calendar.click()
    assert "calendar_todo" in emitted


def test_ai_status_card_updates(qapp):
    card = AIStatusCard()
    card.update_status(DenverState.PROCESSING, latency_s=1.2)
    assert card.status_dot.text() == "● Processing"
    assert card.latency_lbl.text() == "1.2s"

    card.update_status(DenverState.ERROR)
    assert card.status_dot.text() == "● Error"


def test_bottom_bar_widget(qapp):
    mock_controller = MagicMock()
    bar = BottomBarWidget(controller=mock_controller)

    submitted = []
    bar.command_submitted.connect(lambda cmd: submitted.append(cmd))

    bar.search_input.setText("hello denver")
    bar._on_enter_pressed()
    assert submitted == ["hello denver"]
    mock_controller.submit_command.assert_called_with("hello denver")

    # Mic click
    mic_clicked = []
    bar.voice_clicked.connect(lambda: mic_clicked.append(True))
    bar.mic_btn.click()
    assert len(mic_clicked) == 1

    # Close button click
    close_emitted = []
    bar.close_requested.connect(lambda: close_emitted.append(True))
    bar.power_btn.click()
    assert len(close_emitted) == 1


def test_overlay_launch_and_exit_paths(qapp):
    """Test DenverDashboardOverlay instantiation and exit paths (Power button & Escape key)."""
    overlay = DenverDashboardOverlay()
    assert overlay.windowTitle().startswith("Denver")
    assert overlay.weather_card is not None
    assert overlay.perf_card is not None
    assert overlay.quick_status_card is not None
    assert overlay.clock_card is not None
    assert overlay.actions_card is not None
    assert overlay.ai_status_card is not None
    assert overlay.bottom_bar is not None

    # Test exit via power button signal
    close_called = []
    overlay.close_overlay = lambda: close_called.append("power")
    overlay.bottom_bar.power_btn.click()
    assert close_called == ["power"]

    # Test exit via Escape keyPressEvent
    close_called.clear()
    overlay.close_overlay = lambda: close_called.append("escape")
    escape_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    overlay.keyPressEvent(escape_event)
    assert close_called == ["escape"]
    assert escape_event.isAccepted()
