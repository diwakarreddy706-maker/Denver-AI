"""High-level Task Registry managing lifecycle, concurrency, and execution state."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable

from denver.logging.logger import get_logger
from denver.tasks.approval import TaskApprovalManager
from denver.tasks.audit import TaskAuditLogger
from denver.tasks.cancellation import CancellationManager
from denver.tasks.errors import (
    PlanNotFoundError,
    TaskConcurrencyLimitExceededError,
    TaskDisabledError,
    TaskNotFoundError,
)
from denver.tasks.models import (
    FailurePolicy,
    Task,
    TaskExecution,
    TaskOrigin,
    TaskPlan,
    TaskPriority,
    TaskProgress,
    TaskProposal,
    TaskResult,
    TaskStatus,
)
from denver.tasks.persistence import TaskPersistence
from denver.tasks.plan_validator import PlanValidator
from denver.tasks.planner import TaskPlanner
from denver.tasks.workflow_engine import WorkflowEngine

logger = get_logger("tasks.registry")


class TaskRegistry:
    """Unified service and registry for orchestrating tasks and multi-step workflows."""

    def __init__(
        self,
        engine: WorkflowEngine,
        persistence: TaskPersistence,
        planner: TaskPlanner | None = None,
        validator: PlanValidator | None = None,
        approval_manager: TaskApprovalManager | None = None,
        audit_logger: TaskAuditLogger | None = None,
        enabled: bool = True,
        max_concurrent_tasks: int = 2,
    ) -> None:
        self.engine = engine
        self.persistence = persistence
        self.validator = validator or PlanValidator()
        self.planner = planner or TaskPlanner(self.validator)
        self.approval_manager = approval_manager or engine.approval_manager
        self.audit_logger = audit_logger or engine.audit_logger
        self.cancellation_manager = CancellationManager()
        self.enabled = enabled
        self.max_concurrent_tasks = max_concurrent_tasks
        self.is_global_paused = False

        self._active_tasks: dict[str, asyncio.Task[TaskResult]] = {}

    def create_task(
        self,
        title: str,
        description: str = "",
        origin: TaskOrigin = TaskOrigin.USER_CHAT,
        priority: TaskPriority = TaskPriority.MEDIUM,
    ) -> Task:
        """Create and persist a new task in DRAFT state."""
        if not self.enabled:
            raise TaskDisabledError("Task orchestration is currently disabled.")

        task_id = f"task_{uuid.uuid4().hex[:10]}"
        task = Task(
            task_id=task_id,
            title=title,
            description=description,
            origin=origin,
            priority=priority,
            status=TaskStatus.DRAFT,
        )
        saved = self.persistence.create_task(task)
        self.audit_logger.log(
            task_id=task_id,
            event_type="TASK_CREATED",
            actor=origin.value,
            details={"title": title, "priority": priority.value},
        )
        return saved

    def create_task_from_proposal(
        self,
        proposal: TaskProposal,
        origin: TaskOrigin = TaskOrigin.USER_CHAT,
        priority: TaskPriority = TaskPriority.MEDIUM,
    ) -> tuple[Task, TaskPlan]:
        """Create a task and its initial plan from an untrusted proposal."""
        task = self.create_task(
            title=proposal.task_title,
            description=proposal.task_description,
            origin=origin,
            priority=priority,
        )
        plan = self.plan_task(task.task_id, proposal)
        return task, plan

    def register_task_from_proposal(
        self,
        proposal: TaskProposal,
        origin: TaskOrigin = TaskOrigin.USER_CHAT,
        priority: TaskPriority = TaskPriority.MEDIUM,
    ) -> Task:
        """Convenience method returning the registered task entity with associated plan."""
        task, _ = self.create_task_from_proposal(proposal, origin=origin, priority=priority)
        return task

    def plan_task(
        self,
        task_id: str,
        actions_or_proposal: list[dict[str, Any]] | TaskProposal | str,
        failure_policy: FailurePolicy = FailurePolicy.STOP_ON_FAILURE,
    ) -> TaskPlan:
        """Generate and associate a validated TaskPlan with a task."""
        if not self.enabled:
            raise TaskDisabledError("Task orchestration is currently disabled.")

        task = self.persistence.get_task(task_id)
        if not task:
            raise TaskNotFoundError(f"Task '{task_id}' not found.")

        if isinstance(actions_or_proposal, list):
            plan = self.planner.plan_from_action_list(task_id, actions_or_proposal, failure_policy)
        elif isinstance(actions_or_proposal, TaskProposal):
            plan = self.planner.create_plan_from_proposal(task_id, actions_or_proposal)
        elif isinstance(actions_or_proposal, str):
            plan = self.planner.parse_ai_response(task_id, actions_or_proposal)
        else:
            raise ValueError("Unsupported proposal type for planning task.")

        self.persistence.save_plan(plan)
        self.persistence.update_task_status(task_id, TaskStatus.READY, current_plan_id=plan.plan_id)
        self.audit_logger.log(
            task_id=task_id,
            event_type="PLAN_CREATED",
            actor="TaskPlanner",
            details={"plan_id": plan.plan_id, "steps_count": len(plan.steps)},
        )
        return plan

    async def run_task(
        self,
        task_id: str,
        plan_id: str | None = None,
        on_progress: Callable[[TaskProgress], None] | None = None,
    ) -> TaskResult:
        """Execute a task plan asynchronously."""
        if not self.enabled:
            raise TaskDisabledError("Task orchestration is currently disabled.")

        if self.is_global_paused:
            raise TaskDisabledError("All task executions are globally paused.")

        task = self.persistence.get_task(task_id)
        if not task:
            raise TaskNotFoundError(f"Task '{task_id}' not found.")

        target_plan_id = plan_id or task.current_plan_id
        if not target_plan_id:
            raise PlanNotFoundError(f"Task '{task_id}' has no associated plan to execute.")

        plan = self.persistence.get_plan(target_plan_id)
        if not plan:
            raise PlanNotFoundError(f"Plan '{target_plan_id}' not found.")

        # Concurrency limit check
        if len(self._active_tasks) >= self.max_concurrent_tasks:
            raise TaskConcurrencyLimitExceededError(
                f"Active task execution count ({len(self._active_tasks)}) reached limit ({self.max_concurrent_tasks})."
            )

        token = self.cancellation_manager.get_or_create(task_id)

        async def _execution_wrapper() -> TaskResult:
            try:
                res = await self.engine.execute_plan(plan, token, on_progress)
                return res
            finally:
                self._active_tasks.pop(task_id, None)
                self.cancellation_manager.remove(task_id)

        coro = _execution_wrapper()
        async_task = asyncio.create_task(coro)
        self._active_tasks[task_id] = async_task

        return await async_task

    def pause_task(self, task_id: str) -> bool:
        """Pause execution of a running task."""
        task = self.persistence.get_task(task_id)
        if not task:
            return False
        token = self.cancellation_manager.get_or_create(task_id)
        token.pause()
        self.persistence.update_task_status(task_id, TaskStatus.PAUSED)
        self.audit_logger.log(task_id, "TASK_PAUSED", actor="user")
        return True

    def resume_task(self, task_id: str) -> bool:
        """Resume execution of a paused task."""
        task = self.persistence.get_task(task_id)
        if not task:
            return False
        token = self.cancellation_manager.get_or_create(task_id)
        token.resume()
        self.persistence.update_task_status(task_id, TaskStatus.RUNNING)
        self.audit_logger.log(task_id, "TASK_RESUMED", actor="user")
        return True

    def cancel_task(self, task_id: str, reason: str = "User cancelled task") -> bool:
        """Cancel execution of an active or pending task."""
        task = self.persistence.get_task(task_id)
        if not task:
            return False
        success = self.cancellation_manager.cancel_task(task_id, reason=reason)
        self.persistence.update_task_status(task_id, TaskStatus.CANCELLED)
        self.audit_logger.log(task_id, "TASK_CANCELLED", actor="user", details={"reason": reason})
        return True

    def pause_all_tasks(self) -> None:
        """Globally pause all active tasks."""
        self.is_global_paused = True
        for task_id in list(self._active_tasks.keys()):
            self.pause_task(task_id)
        logger.info("All active tasks paused globally.")

    def resume_all_tasks(self) -> None:
        """Resume all tasks from global pause."""
        self.is_global_paused = False
        for task_id in list(self._active_tasks.keys()):
            self.resume_task(task_id)
        logger.info("All active tasks resumed globally.")

    def delete_task(self, task_id: str) -> bool:
        """Delete task and its historical records."""
        self.cancel_task(task_id, reason="Task deleted")
        return self.persistence.delete_task(task_id)

    def get_task(self, task_id: str) -> Task | None:
        return self.persistence.get_task(task_id)

    def get_plan(self, plan_id: str) -> TaskPlan | None:
        return self.persistence.get_plan(plan_id)

    def list_tasks(self, status: TaskStatus | None = None, limit: int = 50) -> list[Task]:
        return self.persistence.list_tasks(status=status, limit=limit)

    def get_task_history(self, task_id: str, limit: int = 20) -> list[TaskExecution]:
        return self.persistence.list_executions_for_task(task_id, limit=limit)

    def get_audit_trail(self, task_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return self.audit_logger.get_audit_trail(task_id, limit=limit)

    def approve_step(self, approval_id: str) -> bool:
        return self.approval_manager.approve(approval_id)

    def reject_step(self, approval_id: str, reason: str = "User rejected confirmation") -> bool:
        return self.approval_manager.reject(approval_id, reason=reason)

    def get_pending_approvals(self, task_id: str | None = None) -> list[dict[str, Any]]:
        return self.approval_manager.get_pending_approvals(task_id)

    def get_active_count(self) -> int:
        return len(self._active_tasks)

    def enable(self) -> None:
        self.enabled = True
        logger.info("Task orchestration enabled.")

    def disable(self) -> None:
        self.enabled = False
        self.pause_all_tasks()
        logger.info("Task orchestration disabled.")
