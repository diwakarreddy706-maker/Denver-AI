"""Typed Data Models for Denver Scheduler & Routines."""

from __future__ import annotations

import enum
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


class TriggerType(str, enum.Enum):
    """Supported trigger types for scheduled routines."""

    ONE_TIME = "one_time"
    DAILY = "daily"
    WEEKLY = "weekly"
    INTERVAL = "interval"

    @classmethod
    def from_value(cls, val: str | TriggerType) -> TriggerType:
        if isinstance(val, TriggerType):
            return val
        clean = str(val).strip().lower()
        for member in cls:
            if member.value == clean or member.name.lower() == clean:
                return member
        raise ValueError(f"Unknown trigger type: '{val}'")


class RoutineStatus(str, enum.Enum):
    """Operational status of a routine."""

    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    COMPLETED = "completed"
    MISSED = "missed"


class ExecutionStatus(str, enum.Enum):
    """Result status of a single routine execution."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"
    MISSED = "MISSED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    BLOCKED = "BLOCKED"
    TIMEOUT = "TIMEOUT"


class NotificationPolicy(str, enum.Enum):
    """Notification policy upon routine execution."""

    ALWAYS = "ALWAYS"
    ON_FAILURE = "ON_FAILURE"
    NEVER = "NEVER"


@dataclass
class RoutineTrigger:
    """Structured trigger configuration for a scheduled routine."""

    trigger_type: TriggerType
    run_at: datetime | None = None          # For ONE_TIME
    time_of_day: str | None = None          # For DAILY / WEEKLY (e.g. "08:30" or "08:30:00")
    days_of_week: list[int] = field(default_factory=list)  # For WEEKLY (0=Monday, 6=Sunday)
    interval_seconds: float | None = None   # For INTERVAL (min 300.0s)
    timezone: str = "UTC"

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger_type": self.trigger_type.value,
            "run_at": self.run_at.isoformat() if self.run_at else None,
            "time_of_day": self.time_of_day,
            "days_of_week": self.days_of_week,
            "interval_seconds": self.interval_seconds,
            "timezone": self.timezone,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoutineTrigger:
        t_type = TriggerType.from_value(data.get("trigger_type", "one_time"))
        run_at_val = data.get("run_at")
        run_at_dt = None
        if run_at_val:
            try:
                run_at_dt = datetime.fromisoformat(run_at_val)
            except (ValueError, TypeError):
                pass

        return cls(
            trigger_type=t_type,
            run_at=run_at_dt,
            time_of_day=data.get("time_of_day"),
            days_of_week=list(data.get("days_of_week") or []),
            interval_seconds=float(data["interval_seconds"]) if data.get("interval_seconds") is not None else None,
            timezone=data.get("timezone", "UTC"),
        )


@dataclass
class RoutineAction:
    """A single structured action executed within a routine."""

    action_name: str
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_name": self.action_name,
            "params": self.params,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoutineAction:
        return cls(
            action_name=str(data.get("action_name", "")).strip(),
            params=dict(data.get("params") or {}),
            description=str(data.get("description", "")),
        )


@dataclass
class Routine:
    """Core persisted routine model."""

    routine_id: str
    name: str
    trigger: RoutineTrigger
    actions: list[RoutineAction]
    description: str = ""
    enabled: bool = True
    status: RoutineStatus = RoutineStatus.ACTIVE
    timezone: str = "UTC"
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_status: str = "PENDING"
    failure_count: int = 0
    max_runtime_seconds: float = 60.0
    notification_policy: NotificationPolicy = NotificationPolicy.ON_FAILURE
    requires_confirmation: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "routine_id": self.routine_id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "status": self.status.value,
            "trigger": self.trigger.to_dict(),
            "actions": [a.to_dict() for a in self.actions],
            "timezone": self.timezone,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_status": self.last_status,
            "failure_count": self.failure_count,
            "max_runtime_seconds": self.max_runtime_seconds,
            "notification_policy": self.notification_policy.value,
            "requires_confirmation": self.requires_confirmation,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Routine:
        def _parse_iso(val: Any) -> datetime | None:
            if not val:
                return None
            if isinstance(val, datetime):
                return val
            try:
                return datetime.fromisoformat(val)
            except (ValueError, TypeError):
                return None

        trigger_data = data.get("trigger")
        if isinstance(trigger_data, dict):
            trigger = RoutineTrigger.from_dict(trigger_data)
        elif isinstance(trigger_data, str):
            trigger = RoutineTrigger.from_dict(json.loads(trigger_data))
        else:
            trigger = RoutineTrigger(trigger_type=TriggerType.ONE_TIME)

        raw_actions = data.get("actions") or []
        if isinstance(raw_actions, str):
            raw_actions = json.loads(raw_actions)
        actions = [RoutineAction.from_dict(a) for a in raw_actions]

        raw_meta = data.get("metadata") or {}
        if isinstance(raw_meta, str):
            try:
                raw_meta = json.loads(raw_meta)
            except (ValueError, TypeError):
                raw_meta = {}

        notif_str = data.get("notification_policy", "ON_FAILURE")
        try:
            notif_policy = NotificationPolicy(notif_str)
        except ValueError:
            notif_policy = NotificationPolicy.ON_FAILURE

        status_str = data.get("status", "active")
        try:
            status = RoutineStatus(status_str)
        except ValueError:
            status = RoutineStatus.ACTIVE

        return cls(
            routine_id=str(data.get("routine_id", uuid.uuid4().hex[:12])),
            name=str(data.get("name", "Unnamed Routine")),
            description=str(data.get("description", "")),
            enabled=bool(data.get("enabled", True)),
            status=status,
            trigger=trigger,
            actions=actions,
            timezone=str(data.get("timezone", "UTC")),
            next_run_at=_parse_iso(data.get("next_run_at")),
            last_run_at=_parse_iso(data.get("last_run_at")),
            last_status=str(data.get("last_status", "PENDING")),
            failure_count=int(data.get("failure_count", 0)),
            max_runtime_seconds=float(data.get("max_runtime_seconds", 60.0)),
            notification_policy=notif_policy,
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            metadata=raw_meta,
            created_at=_parse_iso(data.get("created_at")) or datetime.now(timezone.utc),
            updated_at=_parse_iso(data.get("updated_at")) or datetime.now(timezone.utc),
        )


@dataclass
class RoutineExecution:
    """Historical execution record of a routine run."""

    execution_id: str
    routine_id: str
    started_at: datetime
    status: ExecutionStatus
    trigger_type: str
    completed_at: datetime | None = None
    confirmation_status: str = "NOT_REQUIRED"
    action_count: int = 0
    successful_actions: int = 0
    failed_actions: int = 0
    error_summary: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "routine_id": self.routine_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status.value,
            "trigger_type": self.trigger_type,
            "confirmation_status": self.confirmation_status,
            "action_count": self.action_count,
            "successful_actions": self.successful_actions,
            "failed_actions": self.failed_actions,
            "error_summary": self.error_summary,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoutineExecution:
        def _parse_iso(val: Any) -> datetime | None:
            if not val:
                return None
            if isinstance(val, datetime):
                return val
            try:
                return datetime.fromisoformat(val)
            except (ValueError, TypeError):
                return None

        stat_str = data.get("status", "SUCCESS")
        try:
            status = ExecutionStatus(stat_str)
        except ValueError:
            status = ExecutionStatus.SUCCESS

        return cls(
            execution_id=str(data.get("execution_id", uuid.uuid4().hex[:12])),
            routine_id=str(data.get("routine_id", "")),
            started_at=_parse_iso(data.get("started_at")) or datetime.now(timezone.utc),
            completed_at=_parse_iso(data.get("completed_at")),
            status=status,
            trigger_type=str(data.get("trigger_type", "manual")),
            confirmation_status=str(data.get("confirmation_status", "NOT_REQUIRED")),
            action_count=int(data.get("action_count", 0)),
            successful_actions=int(data.get("successful_actions", 0)),
            failed_actions=int(data.get("failed_actions", 0)),
            error_summary=str(data.get("error_summary", "")),
            duration_ms=float(data.get("duration_ms", 0.0)),
        )


@dataclass
class RoutineProposal:
    """A proposed routine generated by AI or parsed from user intent, requiring explicit confirmation."""

    name: str
    trigger: RoutineTrigger
    actions: list[RoutineAction]
    description: str = ""
    explanation: str = ""
    required_permissions: list[str] = field(default_factory=list)
    risk_level: str = "LOW"
    requires_confirmation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger.to_dict(),
            "actions": [a.to_dict() for a in self.actions],
            "explanation": self.explanation,
            "required_permissions": self.required_permissions,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
        }
