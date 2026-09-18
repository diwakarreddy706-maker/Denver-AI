"""Unit tests for Denver Cockpit Plugins Center and System Auto-Repair Controls."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication

from denver.ui.controller import UIController
from denver.ui.widgets.plugins_widget import PluginCardWidget, PluginsWidget
from denver.ui.widgets.telemetry_panel import TelemetryPanelWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["-platform", "offscreen"])
    return app


def test_plugins_widget_instantiation_and_update(qapp):
    widget = PluginsWidget()
    sample_plugins = [
        {
            "id": "weather_ext",
            "name": "Weather Extension",
            "version": "1.0.0",
            "description": "Extended weather radar queries.",
            "permissions": ["network"],
            "max_risk": "LOW",
            "enabled": True,
            "loaded": True,
        },
        {
            "id": "system_tweak",
            "name": "System Tweaks",
            "version": "0.5.0",
            "description": "Kernel tweaks and hardware controls.",
            "permissions": ["system_exec"],
            "max_risk": "CRITICAL",
            "enabled": False,
            "loaded": False,
        },
    ]
    widget.update_plugins(sample_plugins)
    assert "2 Installed" in widget.count_badge.text()


def test_plugin_card_toggle_signal(qapp):
    p_data = {
        "id": "test_plug",
        "name": "Test Plugin",
        "version": "1.0.0",
        "description": "Test plugin description",
        "permissions": ["network"],
        "max_risk": "LOW",
        "enabled": True,
    }
    card = PluginCardWidget(p_data)
    signals_received = []
    card.toggle_requested.connect(lambda pid, enabled: signals_received.append((pid, enabled)))

    # Simulate toggle click
    card._on_toggle_clicked()
    assert len(signals_received) == 1
    assert signals_received[0] == ("test_plug", False)
    assert "DISABLED" in card.toggle_btn.text()


def test_controller_plugin_delegation():
    mock_app = MagicMock()
    mock_app.command_service = MagicMock()
    mock_app.command_service.plugin_registry = MagicMock()
    controller = UIController(app_instance=mock_app)

    mock_app.command_service.plugin_registry.enable_plugin.return_value = True
    mock_app.command_service.plugin_registry.disable_plugin.return_value = True
    mock_app.command_service.plugin_registry.list_plugins.return_value = [{"id": "p1", "name": "P1"}]
    mock_app.command_service.plugin_registry.reload_all.return_value = 1

    assert controller.toggle_plugin("p1", True) is True
    mock_app.command_service.plugin_registry.enable_plugin.assert_called_with("p1")

    assert controller.toggle_plugin("p1", False) is True
    mock_app.command_service.plugin_registry.disable_plugin.assert_called_with("p1")

    plugins = controller.get_plugins()
    assert len(plugins) == 1

    reloaded = controller.reload_plugins()
    assert reloaded == 1


def test_telemetry_panel_repair_controls(qapp):
    panel = TelemetryPanelWidget()
    repair_signals = []
    panel.repair_requested.connect(lambda: repair_signals.append(True))

    panel._on_repair_clicked()
    assert len(repair_signals) == 1
    assert "Running repair..." in panel.repair_status_lbl.text()

    panel.set_repair_result(fixed_count=2, detected_count=2)
    assert "Repaired 2 issue(s)" in panel.repair_status_lbl.text()

    panel.set_repair_result(fixed_count=0, detected_count=0)
    assert "All systems optimal" in panel.repair_status_lbl.text()
