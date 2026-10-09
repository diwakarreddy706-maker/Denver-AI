"""Unit tests for Denver Cyber HUD Widget and Switchable Mode."""

from unittest.mock import MagicMock
import pytest
from PySide6.QtWidgets import QApplication

from denver.runtime.states import DenverState
from denver.ui.controller import UIController
from denver.ui.widgets.cyber_hud import DenverCyberHUDWidget
from denver.ui.window import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["-platform", "offscreen"])
    return app


def test_cyber_hud_widget_components_and_layout(qapp):
    mock_controller = MagicMock(spec=UIController)
    hud = DenverCyberHUDWidget(controller=mock_controller)

    # 1. Header elements
    assert hud.brand_lbl.text() == "DENVER"
    assert "SYSTEM ONLINE" in hud.status_badge.text()

    # 2. Four Telemetry Cards
    assert hud.cpu_card.title_lbl.text() == "CPU LOAD"
    assert hud.mem_card.title_lbl.text() == "MEMORY"
    assert hud.latency_card.title_lbl.text() == "LATENCY"
    assert hud.model_card.title_lbl.text() == "ACTIVE MODEL"

    # 3. Dynamic State Banner and Core Reactor
    assert hud.reactor is not None
    assert len(hud.state_banner.text()) > 0

    # 4. Activity Log Stream
    assert hud.log_frame is not None
    assert hud.log_layout.count() >= 4

    # 5. Cyber Command Prompt
    assert hud.prompt_edit.placeholderText() == "Ask Denver anything…"


def test_cyber_hud_state_updates(qapp):
    mock_controller = MagicMock(spec=UIController)
    hud = DenverCyberHUDWidget(controller=mock_controller)

    # State: LISTENING
    hud.set_state(DenverState.LISTENING)
    assert "L I S T E N I N G" in hud.state_banner.text()

    # State: PROCESSING
    hud.set_state(DenverState.PROCESSING)
    assert "P R O C E S S I N G" in hud.state_banner.text()

    # State: STANDBY
    hud.set_state(DenverState.STANDBY)
    assert "S T A N D B Y" in hud.state_banner.text()


def test_cyber_hud_telemetry_updates(qapp):
    mock_controller = MagicMock(spec=UIController)
    hud = DenverCyberHUDWidget(controller=mock_controller)

    hud.update_telemetry(cpu_pct=42.0, mem_pct=35.0, latency_ms=18.0, model="llama-3.1-groq")
    assert hud.cpu_card.val_lbl.text() == "42%"
    assert hud.mem_card.val_lbl.text() == "35%"
    assert hud.latency_card.val_lbl.text() == "18ms"
    assert hud.model_card.val_lbl.text() == "llama-3.1-groq"


def test_cyber_hud_activity_logging_and_submission(qapp):
    mock_controller = MagicMock(spec=UIController)
    hud = DenverCyberHUDWidget(controller=mock_controller)

    initial_count = hud.log_layout.count()
    hud.add_activity_event("user command processed")
    assert hud.log_layout.count() == initial_count + 1

    # Prompt submission
    submitted = []
    hud.command_submitted.connect(lambda cmd: submitted.append(cmd))
    hud.prompt_edit.setText("system status")
    hud._on_submit()

    assert submitted == ["system status"]
    mock_controller.submit_command.assert_called_with("system status")
    assert hud.prompt_edit.text() == ""


def test_main_window_switchable_hud_mode(qapp):
    mock_controller = MagicMock(spec=UIController)
    mock_controller.state = MagicMock()
    mock_controller.state.current_state = DenverState.STANDBY
    mock_controller.bridge = None

    window = MainWindow(controller=mock_controller)

    # Initially starts on index 0 (Cockpit Dashboard view)
    assert hasattr(window, "center_stack")
    assert window.center_stack.currentIndex() == 0
    assert hasattr(window, "cyber_hud_view")
    assert isinstance(window.cyber_hud_view, DenverCyberHUDWidget)

    # Toggle to Cyber HUD Mode (Index 1)
    window._toggle_view_mode()
    assert window.center_stack.currentIndex() == 1
    assert "Cockpit" in window.top_bar.mode_btn.text()

    # Toggle back to Cockpit Mode (Index 0)
    window._toggle_view_mode()
    assert window.center_stack.currentIndex() == 0
    assert "Cyber HUD" in window.top_bar.mode_btn.text()

    # Switch via sidebar nav selection
    window._on_sidebar_nav_selected("Cyber HUD")
    assert window.center_stack.currentIndex() == 1

    window._on_sidebar_nav_selected("Home")
    assert window.center_stack.currentIndex() == 0
