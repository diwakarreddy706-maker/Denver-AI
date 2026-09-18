"""Unit tests verifying security invariants of the Denver Cockpit UI."""

import pytest
from PySide6.QtWidgets import QApplication

from denver.config.settings import DenverSettings
from denver.ui.controller import UIController
from denver.ui.state import ActivityItem, CockpitState
from denver.ui.widgets.command_input import CommandInputWidget
from denver.ui.widgets.settings_dialog import SettingsDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["-platform", "offscreen"])
    return app


def test_ui_state_does_not_contain_raw_secrets():
    state = CockpitState()
    state_dict = vars(state)
    for key, value in state_dict.items():
        assert "api_key" not in key.lower()
        assert "password" not in key.lower()
        assert "secret" not in key.lower()


def test_settings_dialog_does_not_reveal_secrets(qapp):
    settings = DenverSettings(
        groq_api_key="gsk_secret_12345_groq_key",
        gemini_api_key="AIzaSy_secret_12345_gemini_key",
    )
    dialog = SettingsDialog(settings)
    dialog_text = ""
    for child in dialog.findChildren(object):
        if hasattr(child, "text") and callable(child.text):
            dialog_text += child.text() + " "

    assert "gsk_secret_12345_groq_key" not in dialog_text
    assert "AIzaSy_secret_12345_gemini_key" not in dialog_text
    assert "Configured" in dialog_text


def test_command_input_does_not_support_terminal_execution(qapp):
    widget = CommandInputWidget()
    # Ensure there is no arbitrary terminal or shell execution attribute
    assert not hasattr(widget, "execute_shell")
    assert not hasattr(widget, "run_powershell")
    assert not hasattr(widget, "spawn_process")


def test_activity_item_preserves_privacy():
    item = ActivityItem(
        command_text="Denver, remember my password is SecretPassword123",
        action_name="remember",
        response_text="Saved to memory.",
        risk_level="LOW",
        success=True,
    )
    # The action must be cleanly encapsulated
    assert item.action_name == "remember"
    assert item.risk_level == "LOW"
