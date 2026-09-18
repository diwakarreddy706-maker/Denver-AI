"""Domain models and data structures for Denver Task & Workflow Orchestration."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    """Lifecycle states of a task and its execution."""

    DRAFT = "draft"
    PLANNING = "planning"
    PENDING_APPROVAL = "pending_approval"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class StepStatus(str, Enum):
    """Execution status for individual workflow steps."""

    PENDING = "pending"
    READY = "ready"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class FailurePolicy(str, Enum):
    """Policy for handling step failures within a workflow DAG."""

    STOP_ON_FAILURE = "stop_on_failure"
    CONTINUE_ON_FAILURE = "continue_on_failure"
    RETRY_THEN_STOP = "retry_then_stop"


class TaskOrigin(str, Enum):
    """Origin of the task request."""

    USER_CHAT = "user_chat"
    USER_ROUTINE = "user_routine"
    SYSTEM = "system"
    API = "api"


class TaskPriority(str, Enum):
    """Priority level for task scheduling and concurrency."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class TaskStep:
    """Immutable representation of a single executable step in a workflow plan."""

    step_id: str
    action_name: str
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    timeout_seconds: float = 60.0
    requires_approval: bool = False
    description: str = ""

    @property
    def id(self) -> str:
        return self.step_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action_name": self.action_name,
            "params": self.params,
            "depends_on": self.depends_on,
            "timeout_seconds": self.timeout_seconds,
            "requires_approval": self.requires_approval,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskStep:
        params = data.get("params")
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {}
        depends_on = data.get("depends_on")
        if isinstance(depends_on, str):
            try:
                depends_on = json.loads(depends_on)
            except Exception:
                depends_on = []
        return cls(
            step_id=str(data["step_id"]),
            action_name=str(data["action_name"]),
            params=params or {},
            depends_on=list(depends_on or []),
            timeout_seconds=float(data.get("timeout_seconds", 60.0)),
            requires_approval=bool(data.get("requires_approval", False)),
            description=str(data.get("description", "")),
        )


@dataclass(frozen=True)
class TaskPlan:
    """Immutable DAG plan for executing a workflow task."""

    plan_id: str
    task_id: str
    steps: list[TaskStep] = field(default_factory=list)
    status: str = "proposed"
    failure_policy: FailurePolicy = FailurePolicy.STOP_ON_FAILURE
    max_retries: int = 1
    timeout_seconds: float = 600.0
    concurrency_limit: int = 2
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def id(self) -> str:
        return self.plan_id

    def get_step(self, step_id: str) -> TaskStep | None:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status,
            "failure_policy": self.failure_policy.value if isinstance(self.failure_policy, FailurePolicy) else str(self.failure_policy),
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
            "concurrency_limit": self.concurrency_limit,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else str(self.created_at),
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else str(self.updated_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskPlan:
        steps_raw = data.get("steps", [])
        steps = [TaskStep.from_dict(s) if isinstance(s, dict) else s for s in steps_raw]
        policy_raw = data.get("failure_policy", FailurePolicy.STOP_ON_FAILURE.value)
        try:
            failure_policy = FailurePolicy(policy_raw)
        except ValueError:
            failure_policy = FailurePolicy.STOP_ON_FAILURE
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif not isinstance(created_at, datetime):
            created_at = datetime.now(timezone.utc)
        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif not isinstance(updated_at, datetime):
            updated_at = datetime.now(timezone.utc)
        return cls(
            plan_id=str(data["plan_id"]),
            task_id=str(data["task_id"]),
            steps=steps,
            status=str(data.get("status", "proposed")),
            failure_policy=failure_policy,
            max_retries=int(data.get("max_retries", 1)),
            timeout_seconds=float(data.get("timeout_seconds", 600.0)),
            concurrency_limit=int(data.get("concurrency_limit", 2)),
            created_at=created_at,
            updated_at=updated_at,
        )


@dataclass
class Task:
    """Top-level task entity tracking status and active plan."""

    task_id: str
    title: str
    description: str = ""
    origin: TaskOrigin = TaskOrigin.USER_CHAT
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.DRAFT
    current_plan_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def id(self) -> str:
        return self.task_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "origin": self.origin.value if isinstance(self.origin, TaskOrigin) else str(self.origin),
            "priority": self.priority.value if isinstance(self.priority, TaskPriority) else str(self.priority),
            "status": self.status.value if isinstance(self.status, TaskStatus) else str(self.status),
            "current_plan_id": self.current_plan_id,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else str(self.created_at),
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else str(self.updated_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        origin_raw = data.get("origin", TaskOrigin.USER_CHAT.value)
        try:
            origin = TaskOrigin(origin_raw)
        except ValueError:
            origin = TaskOrigin.USER_CHAT
        prio_raw = data.get("priority", TaskPriority.MEDIUM.value)
        try:
            priority = TaskPriority(prio_raw)
        except ValueError:
            priority = TaskPriority.MEDIUM
        status_raw = data.get("status", TaskStatus.DRAFT.value)
        try:
            status = TaskStatus(status_raw)
        except ValueError:
            status = TaskStatus.DRAFT
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif not isinstance(created_at, datetime):
            created_at = datetime.now(timezone.utc)
        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif not isinstance(updated_at, datetime):
            updated_at = datetime.now(timezone.utc)
        return cls(
            task_id=str(data["task_id"]),
            title=str(data["title"]),
            description=str(data.get("description", "")),
            origin=origin,
            priority=priority,
            status=status,
            current_plan_id=data.get("current_plan_id"),
            created_at=created_at,
            updated_at=updated_at,
        )


@dataclass
class StepExecution:
    """Execution telemetry and record for a single workflow step."""

    step_execution_id: str
    execution_id: str
    step_id: str
    status: StepStatus = StepStatus.PENDING
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    attempt_count: int = 0
    result_data: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_execution_id": self.step_execution_id,
            "execution_id": self.execution_id,
            "step_id": self.step_id,
            "status": self.status.value if isinstance(self.status, StepStatus) else str(self.status),
            "started_at": self.started_at.isoformat() if isinstance(self.started_at, datetime) else str(self.started_at),
            "completed_at": self.completed_at.isoformat() if isinstance(self.completed_at, datetime) else (str(self.completed_at) if self.completed_at else None),
            "attempt_count": self.attempt_count,
            "result_data": self.result_data,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StepExecution:
        status_raw = data.get("status", StepStatus.PENDING.value)
        try:
            status = StepStatus(status_raw)
        except ValueError:
            status = StepStatus.PENDING
        started_at = data.get("started_at")
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)
        elif not isinstance(started_at, datetime):
            started_at = datetime.now(timezone.utc)
        completed_at = data.get("completed_at")
        if isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at)
        result_data = data.get("result_data")
        if isinstance(result_data, str):
            try:
                result_data = json.loads(result_data)
            except Exception:
                result_data = {}
        return cls(
            step_execution_id=str(data["step_execution_id"]),
            execution_id=str(data["execution_id"]),
            step_id=str(data["step_id"]),
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            attempt_count=int(data.get("attempt_count", 0)),
            result_data=result_data or {},
            error_message=str(data.get("error_message", "")),
            duration_ms=float(data.get("duration_ms", 0.0)),
        )


@dataclass
class TaskExecution:
    """Execution telemetry and record for a full workflow task execution."""

    execution_id: str
    task_id: str
    plan_id: str
    status: TaskStatus = TaskStatus.RUNNING
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    error_summary: str = ""
    result_data: dict[str, Any] = field(default_factory=dict)
    step_executions: list[StepExecution] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "status": self.status.value if isinstance(self.status, TaskStatus) else str(self.status),
            "started_at": self.started_at.isoformat() if isinstance(self.started_at, datetime) else str(self.started_at),
            "completed_at": self.completed_at.isoformat() if isinstance(self.completed_at, datetime) else (str(self.completed_at) if self.completed_at else None),
            "error_summary": self.error_summary,
            "result_data": self.result_data,
            "step_executions": [s.to_dict() for s in self.step_executions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskExecution:
        status_raw = data.get("status", TaskStatus.RUNNING.value)
        try:
            status = TaskStatus(status_raw)
        except ValueError:
            status = TaskStatus.RUNNING
        started_at = data.get("started_at")
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)
        elif not isinstance(started_at, datetime):
            started_at = datetime.now(timezone.utc)
        completed_at = data.get("completed_at")
        if isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at)
        result_data = data.get("result_data")
        if isinstance(result_data, str):
            try:
                result_data = json.loads(result_data)
            except Exception:
                result_data = {}
        step_execs = [
            StepExecution.from_dict(s) if isinstance(s, dict) else s
            for s in data.get("step_executions", [])
        ]
        return cls(
            execution_id=str(data["execution_id"]),
            task_id=str(data["task_id"]),
            plan_id=str(data["plan_id"]),
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            error_summary=str(data.get("error_summary", "")),
            result_data=result_data or {},
            step_executions=step_execs,
        )


@dataclass
class TaskProposal:
    """Untrusted proposal for a task plan generated by AI or heuristic planner."""

    task_title: str
    task_description: str
    steps: list[dict[str, Any]]
    confidence: float = 1.0
    reasoning: str = ""
    suggested_policy: FailurePolicy = FailurePolicy.STOP_ON_FAILURE


@dataclass
class TaskResult:
    """Final outcome summary for a workflow task execution."""

    task_id: str
    execution_id: str
    status: TaskStatus
    steps_completed: int
    steps_failed: int
    steps_total: int
    duration_ms: float
    error_message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskProgress:
    """Real-time progress update for an executing workflow task."""

    task_id: str
    execution_id: str
    percent_complete: float
    current_step_id: str | None
    completed_steps: int
    total_steps: int
    status: TaskStatus
    message: str = ""
