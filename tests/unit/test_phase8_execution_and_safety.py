"""Unit tests for Phase 8 Routine Execution Coordinator and Safety Boundaries."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from denver.automation.executor import AutomationExecutor
from denver.commands.models import (
    ActionRequest,
    ActionResult,
    CommandCategory,
    CommandRiskLevel,
)
from denver.commands.registry import ActionDefinition, ActionRegistry
from denver.commands.safety import SafetyValidator
from denver.memory.database import DenverDatabase
from denver.runtime.event_bus import DenverEventBus
from denver.scheduler.errors import ApprovalRequiredError
from denver.scheduler.execution_coordinator import RoutineExecutionCoordinator
from denver.scheduler.models import (
    ExecutionStatus,
    NotificationPolicy,
    Routine,
    RoutineAction,
    RoutineStatus,
    RoutineTrigger,
    TriggerType,
)


@pytest.fixture
async def temp_db(tmp_path) -> DenverDatabase:
    db_file = tmp_path / "test_phase8_exec.sqlite3"
    db = DenverDatabase(db_path=str(db_file))
    await db.initialize()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_coordinator_safe_execution(temp_db: DenverDatabase) -> None:
    event_bus = DenverEventBus()
    registry = ActionRegistry()
    safety = SafetyValidator()

    # Register a safe test action
    def _test_handler(params):
        return ActionResult(success=True, message="Test action executed successfully", action_name="test_action")

    registry.register(
        ActionDefinition(
            name="test_action",
            description="Safe test action",
            category=CommandCategory.UTILITY,
            risk_level=CommandRiskLevel.SAFE,
            handler=_test_handler,
        )
    )

    coordinator = RoutineExecutionCoordinator(
        db=temp_db,
        action_registry=registry,
        safety_validator=safety,
        event_bus=event_bus,
    )

    routine = Routine(
        routine_id="rtn_safe_01",
        name="Safe Routine",
        trigger=RoutineTrigger(trigger_type=TriggerType.ONE_TIME, run_at=datetime.now(timezone.utc)),
        actions=[RoutineAction(action_name="test_action", params={"k": "v"})],
        enabled=True,
    )

    exec_result = await coordinator.execute_routine(routine)
    assert exec_result.status == ExecutionStatus.SUCCESS
    assert exec_result.successful_actions == 1
    assert exec_result.failed_actions == 0


@pytest.mark.asyncio
async def test_coordinator_blocks_dangerous_actions(temp_db: DenverDatabase) -> None:
    event_bus = DenverEventBus()
    registry = ActionRegistry()
    safety = SafetyValidator()

    coordinator = RoutineExecutionCoordinator(
        db=temp_db,
        action_registry=registry,
        safety_validator=safety,
        event_bus=event_bus,
    )

    # Action that does not exist or blocked
    routine = Routine(
        routine_id="rtn_unreg_01",
        name="Unregistered Action Routine",
        trigger=RoutineTrigger(trigger_type=TriggerType.ONE_TIME, run_at=datetime.now(timezone.utc)),
        actions=[RoutineAction(action_name="nonexistent_action")],
        enabled=True,
    )

    exec_result = await coordinator.execute_routine(routine)
    assert exec_result.status == ExecutionStatus.FAILED
    assert exec_result.failed_actions == 1


@pytest.mark.asyncio
async def test_coordinator_concurrency_limiting(temp_db: DenverDatabase) -> None:
    event_bus = DenverEventBus()
    registry = ActionRegistry()
    safety = SafetyValidator()

    # Slow action
    async def _slow_handler(params):
        await asyncio.sleep(0.05)
        return ActionResult(success=True, message="Slow action done", action_name="slow_action")

    registry.register(
        ActionDefinition(
            name="slow_action",
            description="Slow action",
            category=CommandCategory.UTILITY,
            risk_level=CommandRiskLevel.SAFE,
            handler=_slow_handler,
        )
    )

    # Limit to max_concurrency = 1
    coordinator = RoutineExecutionCoordinator(
        db=temp_db,
        action_registry=registry,
        safety_validator=safety,
        event_bus=event_bus,
        max_concurrency=1,
    )

    routine1 = Routine(
        routine_id="rtn_c1",
        name="R1",
        trigger=RoutineTrigger(trigger_type=TriggerType.ONE_TIME, run_at=datetime.now(timezone.utc)),
        actions=[RoutineAction(action_name="slow_action")],
        enabled=True,
    )
    routine2 = Routine(
        routine_id="rtn_c2",
        name="R2",
        trigger=RoutineTrigger(trigger_type=TriggerType.ONE_TIME, run_at=datetime.now(timezone.utc)),
        actions=[RoutineAction(action_name="slow_action")],
        enabled=True,
    )

    results = await asyncio.gather(
        coordinator.execute_routine(routine1),
        coordinator.execute_routine(routine2),
    )
    assert len(results) == 2
    assert results[0].status == ExecutionStatus.SUCCESS
    assert results[1].status == ExecutionStatus.SUCCESS
