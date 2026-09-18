"""Exception hierarchy for Denver Task & Workflow Orchestration."""

from __future__ import annotations


class TaskError(Exception):
    """Base exception for all task and workflow orchestration errors."""


class PlanValidationError(TaskError):
    """Raised when a task plan fails safety or structural validation."""


class CircularDependencyError(PlanValidationError):
    """Raised when a task plan contains circular dependencies in its step DAG."""


class MaxStepsExceededError(PlanValidationError):
    """Raised when a task plan exceeds the maximum allowed number of steps."""


class MaxDepthExceededError(PlanValidationError):
    """Raised when a task plan exceeds the maximum allowed DAG dependency depth."""


class ActionNotFoundError(PlanValidationError):
    """Raised when a task step references an unknown or unregistered action."""


class InvalidStepDependencyError(PlanValidationError):
    """Raised when a task step depends on a non-existent step ID."""


class TaskExecutionError(TaskError):
    """Raised during the runtime execution of a task plan."""


class StepExecutionError(TaskExecutionError):
    """Raised when an individual task step fails during execution."""


class StepExecutionTimeoutError(StepExecutionError):
    """Raised when an individual task step exceeds its configured timeout."""


class TaskExecutionTimeoutError(TaskExecutionError):
    """Raised when overall task execution exceeds the plan timeout."""


class TaskCancelledError(TaskExecutionError):
    """Raised when a task execution is cancelled by user or system."""


class TaskPausedError(TaskExecutionError):
    """Raised when a task execution is paused."""


class TaskApprovalRequiredError(TaskError):
    """Raised when a step requires manual confirmation before execution."""


class TaskApprovalRejectedError(TaskError):
    """Raised when a requested approval is rejected by the user."""


class TaskConcurrencyLimitExceededError(TaskError):
    """Raised when the maximum concurrent task execution limit is reached."""


class TaskDisabledError(TaskError):
    """Raised when task orchestration is globally disabled."""


class TaskNotFoundError(TaskError):
    """Raised when a requested task ID is not found."""


class PlanNotFoundError(TaskError):
    """Raised when a requested plan ID is not found."""
