"""Progress tracking for active task and workflow executions."""

from __future__ import annotations

from typing import Callable

from denver.tasks.models import TaskProgress, TaskStatus


class TaskProgressTracker:
    """Tracks real-time step completion and progress percentage for a task execution."""

    def __init__(
        self,
        task_id: str,
        execution_id: str,
        total_steps: int,
        on_progress: Callable[[TaskProgress], None] | None = None,
    ) -> None:
        self.task_id = task_id
        self.execution_id = execution_id
        self.total_steps = max(total_steps, 1)
        self.completed_steps = 0
        self.failed_steps = 0
        self.current_step_id: str | None = None
        self.status = TaskStatus.RUNNING
        self.message = "Task initialized"
        self._on_progress = on_progress

    def get_progress(self) -> TaskProgress:
        percent = min(100.0, (self.completed_steps / self.total_steps) * 100.0)
        return TaskProgress(
            task_id=self.task_id,
            execution_id=self.execution_id,
            percent_complete=round(percent, 1),
            current_step_id=self.current_step_id,
            completed_steps=self.completed_steps,
            total_steps=self.total_steps,
            status=self.status,
            message=self.message,
        )

    def _notify(self) -> None:
        if self._on_progress:
            try:
                self._on_progress(self.get_progress())
            except Exception:
                pass

    def step_started(self, step_id: str, description: str = "") -> None:
        self.current_step_id = step_id
        self.status = TaskStatus.RUNNING
        self.message = f"Executing step '{step_id}': {description}".strip()
        self._notify()

    def step_completed(self, step_id: str) -> None:
        self.completed_steps += 1
        self.current_step_id = None
        self.message = f"Step '{step_id}' completed successfully"
        self._notify()

    def step_failed(self, step_id: str, error: str) -> None:
        self.failed_steps += 1
        self.current_step_id = None
        self.message = f"Step '{step_id}' failed: {error}"
        self._notify()

    def task_completed(self, message: str = "Task completed successfully") -> None:
        self.status = TaskStatus.COMPLETED
        self.completed_steps = self.total_steps
        self.current_step_id = None
        self.message = message
        self._notify()

    def task_failed(self, error: str) -> None:
        self.status = TaskStatus.FAILED
        self.current_step_id = None
        self.message = f"Task failed: {error}"
        self._notify()

    def task_paused(self) -> None:
        self.status = TaskStatus.PAUSED
        self.message = "Task execution paused"
        self._notify()

    def task_resumed(self) -> None:
        self.status = TaskStatus.RUNNING
        self.message = "Task execution resumed"
        self._notify()

    def task_cancelled(self, reason: str = "Cancelled by user") -> None:
        self.status = TaskStatus.CANCELLED
        self.message = f"Task cancelled: {reason}"
        self._notify()
