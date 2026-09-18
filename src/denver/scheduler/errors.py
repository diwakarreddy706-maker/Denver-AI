"""Typed Exceptions for Denver Scheduler & Routines."""

from __future__ import annotations


class SchedulerError(Exception):
    """Base exception for all scheduler errors."""


class RoutineValidationError(SchedulerError):
    """Raised when a routine definition fails validation checks."""


class RoutineNotFoundError(SchedulerError):
    """Raised when a requested routine cannot be found."""


class DuplicateRoutineError(SchedulerError):
    """Raised when attempting to create a duplicate active routine."""


class InvalidTriggerError(SchedulerError):
    """Raised when a trigger definition is invalid or malformed."""


class TriggerIntervalTooShortError(InvalidTriggerError):
    """Raised when an interval trigger is below the safety threshold (default 300s)."""


class ExecutionTimeoutError(SchedulerError):
    """Raised when a routine exceeds its configured maximum execution runtime."""


class ApprovalRequiredError(SchedulerError):
    """Raised when an action requires explicit user confirmation before execution."""


class ApprovalRejectedError(SchedulerError):
    """Raised when a user explicitly rejects confirmation for a scheduled action."""


class SchedulerDisabledError(SchedulerError):
    """Raised when an operation is attempted while the scheduler is globally disabled."""


class SchedulerPausedError(SchedulerError):
    """Raised when an execution is attempted while the scheduler is globally paused."""
