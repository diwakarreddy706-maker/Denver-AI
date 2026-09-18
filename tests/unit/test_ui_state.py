"""Unit tests for Denver Cockpit presentation state model."""

import time
from denver.runtime.states import DenverState
from denver.ui.state import ActivityItem, CockpitState, ConfirmationItem


def test_activity_item_creation():
    item = ActivityItem(
        command_text="what time is it",
        action_name="get_time",
        response_text="The current time is 01:45 PM.",
        risk_level="SAFE",
        success=True,
        latency_ms=12.5,
    )
    assert item.command_text == "what time is it"
    assert item.action_name == "get_time"
    assert item.success is True
    assert item.risk_level == "SAFE"
    assert item.latency_ms == 12.5
    assert len(item.formatted_time) > 0


def test_confirmation_item_expiration():
    now = time.time()
    active_item = ConfirmationItem(
        token="cnf_test123",
        action_name="lock_workstation",
        description="Locking workstation requires confirmation.",
        expires_at=now + 30.0,
    )
    assert not active_item.is_expired
    assert active_item.seconds_remaining > 0

    expired_item = ConfirmationItem(
        token="cnf_exp123",
        action_name="lock_workstation",
        description="Expired",
        expires_at=now - 5.0,
    )
    assert expired_item.is_expired
    assert expired_item.seconds_remaining == 0.0


def test_cockpit_state_add_activity_capping():
    state = CockpitState()
    assert state.current_state == DenverState.BOOTING
    assert len(state.activity_history) == 0

    for i in range(60):
        state.add_activity(ActivityItem(command_text=f"cmd_{i}"))

    assert len(state.activity_history) == 50
    assert state.activity_history[-1].command_text == "cmd_59"
    assert state.activity_history[0].command_text == "cmd_10"
