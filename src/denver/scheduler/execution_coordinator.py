"""Routine Execution Coordinator with Concurrency, Safety, and Timeout Guarantees."""

from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from denver.automation.executor import AutomationExecutor
from denver.automation.models import AutomationRequest
from denver.commands.models import ActionRequest, ActionResult, CommandCategory, CommandRiskLevel
from denver.commands.registry import ActionRegistry
from denver.commands.safety import SafetyValidator
from denver.logging.logger import get_logger, mask_sensitive_data
from denver.memory.database import DenverDatabase
from denver.runtime.event_bus import DenverEventBus, get_event_bus
from denver.runtime.events import (
    RoutineBlocked,
    RoutineCompleted,
    RoutineFailed,
    RoutineStarted,
)
from denver.scheduler.approval import RoutineApprovalManager
from denver.scheduler.audit import RoutineAuditLogger
from denver.scheduler.errors import ExecutionTimeoutError
from denver.scheduler.models import (
    ExecutionStatus,
    Routine,
    RoutineAction,
    RoutineExecution,
    RoutineStatus,
    TriggerType,
)
from denver.scheduler.notifications import RoutineNotificationService
from denver.scheduler.persistence import RoutineExecutionRepository, RoutineRepository
from denver.scheduler.trigger_engine import TriggerEngine

logger = get_logger("scheduler.coordinator")


class RoutineExecutionCoordinator:
    """Coordinates execution of scheduled routines through the secure Denver execution pipeline."""

    def __init__(
        self,
        db: DenverDatabase,
        action_registry: ActionRegistry,
        safety_validator: SafetyValidator,
        automation_executor: AutomationExecutor | None = None,
        approval_manager: RoutineApprovalManager | None = None,
        notification_service: RoutineNotificationService | None = None,
        audit_logger: RoutineAuditLogger | None = None,
        trigger_engine: TriggerEngine | None = None,
        event_bus: DenverEventBus | None = None,
        max_concurrency: int = 2,
    ) -> None:
        self.db = db
        self.registry = action_registry
        self.safety = safety_validator
        self.automation = automation_executor or AutomationExecutor(event_bus=event_bus)
        self.approval = approval_manager or RoutineApprovalManager(event_bus=event_bus)
        self.notifications = notification_service or RoutineNotificationService(event_bus=event_bus)
        self.audit = audit_logger or RoutineAuditLogger(db)
        self.trigger_engine = trigger_engine or TriggerEngine()
        self.event_bus = event_bus or get_event_bus()

        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._running_routines: set[str] = set()

    @property
    def currently_executing_count(self) -> int:
        return len(self._running_routines)

    def is_routine_running(self, routine_id: str) -> bool:
        return routine_id in self._running_routines

    async def execute_routine(
        self,
        routine: Routine,
        trigger_type: str = "scheduled",
        force: bool = False,
    ) -> RoutineExecution:
        """Execute all actions in a routine bounded by semaphore and timeout."""
        if not routine.enabled and not force:
            logger.warning("Attempted to execute disabled routine '%s'.", routine.routine_id)
            now = datetime.now(timezone.utc)
            return RoutineExecution(
                execution_id=f"exec_{uuid.uuid4().hex[:8]}",
                routine_id=routine.routine_id,
                started_at=now,
                completed_at=now,
                status=ExecutionStatus.SKIPPED,
                trigger_type=trigger_type,
                error_summary="Routine is disabled",
            )

        # Prevent duplicate concurrent executions of the same routine
        if self.is_routine_running(routine.routine_id):
            logger.warning("Routine '%s' is already executing; skipping duplicate run.", routine.routine_id)
            now = datetime.now(timezone.utc)
            return RoutineExecution(
                execution_id=f"exec_{uuid.uuid4().hex[:8]}",
                routine_id=routine.routine_id,
                started_at=now,
                completed_at=now,
                status=ExecutionStatus.SKIPPED,
                trigger_type=trigger_type,
                error_summary="Duplicate run prevented (already running)",
            )

        async with self._semaphore:
            self._running_routines.add(routine.routine_id)
            start_time = time.time()
            start_dt = datetime.now(timezone.utc)
            execution_id = f"exec_{uuid.uuid4().hex[:8]}"

            await self.event_bus.publish(
                RoutineStarted(
                    execution_id=execution_id,
                    routine_id=routine.routine_id,
                    name=routine.name,
                    trigger_type=trigger_type,
                )
            )

            execution = RoutineExecution(
                execution_id=execution_id,
                routine_id=routine.routine_id,
                started_at=start_dt,
                status=ExecutionStatus.RUNNING,
                trigger_type=trigger_type,
                action_count=len(routine.actions),
            )

            try:
                # Wrap execution in bounded timeout
                execution = await asyncio.wait_for(
                    self._run_actions(routine, execution),
                    timeout=routine.max_runtime_seconds,
                )
            except asyncio.TimeoutError:
                execution.status = ExecutionStatus.TIMEOUT
                execution.error_summary = f"Execution exceeded maximum timeout of {routine.max_runtime_seconds}s"
                execution.completed_at = datetime.now(timezone.utc)
                execution.duration_ms = round((time.time() - start_time) * 1000, 2)
                logger.error("Routine '%s' [%s] timed out after %.2fs.", routine.name, routine.routine_id, routine.max_runtime_seconds)
            except Exception as exc:
                execution.status = ExecutionStatus.FAILED
                execution.error_summary = mask_sensitive_data(str(exc))
                execution.completed_at = datetime.now(timezone.utc)
                execution.duration_ms = round((time.time() - start_time) * 1000, 2)
                logger.error("Routine '%s' [%s] failed: %s", routine.name, routine.routine_id, exc)
            finally:
                self._running_routines.discard(routine.routine_id)

            # Persist execution history safely
            def _save_exec_op(conn) -> RoutineExecution:
                r_repo = RoutineRepository(conn)
                if not r_repo.get(routine.routine_id):
                    r_repo.save(routine)
                repo = RoutineExecutionRepository(conn)
                return repo.save(execution)

            try:
                await self.db.run_async(_save_exec_op)
            except Exception as e:
                logger.warning("Failed to persist routine execution record: %s", e)

            # Compute next run time and update routine state
            now_utc = datetime.now(timezone.utc)
            next_run = None
            if routine.trigger.trigger_type != TriggerType.ONE_TIME and routine.enabled:
                next_run = self.trigger_engine.compute_next_run(routine.trigger, after_dt=now_utc)

            new_fail_count = routine.failure_count + 1 if execution.status in (ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT) else 0

            def _update_rtn_op(conn) -> bool:
                repo = RoutineRepository(conn)
                return repo.update_execution_result(
                    routine_id=routine.routine_id,
                    next_run_at=next_run,
                    last_run_at=start_dt,
                    last_status=execution.status.value,
                    failure_count=new_fail_count,
                )

            try:
                await self.db.run_async(_update_rtn_op)
            except Exception as e:
                logger.warning("Failed to update routine execution result: %s", e)

            # Emit appropriate events and notifications
            success = execution.status == ExecutionStatus.SUCCESS
            if success:
                await self.event_bus.publish(
                    RoutineCompleted(
                        execution_id=execution.execution_id,
                        routine_id=routine.routine_id,
                        name=routine.name,
                        action_count=execution.action_count,
                        duration_ms=execution.duration_ms,
                    )
                )
                await self.notifications.notify(
                    routine_id=routine.routine_id,
                    title=f"Routine Completed: {routine.name}",
                    message=f"Executed {execution.successful_actions} action(s) successfully.",
                    policy=routine.notification_policy,
                    success=True,
                )
            else:
                await self.event_bus.publish(
                    RoutineFailed(
                        execution_id=execution.execution_id,
                        routine_id=routine.routine_id,
                        name=routine.name,
                        error=execution.error_summary,
                        failed_actions=execution.failed_actions,
                    )
                )
                await self.notifications.notify(
                    routine_id=routine.routine_id,
                    title=f"Routine Failed: {routine.name}",
                    message=execution.error_summary or "Execution failed.",
                    policy=routine.notification_policy,
                    success=False,
                )

            await self.audit.log_event(
                routine_id=routine.routine_id,
                event_type="routine_executed",
                details={
                    "execution_id": execution.execution_id,
                    "status": execution.status.value,
                    "duration_ms": execution.duration_ms,
                },
            )

            return execution

    async def _run_actions(
        self,
        routine: Routine,
        execution: RoutineExecution,
    ) -> RoutineExecution:
        """Iterate through routine actions and execute them via ActionRegistry / AutomationExecutor."""
        successful_actions = 0
        failed_actions = 0
        errors = []
        start_time = time.time()

        for idx, act in enumerate(routine.actions):
            action_def = self.registry.get(act.action_name)
            if not action_def:
                # Check if it's an automation action
                action_def = self.registry.get(f"automation_{act.action_name}")

            if not action_def:
                err_msg = f"Action '{act.action_name}' is not registered in Denver ActionRegistry."
                logger.error(err_msg)
                errors.append(err_msg)
                failed_actions += 1
                break

            # Check confirmation requirement
            if routine.requires_confirmation or action_def.risk_level == CommandRiskLevel.HIGH:
                # High-risk action in unattended routine requires approval
                approval_req = await self.approval.request_approval(
                    routine_id=routine.routine_id,
                    action_summary=f"Run '{act.action_name}' for routine '{routine.name}'",
                    timeout_seconds=30.0,
                )
                execution.status = ExecutionStatus.AWAITING_CONFIRMATION
                execution.confirmation_status = "AWAITING_CONFIRMATION"
                execution.completed_at = datetime.now(timezone.utc)
                execution.duration_ms = round((time.time() - start_time) * 1000, 2)
                execution.error_summary = f"High-risk action '{act.action_name}' requires explicit confirmation."
                return execution

            # SafetyValidator check
            req = ActionRequest(
                action_name=act.action_name,
                params=act.params,
                risk_level=action_def.risk_level,
                requires_confirmation=action_def.requires_confirmation,
            )
            is_valid, reason = self.safety.validate(req)
            if not is_valid:
                err_msg = f"Action '{act.action_name}' blocked by SafetyValidator: {reason}"
                logger.warning(err_msg)
                errors.append(err_msg)
                failed_actions += 1
                await self.event_bus.publish(RoutineBlocked(routine_id=routine.routine_id, reason=reason or ""))
                break

            # Execute action
            try:
                if action_def.handler:
                    if inspect.iscoroutinefunction(action_def.handler):
                        res = await action_def.handler(act.params)
                    else:
                        res = action_def.handler(act.params)
                    if isinstance(res, ActionResult):
                        if res.success:
                            successful_actions += 1
                        else:
                            failed_actions += 1
                            errors.append(res.error or res.message)
                    else:
                        successful_actions += 1
                else:
                    # Fallback to AutomationExecutor
                    auto_res = await self.automation.execute(
                        AutomationRequest(action_name=act.action_name, params=act.params)
                    )
                    if auto_res.success:
                        successful_actions += 1
                    else:
                        failed_actions += 1
                        errors.append(auto_res.error or auto_res.message)
            except Exception as exc:
                failed_actions += 1
                errors.append(mask_sensitive_data(str(exc)))
                break

        execution.successful_actions = successful_actions
        execution.failed_actions = failed_actions
        execution.completed_at = datetime.now(timezone.utc)
        execution.duration_ms = round((time.time() - start_time) * 1000, 2)

        if failed_actions > 0:
            execution.status = ExecutionStatus.FAILED
            execution.error_summary = "; ".join(errors)
        else:
            execution.status = ExecutionStatus.SUCCESS
            execution.error_summary = ""

        return execution
