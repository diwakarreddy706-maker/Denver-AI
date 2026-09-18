"""Core DAG workflow execution engine for Denver tasks."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from denver.automation.executor import AutomationExecutor
from denver.commands.models import ActionRequest
from denver.commands.registry import ActionRegistry
from denver.commands.safety import SafetyValidator
from denver.logging.logger import get_logger
from denver.runtime.events import (
    DenverEvent,
    TaskCancelled,
    TaskCompleted,
    TaskFailed,
    TaskPaused,
    TaskProgressUpdated,
    TaskResumed,
    TaskStarted,
    TaskStepCompleted,
    TaskStepFailed,
    TaskStepStarted,
)
from denver.tasks.approval import TaskApprovalManager
from denver.tasks.audit import TaskAuditLogger
from denver.tasks.cancellation import CancellationToken
from denver.tasks.errors import (
    ActionNotFoundError,
    PlanValidationError,
    StepExecutionError,
    StepExecutionTimeoutError,
    TaskApprovalRejectedError,
    TaskApprovalRequiredError,
    TaskCancelledError,
    TaskExecutionTimeoutError,
    TaskPausedError,
)
from denver.tasks.models import (
    FailurePolicy,
    StepExecution,
    StepStatus,
    TaskExecution,
    TaskPlan,
    TaskProgress,
    TaskResult,
    TaskStatus,
    TaskStep,
)
from denver.tasks.persistence import TaskPersistence
from denver.tasks.progress import TaskProgressTracker
from denver.tasks.retry import TaskRetryPolicy

logger = get_logger("tasks.engine")


class WorkflowEngine:
    """Executes validated DAG task plans with bounded concurrency, step-level safety revalidation,

    timeout enforcement, cooperative pause/cancellation, and audit telemetry.
    """

    def __init__(
        self,
        action_registry: ActionRegistry,
        safety_validator: SafetyValidator,
        automation_executor: AutomationExecutor,
        persistence: TaskPersistence | None = None,
        approval_manager: TaskApprovalManager | None = None,
        audit_logger: TaskAuditLogger | None = None,
        event_publisher: Callable[[DenverEvent], None] | None = None,
        max_concurrency: int = 2,
    ) -> None:
        self.action_registry = action_registry
        self.safety_validator = safety_validator
        self.automation_executor = automation_executor
        self.persistence = persistence
        self.approval_manager = approval_manager or TaskApprovalManager()
        self.audit_logger = audit_logger or TaskAuditLogger()
        self.event_publisher = event_publisher
        self.max_concurrency = max_concurrency
        self.retry_policy = TaskRetryPolicy(max_retries=1)

    def _emit_event(self, event: DenverEvent) -> None:
        if self.event_publisher:
            try:
                res = self.event_publisher(event)
                if asyncio.iscoroutine(res):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(res)
                    except RuntimeError:
                        pass
            except Exception as exc:
                logger.warning("Failed to publish task event %s: %s", type(event).__name__, exc)

    async def execute_plan(
        self,
        plan: TaskPlan,
        cancellation_token: CancellationToken | None = None,
        on_progress: Callable[[TaskProgress], None] | None = None,
    ) -> TaskResult:
        """Execute a validated TaskPlan to completion or failure."""
        start_time = time.perf_counter()
        execution_id = f"exec_{uuid.uuid4().hex[:10]}"
        token = cancellation_token or CancellationToken(plan.task_id)

        tracker = TaskProgressTracker(
            task_id=plan.task_id,
            execution_id=execution_id,
            total_steps=len(plan.steps),
            on_progress=lambda p: self._handle_progress_update(p, on_progress),
        )

        task_exec = TaskExecution(
            execution_id=execution_id,
            task_id=plan.task_id,
            plan_id=plan.plan_id,
            status=TaskStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )

        if self.persistence:
            try:
                self.persistence.create_execution(task_exec)
                self.persistence.update_task_status(plan.task_id, TaskStatus.RUNNING, current_plan_id=plan.plan_id)
            except Exception as exc:
                logger.warning("Error saving initial task execution: %s", exc)

        self.audit_logger.log(
            task_id=plan.task_id,
            event_type="TASK_STARTED",
            actor="WorkflowEngine",
            details={"execution_id": execution_id, "plan_id": plan.plan_id, "steps_count": len(plan.steps)},
        )

        self._emit_event(TaskStarted(task_id=plan.task_id, plan_id=plan.plan_id))

        # Overall task timeout wrapper
        try:
            result = await asyncio.wait_for(
                self._run_dag(plan, task_exec, token, tracker),
                timeout=plan.timeout_seconds,
            )
            return result
        except asyncio.TimeoutError:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            error_msg = f"Task plan '{plan.plan_id}' exceeded overall timeout of {plan.timeout_seconds}s"
            logger.error(error_msg)
            tracker.task_failed(error_msg)
            self._finalize_execution(task_exec, TaskStatus.FAILED, error_summary=error_msg)
            self.audit_logger.log(plan.task_id, "TASK_TIMED_OUT", details={"execution_id": execution_id, "error": error_msg})
            self._emit_event(TaskFailed(task_id=plan.task_id, execution_id=execution_id, error=error_msg))
            return TaskResult(
                task_id=plan.task_id,
                execution_id=execution_id,
                status=TaskStatus.FAILED,
                steps_completed=tracker.completed_steps,
                steps_failed=tracker.failed_steps + 1,
                steps_total=len(plan.steps),
                duration_ms=duration_ms,
                error_message=error_msg,
            )
        except TaskCancelledError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            tracker.task_cancelled(str(exc))
            self._finalize_execution(task_exec, TaskStatus.CANCELLED, error_summary=str(exc))
            self.audit_logger.log(plan.task_id, "TASK_CANCELLED", details={"execution_id": execution_id, "reason": str(exc)})
            self._emit_event(TaskCancelled(task_id=plan.task_id, execution_id=execution_id, reason=str(exc)))
            return TaskResult(
                task_id=plan.task_id,
                execution_id=execution_id,
                status=TaskStatus.CANCELLED,
                steps_completed=tracker.completed_steps,
                steps_failed=tracker.failed_steps,
                steps_total=len(plan.steps),
                duration_ms=duration_ms,
                error_message=str(exc),
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            error_msg = f"Unexpected error during task execution: {exc}"
            logger.exception(error_msg)
            tracker.task_failed(error_msg)
            self._finalize_execution(task_exec, TaskStatus.FAILED, error_summary=error_msg)
            self.audit_logger.log(plan.task_id, "TASK_FAILED", details={"execution_id": execution_id, "error": error_msg})
            self._emit_event(TaskFailed(task_id=plan.task_id, execution_id=execution_id, error=error_msg))
            return TaskResult(
                task_id=plan.task_id,
                execution_id=execution_id,
                status=TaskStatus.FAILED,
                steps_completed=tracker.completed_steps,
                steps_failed=tracker.failed_steps + 1,
                steps_total=len(plan.steps),
                duration_ms=duration_ms,
                error_message=error_msg,
            )

    def _handle_progress_update(
        self,
        progress: TaskProgress,
        custom_callback: Callable[[TaskProgress], None] | None,
    ) -> None:
        self._emit_event(
            TaskProgressUpdated(
                task_id=progress.task_id,
                execution_id=progress.execution_id,
                completed_steps=progress.completed_steps,
                total_steps=progress.total_steps,
                progress_percent=progress.percent_complete,
                current_step_name=progress.current_step_id or "",
            )
        )
        if custom_callback:
            try:
                custom_callback(progress)
            except Exception:
                pass

    async def _run_dag(
        self,
        plan: TaskPlan,
        task_exec: TaskExecution,
        token: CancellationToken,
        tracker: TaskProgressTracker,
    ) -> TaskResult:
        """Run steps in DAG order with bounded concurrency."""
        start_time = time.perf_counter()
        concurrency = min(plan.concurrency_limit, self.max_concurrency)
        sem = asyncio.Semaphore(concurrency)

        step_map: dict[str, TaskStep] = {s.step_id: s for s in plan.steps}
        step_statuses: dict[str, StepStatus] = {s.step_id: StepStatus.PENDING for s in plan.steps}
        step_results: dict[str, dict[str, Any]] = {}
        step_errors: dict[str, str] = {}
        running_tasks: dict[str, asyncio.Task[None]] = {}

        while True:
            await token.check_pause_and_cancellation()

            # Find ready steps whose dependencies are all COMPLETED
            ready_step_ids: list[str] = []
            for step_id, status in step_statuses.items():
                if status == StepStatus.PENDING:
                    deps = step_map[step_id].depends_on
                    if all(step_statuses.get(d) == StepStatus.COMPLETED for d in deps):
                        ready_step_ids.append(step_id)
                    elif any(step_statuses.get(d) in (StepStatus.FAILED, StepStatus.SKIPPED, StepStatus.CANCELLED) for d in deps):
                        # Dependency failed
                        if plan.failure_policy == FailurePolicy.CONTINUE_ON_FAILURE:
                            # If continue on failure, run anyway if ready
                            ready_step_ids.append(step_id)
                        else:
                            step_statuses[step_id] = StepStatus.SKIPPED

            # Launch ready steps
            for step_id in ready_step_ids:
                if step_id not in running_tasks:
                    step_statuses[step_id] = StepStatus.RUNNING
                    t = asyncio.create_task(
                        self._execute_single_step(
                            step=step_map[step_id],
                            task_exec=task_exec,
                            sem=sem,
                            token=token,
                            tracker=tracker,
                            step_statuses=step_statuses,
                            step_results=step_results,
                            step_errors=step_errors,
                            failure_policy=plan.failure_policy,
                        )
                    )
                    running_tasks[step_id] = t

            # If no tasks are running and no pending tasks can be scheduled, we are done
            if not running_tasks:
                break

            # Wait for at least one running step task to complete
            done, _ = await asyncio.wait(
                running_tasks.values(),
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cleanup finished tasks
            completed_step_ids = [
                s_id for s_id, t in running_tasks.items() if t in done
            ]
            for s_id in completed_step_ids:
                del running_tasks[s_id]

            # If any step failed and policy is STOP_ON_FAILURE or RETRY_THEN_STOP, break
            if plan.failure_policy in (FailurePolicy.STOP_ON_FAILURE, FailurePolicy.RETRY_THEN_STOP):
                if any(st == StepStatus.FAILED for st in step_statuses.values()):
                    # Cancel any remaining running step tasks
                    for t in running_tasks.values():
                        t.cancel()
                    break

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        # Determine overall status
        failed_count = sum(1 for st in step_statuses.values() if st == StepStatus.FAILED)
        completed_count = sum(1 for st in step_statuses.values() if st == StepStatus.COMPLETED)

        if failed_count > 0:
            overall_status = TaskStatus.FAILED
            error_summary = "; ".join(f"{s_id}: {err}" for s_id, err in step_errors.items())
            tracker.task_failed(error_summary)
            self._finalize_execution(task_exec, overall_status, error_summary=error_summary, result_data=step_results)
            self.audit_logger.log(plan.task_id, "TASK_FAILED", details={"errors": step_errors})
            self._emit_event(
                TaskFailed(
                    execution_id=task_exec.execution_id,
                    task_id=plan.task_id,
                    error=error_summary,
                    completed_steps=completed_count,
                    total_steps=len(plan.steps),
                )
            )
        else:
            overall_status = TaskStatus.COMPLETED
            tracker.task_completed("All workflow steps completed successfully")
            self._finalize_execution(task_exec, overall_status, result_data=step_results)
            self.audit_logger.log(plan.task_id, "TASK_COMPLETED", details={"steps_completed": completed_count})
            self._emit_event(
                TaskCompleted(
                    execution_id=task_exec.execution_id,
                    task_id=plan.task_id,
                    completed_steps=completed_count,
                    total_steps=len(plan.steps),
                    duration_ms=duration_ms,
                )
            )

        return TaskResult(
            task_id=plan.task_id,
            execution_id=task_exec.execution_id,
            status=overall_status,
            steps_completed=completed_count,
            steps_failed=failed_count,
            steps_total=len(plan.steps),
            duration_ms=duration_ms,
            error_message="; ".join(step_errors.values()) if step_errors else "",
            data=step_results,
        )

    async def _execute_single_step(
        self,
        step: TaskStep,
        task_exec: TaskExecution,
        sem: asyncio.Semaphore,
        token: CancellationToken,
        tracker: TaskProgressTracker,
        step_statuses: dict[str, StepStatus],
        step_results: dict[str, dict[str, Any]],
        step_errors: dict[str, str],
        failure_policy: FailurePolicy,
    ) -> None:
        """Execute a single step within concurrency semaphore and safety bounds."""
        async with sem:
            await token.check_pause_and_cancellation()

            step_exec_id = f"sexec_{uuid.uuid4().hex[:10]}"
            step_exec = StepExecution(
                step_execution_id=step_exec_id,
                execution_id=task_exec.execution_id,
                step_id=step.step_id,
                status=StepStatus.RUNNING,
                started_at=datetime.now(timezone.utc),
            )

            if self.persistence:
                try:
                    self.persistence.save_step_execution(step_exec)
                except Exception as exc:
                    logger.warning("Error creating step execution record: %s", exc)

            tracker.step_started(step.step_id, step.description)
            self.audit_logger.log(
                task_id=task_exec.task_id,
                event_type="STEP_STARTED",
                details={"step_id": step.step_id, "action_name": step.action_name},
            )
            self._emit_event(TaskStepStarted(task_id=task_exec.task_id, step_id=step.step_id, action_name=step.action_name))

            step_start = time.perf_counter()
            attempts = 0
            max_attempts = 2 if failure_policy == FailurePolicy.RETRY_THEN_STOP and self.retry_policy.is_safe_action(step.action_name) else 1

            while attempts < max_attempts:
                attempts += 1
                try:
                    await token.check_pause_and_cancellation()

                    # -------------------------------------------------------------
                    # MANDATORY NON-NEGOTIABLE SAFETY PIPELINE:
                    # 1. Check approval requirement
                    # 2. SafetyValidator.validate(request)
                    # 3. ActionRegistry.get(action_name)
                    # 4. AutomationExecutor.execute(request)
                    # -------------------------------------------------------------

                    if step.requires_approval:
                        # Check or request approval
                        appr_id = self.approval_manager.request_approval(
                            task_id=task_exec.task_id,
                            step_id=step.step_id,
                            plan_id=task_exec.plan_id,
                            action_name=step.action_name,
                            params=step.params,
                        )
                        # Await approval with timeout
                        approved = await self.approval_manager.wait_for_decision(appr_id, timeout_seconds=step.timeout_seconds)
                        if not approved:
                            raise TaskApprovalRejectedError(f"Step '{step.step_id}' approval was rejected or timed out.")

                    req = ActionRequest(action_name=step.action_name, params=step.params)
                    is_safe, reason = self.safety_validator.validate(req)
                    if not is_safe:
                        raise StepExecutionError(f"Pre-execution safety validation rejected step: {reason}")

                    action = self.action_registry.get(step.action_name)
                    if not action:
                        raise ActionNotFoundError(f"Action '{step.action_name}' not found in registry.")

                    # Execute via AutomationExecutor / Handler with step timeout
                    exec_success = False
                    exec_output = ""
                    exec_data: dict[str, Any] = {}
                    exec_err: str | None = None

                    if self.automation_executor:
                        from denver.automation.models import AutomationRequest
                        auto_req = AutomationRequest(action_name=step.action_name, params=step.params)
                        exec_res = await asyncio.wait_for(
                            self.automation_executor.execute(auto_req),
                            timeout=step.timeout_seconds,
                        )
                        exec_success = exec_res.success
                        exec_output = getattr(exec_res, "message", getattr(exec_res, "output", ""))
                        exec_data = getattr(exec_res, "data", {})
                        exec_err = getattr(exec_res, "error", None)
                    elif action.handler:
                        import inspect
                        res = action.handler(step.params)
                        if inspect.isawaitable(res):
                            res = await asyncio.wait_for(res, timeout=step.timeout_seconds)
                        if isinstance(res, str):
                            exec_success = True
                            exec_output = res
                        elif hasattr(res, "success"):
                            exec_success = res.success
                            exec_output = getattr(res, "message", getattr(res, "output", ""))
                            exec_data = getattr(res, "data", {})
                            exec_err = getattr(res, "error", None)
                        else:
                            exec_success = True
                            exec_output = str(res)
                    else:
                        exec_success = True
                        exec_output = f"Executed {step.action_name}"

                    duration_ms = (time.perf_counter() - step_start) * 1000.0

                    if exec_success:
                        step_statuses[step.step_id] = StepStatus.COMPLETED
                        step_results[step.step_id] = {
                            "success": True,
                            "output": exec_output,
                            "data": exec_data,
                        }
                        step_exec.status = StepStatus.COMPLETED
                        step_exec.completed_at = datetime.now(timezone.utc)
                        step_exec.attempt_count = attempts
                        step_exec.result_data = step_results[step.step_id]
                        step_exec.duration_ms = duration_ms

                        if self.persistence:
                            try:
                                self.persistence.save_step_execution(step_exec)
                            except Exception:
                                pass

                        tracker.step_completed(step.step_id)
                        self.audit_logger.log(
                            task_id=task_exec.task_id,
                            event_type="STEP_COMPLETED",
                            details={"step_id": step.step_id, "duration_ms": duration_ms},
                        )
                        self._emit_event(
                            TaskStepCompleted(
                                execution_id=task_exec.execution_id,
                                task_id=task_exec.task_id,
                                step_id=step.step_id,
                                action_name=step.action_name,
                                latency_ms=duration_ms,
                            )
                        )
                        return
                    else:
                        raise StepExecutionError(exec_err or "Step action failed execution")

                except asyncio.TimeoutError:
                    err_msg = f"Step '{step.step_id}' exceeded timeout of {step.timeout_seconds}s"
                    logger.warning(err_msg)
                    if attempts >= max_attempts:
                        self._fail_step(step, step_exec, err_msg, time.perf_counter() - step_start, attempts, step_statuses, step_errors, tracker, task_exec)
                        return
                except TaskCancelledError:
                    raise
                except Exception as exc:
                    err_msg = str(exc)
                    logger.warning("Step '%s' attempt %d failed: %s", step.step_id, attempts, err_msg)
                    if attempts >= max_attempts:
                        self._fail_step(step, step_exec, err_msg, time.perf_counter() - step_start, attempts, step_statuses, step_errors, tracker, task_exec)
                        return

    def _fail_step(
        self,
        step: TaskStep,
        step_exec: StepExecution,
        error_msg: str,
        duration_s: float,
        attempts: int,
        step_statuses: dict[str, StepStatus],
        step_errors: dict[str, str],
        tracker: TaskProgressTracker,
        task_exec: TaskExecution,
    ) -> None:
        duration_ms = duration_s * 1000.0
        step_statuses[step.step_id] = StepStatus.FAILED
        step_errors[step.step_id] = error_msg
        step_exec.status = StepStatus.FAILED
        step_exec.completed_at = datetime.now(timezone.utc)
        step_exec.attempt_count = attempts
        step_exec.error_message = error_msg
        step_exec.duration_ms = duration_ms

        if self.persistence:
            try:
                self.persistence.save_step_execution(step_exec)
            except Exception:
                pass

        tracker.step_failed(step.step_id, error_msg)
        self.audit_logger.log(
            task_id=task_exec.task_id,
            event_type="STEP_FAILED",
            details={"step_id": step.step_id, "error": error_msg, "duration_ms": duration_ms},
        )
        self._emit_event(TaskStepFailed(task_id=task_exec.task_id, step_id=step.step_id, error=error_msg))

    def _finalize_execution(
        self,
        task_exec: TaskExecution,
        status: TaskStatus,
        error_summary: str = "",
        result_data: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        task_exec.status = status
        task_exec.completed_at = now
        task_exec.error_summary = error_summary
        if result_data:
            task_exec.result_data = result_data

        if self.persistence:
            try:
                self.persistence.update_execution(
                    execution_id=task_exec.execution_id,
                    status=status,
                    completed_at=now,
                    error_summary=error_summary,
                    result_data=result_data,
                )
                self.persistence.update_task_status(task_exec.task_id, status)
            except Exception as exc:
                logger.warning("Error finalizing task execution in DB: %s", exc)
