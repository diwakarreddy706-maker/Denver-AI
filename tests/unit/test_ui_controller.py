"""Unit tests for Denver Cockpit UIController and QtEventBridge."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from denver.commands.models import CommandResponse, CommandRiskLevel
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.events import (
    AutomationConfirmationRequired,
    SpeechStarted,
    SpeechStopped,
    StateChanged,
    WakeWordDetected,
)
from denver.runtime.states import DenverState
from denver.ui.controller import QtEventBridge, UIController


@pytest.fixture
def mock_app():
    app = MagicMock()
    app.event_bus = DenverEventBus()
    app.health_service = MagicMock()
    app.health_service.get_health_report.return_value = {
        "uptime_seconds": 12.0,
        "uptime_formatted": "00:00:12",
        "telemetry": {
            "cpu": {"usage_percent": 15.5},
            "memory": {"usage_percent": 55.0, "used_gb": 8.0, "total_gb": 16.0},
        },
        "ai_providers": {
            "providers": {"ollama": "READY", "lmstudio": "UNAVAILABLE"}
        },
        "automation": {
            "applications": "READY",
            "windows": "READY",
            "volume": "READY",
            "browser": "READY",
            "screenshot": "READY",
            "system": "READY",
        },
    }
    return app


def test_controller_initialization(mock_app):
    controller = UIController(app_instance=mock_app)
    assert controller.state.current_state == DenverState.BOOTING
    assert controller.state.cpu_percent is None


def test_controller_telemetry_polling(mock_app):
    controller = UIController(app_instance=mock_app)
    controller.poll_telemetry()
    assert controller.state.cpu_percent == 15.5
    assert controller.state.ram_percent == 55.0
    assert controller.state.ai_providers["ollama"] == "READY"
    assert controller.state.automation_status["applications"] == "READY"


def test_controller_submit_command_headless(mock_app):
    controller = UIController(app_instance=mock_app)
    controller.submit_command("Denver, what time is it?")
    assert len(controller.state.activity_history) == 1
    item = controller.state.activity_history[0]
    assert item.command_text == "Denver, what time is it?"
    assert item.success is True


@pytest.mark.asyncio
async def test_controller_event_bus_binding(mock_app):
    controller = UIController(app_instance=mock_app)
    controller.bind_event_bus()

    # Publish StateChanged
    await mock_app.event_bus.publish(StateChanged(from_state=DenverState.BOOTING, to_state=DenverState.STANDBY, reason="Test"))
    assert controller.state.current_state == DenverState.STANDBY

    # Publish SpeechStarted / SpeechStopped
    await mock_app.event_bus.publish(SpeechStarted())
    assert controller.state.voice_state == "LISTENING"
    assert controller.state.microphone_active is True

    await mock_app.event_bus.publish(SpeechStopped())
    assert controller.state.voice_state == "PROCESSING"
    assert controller.state.microphone_active is False

    # Publish WakeWordDetected
    await mock_app.event_bus.publish(WakeWordDetected(wake_word="Denver", confidence=1.0))
    assert controller.state.voice_state == "WAKE WORD"

    # Publish AutomationConfirmationRequired
    await mock_app.event_bus.publish(
        AutomationConfirmationRequired(
            action_name="lock_workstation",
            token="cnf_abc999",
            prompt_message="Confirm lock",
            timeout_seconds=30.0,
        )
    )
    assert controller.state.pending_confirmation is not None
    assert controller.state.pending_confirmation.token == "cnf_abc999"
