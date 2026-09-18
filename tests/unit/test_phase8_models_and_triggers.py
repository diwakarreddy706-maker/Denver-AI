"""Unit tests for Phase 8 Scheduler Models and Trigger Engine."""

from __future__ import annotations

from datetime import datetime, time as dtime, timedelta, timezone

import pytest

from denver.scheduler.errors import (
    InvalidTriggerError,
    TriggerIntervalTooShortError,
)
from denver.scheduler.models import (
    ExecutionStatus,
    NotificationPolicy,
    Routine,
    RoutineAction,
    RoutineExecution,
    RoutineProposal,
    RoutineStatus,
    RoutineTrigger,
    TriggerType,
)
from denver.scheduler.trigger_engine import TriggerEngine


def test_trigger_type_enums() -> None:
    assert TriggerType.from_value("one_time") == TriggerType.ONE_TIME
    assert TriggerType.from_value("daily") == TriggerType.DAILY
    assert TriggerType.from_value("weekly") == TriggerType.WEEKLY
    assert TriggerType.from_value("interval") == TriggerType.INTERVAL
    with pytest.raises(ValueError):
        TriggerType.from_value("invalid_type")


def test_trigger_model_to_from_dict() -> None:
    dt = datetime(2026, 9, 15, 10, 0, 0, tzinfo=timezone.utc)
    trigger = RoutineTrigger(
        trigger_type=TriggerType.ONE_TIME,
        run_at=dt,
        time_of_day="10:00",
        days_of_week=[0, 1, 2],
        interval_seconds=600.0,
        timezone="UTC",
    )
    d = trigger.to_dict()
    assert d["trigger_type"] == "one_time"
    assert d["time_of_day"] == "10:00"
    assert d["interval_seconds"] == 600.0

    restored = RoutineTrigger.from_dict(d)
    assert restored.trigger_type == TriggerType.ONE_TIME
    assert restored.run_at == dt
    assert restored.time_of_day == "10:00"
    assert restored.days_of_week == [0, 1, 2]
    assert restored.interval_seconds == 600.0


def test_routine_action_to_from_dict() -> None:
    action = RoutineAction(
        action_name="get_cpu",
        params={"threshold": 90},
        description="Check high CPU usage",
    )
    d = action.to_dict()
    assert d["action_name"] == "get_cpu"
    assert d["params"] == {"threshold": 90}

    restored = RoutineAction.from_dict(d)
    assert restored.action_name == "get_cpu"
    assert restored.params == {"threshold": 90}
    assert restored.description == "Check high CPU usage"


def test_routine_model_serialization() -> None:
    now = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
    routine = Routine(
        routine_id="rtn_test123",
        name="Morning Health Check",
        trigger=RoutineTrigger(trigger_type=TriggerType.DAILY, time_of_day="08:30"),
        actions=[RoutineAction(action_name="get_system_status")],
        created_at=now,
        updated_at=now,
    )
    d = routine.to_dict()
    assert d["routine_id"] == "rtn_test123"
    assert d["name"] == "Morning Health Check"
    assert d["enabled"] is True
    assert d["status"] == "active"

    restored = Routine.from_dict(d)
    assert restored.routine_id == "rtn_test123"
    assert restored.name == "Morning Health Check"
    assert len(restored.actions) == 1
    assert restored.actions[0].action_name == "get_system_status"


def test_trigger_engine_one_time() -> None:
    engine = TriggerEngine()
    now = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
    future = datetime(2026, 9, 14, 14, 0, 0, tzinfo=timezone.utc)
    past = datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone.utc)

    # Future one-time trigger
    t_future = RoutineTrigger(trigger_type=TriggerType.ONE_TIME, run_at=future)
    assert engine.compute_next_run(t_future, after_dt=now) == future

    # Past one-time trigger returns None (missed / completed)
    t_past = RoutineTrigger(trigger_type=TriggerType.ONE_TIME, run_at=past)
    assert engine.compute_next_run(t_past, after_dt=now) is None


def test_trigger_engine_interval() -> None:
    engine = TriggerEngine()
    now = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)

    # Valid interval (>= 300s)
    t_valid = RoutineTrigger(trigger_type=TriggerType.INTERVAL, interval_seconds=600.0)
    next_run = engine.compute_next_run(t_valid, after_dt=now)
    assert next_run == now + timedelta(seconds=600.0)

    # Too short interval (< 300s) raises TriggerIntervalTooShortError
    t_short = RoutineTrigger(trigger_type=TriggerType.INTERVAL, interval_seconds=60.0)
    with pytest.raises(TriggerIntervalTooShortError):
        engine.compute_next_run(t_short, after_dt=now)


def test_trigger_engine_daily() -> None:
    engine = TriggerEngine()
    # Now is 10:00 UTC
    now = datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone.utc)

    # Target is 14:30 today
    t_today = RoutineTrigger(trigger_type=TriggerType.DAILY, time_of_day="14:30", timezone="UTC")
    next_today = engine.compute_next_run(t_today, after_dt=now)
    assert next_today == datetime(2026, 9, 14, 14, 30, 0, tzinfo=timezone.utc)

    # Target is 08:30 (already passed today) -> schedules for tomorrow 08:30
    t_tomorrow = RoutineTrigger(trigger_type=TriggerType.DAILY, time_of_day="08:30", timezone="UTC")
    next_tomorrow = engine.compute_next_run(t_tomorrow, after_dt=now)
    assert next_tomorrow == datetime(2026, 9, 15, 8, 30, 0, tzinfo=timezone.utc)


def test_trigger_engine_weekly() -> None:
    engine = TriggerEngine()
    # 2026-09-14 is a Monday (weekday=0)
    now = datetime(2026, 9, 14, 10, 0, 0, tzinfo=timezone.utc)

    # Target: Wednesday (weekday=2) and Friday (weekday=4) at 09:00
    t_weekly = RoutineTrigger(
        trigger_type=TriggerType.WEEKLY,
        time_of_day="09:00",
        days_of_week=[2, 4],
        timezone="UTC",
    )
    next_run = engine.compute_next_run(t_weekly, after_dt=now)
    # Next should be Wednesday 2026-09-16 09:00 UTC
    assert next_run == datetime(2026, 9, 16, 9, 0, 0, tzinfo=timezone.utc)


def test_trigger_engine_invalid_triggers() -> None:
    engine = TriggerEngine()
    with pytest.raises(InvalidTriggerError):
        engine.validate_trigger(RoutineTrigger(trigger_type=TriggerType.ONE_TIME, run_at=None))

    with pytest.raises(InvalidTriggerError):
        engine.validate_trigger(RoutineTrigger(trigger_type=TriggerType.DAILY, time_of_day=None))

    with pytest.raises(InvalidTriggerError):
        engine.validate_trigger(RoutineTrigger(trigger_type=TriggerType.DAILY, time_of_day="99:99"))

    with pytest.raises(InvalidTriggerError):
        engine.validate_trigger(RoutineTrigger(trigger_type=TriggerType.WEEKLY, time_of_day="10:00", days_of_week=[]))

    with pytest.raises(InvalidTriggerError):
        engine.validate_trigger(RoutineTrigger(trigger_type=TriggerType.WEEKLY, time_of_day="10:00", days_of_week=[7]))
