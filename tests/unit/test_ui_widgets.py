"""Unit tests for Denver Cockpit custom GUI widgets."""

import pytest
from PySide6.QtWidgets import QApplication

from denver.config.settings import DenverSettings
from denver.runtime.states import DenverState
from denver.ui.state import ActivityItem, CockpitState, ConfirmationItem
from denver.ui.theme import (
    BG_ROOT,
    BG_SURFACE,
    COCKPIT_STYLESHEET,
    PRIMARY_CYAN,
)
from denver.ui.widgets.activity_panel import ActivityItemCard, ActivityPanelWidget
from denver.ui.widgets.automation_status import AutomationStatusWidget
from denver.ui.widgets.command_input import CommandInputWidget
from denver.ui.widgets.confirmation_dialog import SecurityConfirmationDialog
from denver.ui.widgets.core_visualizer import DenverCoreVisualizer
from denver.ui.widgets.memory_status import MemoryStatusWidget
from denver.ui.widgets.provider_status import ProviderStatusWidget
from denver.ui.widgets.settings_dialog import SettingsDialog
from denver.ui.widgets.telemetry_panel import TelemetryCard, TelemetryPanelWidget
from denver.ui.widgets.voice_status import VoiceStatusWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["-platform", "offscreen"])
    return app


def test_core_visualizer_state_updates(qapp):
    visualizer = DenverCoreVisualizer()
    assert visualizer.minimumWidth() >= 260
    assert visualizer.minimumHeight() >= 260

    visualizer.set_state(DenverState.STANDBY)
    primary, accent, label = visualizer._get_state_visuals()
    assert label == "READY"

    visualizer.set_state(DenverState.LISTENING)
    primary, accent, label = visualizer._get_state_visuals()
    assert label == "LISTENING"

    visualizer.set_state(DenverState.PROCESSING)
    primary, accent, label = visualizer._get_state_visuals()
    assert label == "PROCESSING"

    visualizer.set_state(DenverState.ERROR)
    primary, accent, label = visualizer._get_state_visuals()
    assert label == "ERROR"


def test_command_input_widget(qapp):
    widget = CommandInputWidget()
    emitted = []
    widget.command_submitted.connect(lambda txt: emitted.append(txt))

    widget.input_field.setText("Denver, open calculator")
    widget._on_submit()

    assert len(emitted) == 1
    assert emitted[0] == "Denver, open calculator"
    assert widget.input_field.text() == ""


def test_activity_panel_widget(qapp):
    panel = ActivityPanelWidget()
    assert panel.empty_state.isHidden() is False

    item = ActivityItem(
        command_text="Denver, what time is it?",
        action_name="get_time",
        response_text="01:50 PM",
        risk_level="SAFE",
        success=True,
    )
    panel.add_item(item)
    # Empty state hidden after item arrival
    assert panel.empty_state.isHidden() is True
    assert panel.list_layout.count() >= 2


def test_telemetry_panel_widget(qapp):
    panel = TelemetryPanelWidget()
    state = CockpitState(
        cpu_percent=42.0,
        ram_percent=68.5,
        ram_used_gb=10.5,
        ram_total_gb=16.0,
        battery_percent=88,
        battery_charging=True,
        uptime_seconds=3600.0,
        uptime_formatted="01:00:00",
    )
    panel.update_telemetry(state)
    assert panel.cpu_card.value_lbl.text() == "42.0%"
    assert panel.ram_card.value_lbl.text() == "68.5%"
    assert panel.battery_card.value_lbl.text() == "88%"
    assert panel.uptime_card.value_lbl.text() == "01:00:00"


def test_subsystem_status_widgets(qapp):
    # Provider status
    p_widget = ProviderStatusWidget()
    p_widget.update_providers({"ollama": "READY", "groq": "NOT_CONFIGURED"})
    assert p_widget.ollama_row.status_lbl.text() == "READY"
    assert p_widget.groq_row.status_lbl.text() == "NOT CONFIGURED"

    # Automation status
    a_widget = AutomationStatusWidget()
    a_widget.update_automation({"applications": "READY", "volume": "READY"})
    assert a_widget.apps_badge.label.text() == "Applications"

    # Memory status
    m_widget = MemoryStatusWidget()
    m_widget.update_memory({"memories_count": 5, "notes_count": 2, "tasks_count": 3, "privacy_mode": True})
    assert m_widget.mem_count_lbl.text() == "5 Memories"
    assert m_widget.privacy_label.text() == "PRIVACY: ON"

    # Voice status
    v_widget = VoiceStatusWidget()
    v_widget.set_voice_state("LISTENING", mic_active=True, mic_available=True)
    assert v_widget.pipeline_state_lbl.text() == "LISTENING"
    assert "Listening" in v_widget.mic_lbl.text()


def test_confirmation_dialog_widget(qapp):
    item = ConfirmationItem(
        token="cnf_test999",
        action_name="lock_workstation",
        description="Lock computer?",
        expires_at=9999999999.0,
    )
    dialog = SecurityConfirmationDialog(item)
    confirmed_tokens = []
    dialog.confirmed.connect(lambda tok: confirmed_tokens.append(tok))

    dialog._on_confirm()
    assert confirmed_tokens == ["cnf_test999"]


def test_settings_dialog_widget(qapp):
    settings = DenverSettings()
    dialog = SettingsDialog(settings)
    assert dialog.chk_privacy.isChecked() == settings.privacy_mode
    assert dialog.combo_ai_mode.currentText() == settings.ai_mode


def test_theme_constants():
    assert BG_ROOT == "#070B14"
    assert BG_SURFACE == "#0F172A"
    assert PRIMARY_CYAN == "#06B6D4"
    assert len(COCKPIT_STYLESHEET) > 100
