"""Unit tests for Phase 8 Routine Registry and SQLite Persistence."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from denver.memory.database import DenverDatabase
from denver.runtime.event_bus import DenverEventBus
from denver.scheduler.errors import (
    DuplicateRoutineError,
    RoutineNotFoundError,
    RoutineValidationError,
)
from denver.scheduler.models import (
    ExecutionStatus,
    NotificationPolicy,
    Routine,
    RoutineAction,
    RoutineExecution,
    RoutineStatus,
    RoutineTrigger,
    TriggerType,
)
from denver.scheduler.persistence import (
    RoutineAuditRepository,
    RoutineExecutionRepository,
    RoutineRepository,
)
from denver.scheduler.routine_registry import RoutineRegistry


@pytest.fixture
async def temp_db(tmp_path) -> DenverDatabase:
    db_file = tmp_path / "test_phase8.sqlite3"
    db = DenverDatabase(db_path=str(db_file))
    await db.initialize()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_routine_registry_crud(temp_db: DenverDatabase) -> None:
    event_bus = DenverEventBus()
    registry = RoutineRegistry(db=temp_db, event_bus=event_bus)

    trigger = RoutineTrigger(
        trigger_type=TriggerType.DAILY,
        time_of_day="09:00",
        timezone="UTC",
    )
    actions = [RoutineAction(action_name="get_time", params={})]

    # 1. Create Routine
    created = await registry.create_routine(
        name="Daily Time Check",
        trigger=trigger,
        actions=actions,
        description="Reads the current time every morning",
    )
    assert created.routine_id.startswith("rtn_")
    assert created.name == "Daily Time Check"
    assert created.enabled is True
    assert created.status == RoutineStatus.ACTIVE
    assert created.next_run_at is not None

    # 2. Get Routine
    fetched = await registry.get_routine(created.routine_id)
    assert fetched is not None
    assert fetched.name == "Daily Time Check"
    assert len(fetched.actions) == 1

    # 3. Duplicate Routine Prevention
    with pytest.raises(DuplicateRoutineError):
        await registry.create_routine(
            name="Daily Time Check",
            trigger=trigger,
            actions=actions,
        )

    # 4. Disable and Enable Routine
    disabled = await registry.disable_routine(created.routine_id)
    assert disabled.enabled is False
    assert disabled.status == RoutineStatus.DISABLED
    assert disabled.next_run_at is None

    enabled = await registry.enable_routine(created.routine_id)
    assert enabled.enabled is True
    assert enabled.status == RoutineStatus.ACTIVE
    assert enabled.next_run_at is not None

    # 5. Pause and Resume Routine
    paused = await registry.pause_routine(created.routine_id)
    assert paused.status == RoutineStatus.PAUSED

    resumed = await registry.resume_routine(created.routine_id)
    assert resumed.status == RoutineStatus.ACTIVE

    # 6. Delete Routine
    deleted = await registry.delete_routine(created.routine_id)
    assert deleted is True

    # 7. Verify Not Found after deletion
    assert await registry.get_routine(created.routine_id) is None


@pytest.mark.asyncio
async def test_routine_registry_validation_rejections(temp_db: DenverDatabase) -> None:
    event_bus = DenverEventBus()
    registry = RoutineRegistry(db=temp_db, event_bus=event_bus)

    trigger = RoutineTrigger(trigger_type=TriggerType.DAILY, time_of_day="12:00")

    # Empty name
    with pytest.raises(RoutineValidationError):
        await registry.create_routine(name="", trigger=trigger, actions=[RoutineAction(action_name="get_time")])

    # Empty actions
    with pytest.raises(RoutineValidationError):
        await registry.create_routine(name="Valid Name", trigger=trigger, actions=[])

    # Dangerous action injection attempts
    dangerous_actions = [
        RoutineAction(action_name="exec", params={"code": "import os"}),
        RoutineAction(action_name="eval", params={"expr": "1+1"}),
        RoutineAction(action_name="shell", params={"cmd": "subprocess.Popen"}),
        RoutineAction(action_name="custom", params={"script": "powershell -c whoami"}),
    ]
    for act in dangerous_actions:
        with pytest.raises(RoutineValidationError):
            await registry.create_routine(name=f"Dangerous {act.action_name}", trigger=trigger, actions=[act])


@pytest.mark.asyncio
async def test_routine_execution_and_audit_persistence(temp_db: DenverDatabase) -> None:
    now = datetime.now(timezone.utc)
    # Ensure parent routine exists in database
    parent_routine = Routine(
        routine_id="rtn_test_001",
        name="Test Routine",
        trigger=RoutineTrigger(trigger_type=TriggerType.DAILY, time_of_day="10:00"),
        actions=[RoutineAction(action_name="get_time")],
    )
    def _create_parent(conn):
        r_repo = RoutineRepository(conn)
        r_repo.save(parent_routine)
    await temp_db.run_async(_create_parent)

    execution = RoutineExecution(
        execution_id="exec_test_001",
        routine_id="rtn_test_001",
        started_at=now,
        completed_at=now,
        status=ExecutionStatus.SUCCESS,
        duration_ms=45.2,
        trigger_type="scheduled",
        action_count=1,
        successful_actions=1,
        failed_actions=0,
    )

    def _save_exec(conn):
        repo = RoutineExecutionRepository(conn)
        repo.save(execution)
        return repo.list_for_routine("rtn_test_001")

    history = await temp_db.run_async(_save_exec)
    assert len(history) == 1
    assert history[0].execution_id == "exec_test_001"
    assert history[0].status == ExecutionStatus.SUCCESS

    def _save_audit(conn):
        repo = RoutineAuditRepository(conn)
        repo.log("rtn_test_001", "routine_created", "user", {"name": "Test Routine"})
        return repo.list_for_routine("rtn_test_001")

    audit_logs = await temp_db.run_async(_save_audit)
    assert len(audit_logs) == 1
    assert audit_logs[0]["event_type"] == "routine_created"
    assert audit_logs[0]["actor"] == "user"
