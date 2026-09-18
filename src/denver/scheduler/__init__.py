"""Denver Scheduler package for proactive intelligence and scheduled routines."""

from denver.scheduler.errors import (
    ApprovalRejectedError,
    ApprovalRequiredError,
    DuplicateRoutineError,
    ExecutionTimeoutError,
    InvalidTriggerError,
    RoutineNotFoundError,
    RoutineValidationError,
    SchedulerDisabledError,
    SchedulerError,
    SchedulerPausedError,
    TriggerIntervalTooShortError,
)
from denver.scheduler.execution_coordinator import RoutineExecutionCoordinator
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
from denver.scheduler.routine_registry import RoutineRegistry
from denver.scheduler.scheduler import DenverScheduler
from denver.scheduler.trigger_engine import TriggerEngine

from denver.scheduler.compound_routines import (
    CompoundRoutineDefinition,
    CompoundRoutineLoader,
    get_compound_routine_loader,
)

__all__ = [
    "DenverScheduler",
    "TriggerEngine",
    "RoutineRegistry",
    "RoutineExecutionCoordinator",
    "CompoundRoutineDefinition",
    "CompoundRoutineLoader",
    "get_compound_routine_loader",
    "TriggerType",
    "RoutineStatus",
    "ExecutionStatus",
    "NotificationPolicy",
    "RoutineTrigger",
    "RoutineAction",
    "Routine",
    "RoutineExecution",
    "RoutineProposal",
    "SchedulerError",
    "RoutineValidationError",
    "RoutineNotFoundError",
    "DuplicateRoutineError",
    "InvalidTriggerError",
    "TriggerIntervalTooShortError",
    "ExecutionTimeoutError",
    "ApprovalRequiredError",
    "ApprovalRejectedError",
    "SchedulerDisabledError",
    "SchedulerPausedError",
]
