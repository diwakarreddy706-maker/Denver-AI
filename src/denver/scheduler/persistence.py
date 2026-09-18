"""SQLite Repositories for Denver Scheduler & Routines."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from denver.logging.logger import get_logger
from denver.scheduler.models import (
    ExecutionStatus,
    NotificationPolicy,
    Routine,
    RoutineAction,
    RoutineExecution,
    RoutineStatus,
    RoutineTrigger,
    TriggerType,
)

logger = get_logger("scheduler.persistence")


def _parse_dt(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


class RoutineRepository:
    """SQLite repository for persistent Routine entities."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _row_to_routine(self, row: Any) -> Routine:
        # id, routine_id, name, description, enabled, status, trigger_type, trigger_config, actions,
        # timezone, next_run_at, last_run_at, last_status, failure_count, max_runtime_seconds,
        # notification_policy, requires_confirmation, metadata, created_at, updated_at
        trigger_cfg = {}
        if row[7]:
            try:
                trigger_cfg = json.loads(row[7]) if isinstance(row[7], str) else row[7]
            except Exception:
                trigger_cfg = {}
        trigger_cfg["trigger_type"] = row[6]
        trigger = RoutineTrigger.from_dict(trigger_cfg)

        actions_list = []
        if row[8]:
            try:
                raw_acts = json.loads(row[8]) if isinstance(row[8], str) else row[8]
                actions_list = [RoutineAction.from_dict(a) for a in raw_acts]
            except Exception:
                actions_list = []

        meta = {}
        if row[17]:
            try:
                meta = json.loads(row[17]) if isinstance(row[17], str) else row[17]
            except Exception:
                meta = {}

        enabled_bool = bool(row[4])
        status_raw = row[5] or ("active" if enabled_bool else "disabled")
        try:
            status_val = RoutineStatus(status_raw)
        except ValueError:
            status_val = RoutineStatus.ACTIVE if enabled_bool else RoutineStatus.DISABLED

        return Routine(
            routine_id=row[1],
            name=row[2],
            description=row[3] or "",
            enabled=enabled_bool,
            status=status_val,
            trigger=trigger,
            actions=actions_list,
            timezone=row[9] or "UTC",
            next_run_at=_parse_dt(row[10]),
            last_run_at=_parse_dt(row[11]),
            last_status=row[12] or "PENDING",
            failure_count=int(row[13] or 0),
            max_runtime_seconds=float(row[14] or 60.0),
            notification_policy=NotificationPolicy(row[15]) if row[15] in [p.value for p in NotificationPolicy] else NotificationPolicy.ON_FAILURE,
            requires_confirmation=bool(row[16]),
            metadata=meta,
            created_at=_parse_dt(row[18]) or datetime.now(timezone.utc),
            updated_at=_parse_dt(row[19]) or datetime.now(timezone.utc),
        )

    def save(self, routine: Routine) -> Routine:
        """Insert or update a routine record."""
        trigger_json = json.dumps(routine.trigger.to_dict())
        actions_json = json.dumps([a.to_dict() for a in routine.actions])
        meta_json = json.dumps(routine.metadata)
        next_run_str = routine.next_run_at.isoformat() if routine.next_run_at else None
        last_run_str = routine.last_run_at.isoformat() if routine.last_run_at else None

        cursor = self.conn.execute(
            """
            INSERT INTO routines (
                routine_id, name, description, enabled, status, trigger_type, trigger_config,
                actions, timezone, next_run_at, last_run_at, last_status, failure_count,
                max_runtime_seconds, notification_policy, requires_confirmation, metadata,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(routine_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                enabled = excluded.enabled,
                status = excluded.status,
                trigger_type = excluded.trigger_type,
                trigger_config = excluded.trigger_config,
                actions = excluded.actions,
                timezone = excluded.timezone,
                next_run_at = excluded.next_run_at,
                last_run_at = excluded.last_run_at,
                last_status = excluded.last_status,
                failure_count = excluded.failure_count,
                max_runtime_seconds = excluded.max_runtime_seconds,
                notification_policy = excluded.notification_policy,
                requires_confirmation = excluded.requires_confirmation,
                metadata = excluded.metadata,
                updated_at = CURRENT_TIMESTAMP
            RETURNING
                id, routine_id, name, description, enabled, status, trigger_type, trigger_config,
                actions, timezone, next_run_at, last_run_at, last_status, failure_count,
                max_runtime_seconds, notification_policy, requires_confirmation, metadata,
                created_at, updated_at;
            """,
            (
                routine.routine_id,
                routine.name,
                routine.description,
                1 if routine.enabled else 0,
                routine.status.value,
                routine.trigger.trigger_type.value,
                trigger_json,
                actions_json,
                routine.timezone,
                next_run_str,
                last_run_str,
                routine.last_status,
                routine.failure_count,
                routine.max_runtime_seconds,
                routine.notification_policy.value,
                1 if routine.requires_confirmation else 0,
                meta_json,
                routine.created_at.isoformat(),
            ),
        )
        row = cursor.fetchone()
        return self._row_to_routine(row)

    def get(self, routine_id: str) -> Routine | None:
        """Fetch a routine by routine_id."""
        cursor = self.conn.execute(
            """
            SELECT
                id, routine_id, name, description, enabled, status, trigger_type, trigger_config,
                actions, timezone, next_run_at, last_run_at, last_status, failure_count,
                max_runtime_seconds, notification_policy, requires_confirmation, metadata,
                created_at, updated_at
            FROM routines
            WHERE routine_id = ?;
            """,
            (routine_id.strip(),),
        )
        row = cursor.fetchone()
        return self._row_to_routine(row) if row else None

    def get_by_name(self, name: str) -> Routine | None:
        """Fetch a routine by name (case-insensitive)."""
        cursor = self.conn.execute(
            """
            SELECT
                id, routine_id, name, description, enabled, status, trigger_type, trigger_config,
                actions, timezone, next_run_at, last_run_at, last_status, failure_count,
                max_runtime_seconds, notification_policy, requires_confirmation, metadata,
                created_at, updated_at
            FROM routines
            WHERE LOWER(name) = LOWER(?);
            """,
            (name.strip(),),
        )
        row = cursor.fetchone()
        return self._row_to_routine(row) if row else None

    def list_all(self, enabled_only: bool = False) -> list[Routine]:
        """Fetch all routines optionally filtered by enabled."""
        if enabled_only:
            cursor = self.conn.execute(
                """
                SELECT
                    id, routine_id, name, description, enabled, status, trigger_type, trigger_config,
                    actions, timezone, next_run_at, last_run_at, last_status, failure_count,
                    max_runtime_seconds, notification_policy, requires_confirmation, metadata,
                    created_at, updated_at
                FROM routines
                WHERE enabled = 1
                ORDER BY created_at ASC;
                """
            )
        else:
            cursor = self.conn.execute(
                """
                SELECT
                    id, routine_id, name, description, enabled, status, trigger_type, trigger_config,
                    actions, timezone, next_run_at, last_run_at, last_status, failure_count,
                    max_runtime_seconds, notification_policy, requires_confirmation, metadata,
                    created_at, updated_at
                FROM routines
                ORDER BY created_at ASC;
                """
            )
        rows = cursor.fetchall()
        return [self._row_to_routine(r) for r in rows]

    def list_due(self, before_dt: datetime) -> list[Routine]:
        """Fetch all enabled routines whose next_run_at is <= before_dt."""
        iso_str = before_dt.isoformat()
        cursor = self.conn.execute(
            """
            SELECT
                id, routine_id, name, description, enabled, trigger_type, trigger_config,
                actions, timezone, next_run_at, last_run_at, last_status, failure_count,
                max_runtime_seconds, notification_policy, requires_confirmation, metadata,
                created_at, updated_at
            FROM routines
            WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ?
            ORDER BY next_run_at ASC;
            """,
            (iso_str,),
        )
        return [self._row_to_routine(r) for r in cursor.fetchall()]

    def update_execution_result(
        self,
        routine_id: str,
        next_run_at: datetime | None,
        last_run_at: datetime,
        last_status: str,
        failure_count: int,
    ) -> bool:
        """Update routine state after execution."""
        next_run_str = next_run_at.isoformat() if next_run_at else None
        cursor = self.conn.execute(
            """
            UPDATE routines
            SET next_run_at = ?,
                last_run_at = ?,
                last_status = ?,
                failure_count = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE routine_id = ?;
            """,
            (next_run_str, last_run_at.isoformat(), last_status, failure_count, routine_id.strip()),
        )
        return cursor.rowcount > 0

    def delete(self, routine_id: str) -> bool:
        """Delete routine and associated executions."""
        cursor = self.conn.execute(
            "DELETE FROM routines WHERE routine_id = ?;",
            (routine_id.strip(),),
        )
        return cursor.rowcount > 0


class RoutineExecutionRepository:
    """SQLite repository for RoutineExecution records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _row_to_execution(self, row: Any) -> RoutineExecution:
        # id, execution_id, routine_id, started_at, completed_at, status, trigger_type,
        # confirmation_status, action_count, successful_actions, failed_actions, error_summary, duration_ms
        stat_val = row[5]
        try:
            status = ExecutionStatus(stat_val)
        except ValueError:
            status = ExecutionStatus.SUCCESS

        return RoutineExecution(
            execution_id=row[1],
            routine_id=row[2],
            started_at=_parse_dt(row[3]) or datetime.now(timezone.utc),
            completed_at=_parse_dt(row[4]),
            status=status,
            trigger_type=row[6] or "manual",
            confirmation_status=row[7] or "NOT_REQUIRED",
            action_count=int(row[8] or 0),
            successful_actions=int(row[9] or 0),
            failed_actions=int(row[10] or 0),
            error_summary=row[11] or "",
            duration_ms=float(row[12] or 0.0),
        )

    def save(self, execution: RoutineExecution) -> RoutineExecution:
        """Insert or update execution history record."""
        cursor = self.conn.execute(
            """
            INSERT INTO routine_executions (
                execution_id, routine_id, started_at, completed_at, status,
                trigger_type, confirmation_status, action_count, successful_actions,
                failed_actions, error_summary, duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(execution_id) DO UPDATE SET
                completed_at = excluded.completed_at,
                status = excluded.status,
                confirmation_status = excluded.confirmation_status,
                action_count = excluded.action_count,
                successful_actions = excluded.successful_actions,
                failed_actions = excluded.failed_actions,
                error_summary = excluded.error_summary,
                duration_ms = excluded.duration_ms
            RETURNING
                id, execution_id, routine_id, started_at, completed_at, status,
                trigger_type, confirmation_status, action_count, successful_actions,
                failed_actions, error_summary, duration_ms;
            """,
            (
                execution.execution_id,
                execution.routine_id,
                execution.started_at.isoformat(),
                execution.completed_at.isoformat() if execution.completed_at else None,
                execution.status.value,
                execution.trigger_type,
                execution.confirmation_status,
                execution.action_count,
                execution.successful_actions,
                execution.failed_actions,
                execution.error_summary,
                execution.duration_ms,
            ),
        )
        row = cursor.fetchone()
        return self._row_to_execution(row)

    def get(self, execution_id: str) -> RoutineExecution | None:
        cursor = self.conn.execute(
            """
            SELECT
                id, execution_id, routine_id, started_at, completed_at, status,
                trigger_type, confirmation_status, action_count, successful_actions,
                failed_actions, error_summary, duration_ms
            FROM routine_executions
            WHERE execution_id = ?;
            """,
            (execution_id.strip(),),
        )
        row = cursor.fetchone()
        return self._row_to_execution(row) if row else None

    def list_by_routine(self, routine_id: str, limit: int = 50) -> list[RoutineExecution]:
        cursor = self.conn.execute(
            """
            SELECT
                id, execution_id, routine_id, started_at, completed_at, status,
                trigger_type, confirmation_status, action_count, successful_actions,
                failed_actions, error_summary, duration_ms
            FROM routine_executions
            WHERE routine_id = ?
            ORDER BY started_at DESC
            LIMIT ?;
            """,
            (routine_id.strip(), limit),
        )
        return [self._row_to_execution(r) for r in cursor.fetchall()]

    list_for_routine = list_by_routine

    def list_recent(self, limit: int = 50) -> list[RoutineExecution]:
        cursor = self.conn.execute(
            """
            SELECT
                id, execution_id, routine_id, started_at, completed_at, status,
                trigger_type, confirmation_status, action_count, successful_actions,
                failed_actions, error_summary, duration_ms
            FROM routine_executions
            ORDER BY started_at DESC
            LIMIT ?;
            """,
            (limit,),
        )
        return [self._row_to_execution(r) for r in cursor.fetchall()]


class RoutineAuditRepository:
    """SQLite repository for security audit logging of scheduler operations."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def record(
        self,
        routine_id: str,
        event_type: str,
        actor: str = "system",
        details: dict[str, Any] | None = None,
    ) -> None:
        audit_id = f"aud_{uuid.uuid4().hex[:10]}"
        details_json = json.dumps(details or {})
        self.conn.execute(
            """
            INSERT INTO routine_audit (audit_id, routine_id, event_type, actor, details, created_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
            """,
            (audit_id, routine_id.strip(), event_type, actor, details_json),
        )

    log = record

    def list_by_routine(self, routine_id: str, limit: int = 50) -> list[dict[str, Any]]:
        cursor = self.conn.execute(
            """
            SELECT audit_id, routine_id, event_type, actor, details, created_at
            FROM routine_audit
            WHERE routine_id = ?
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (routine_id.strip(), limit),
        )
        results = []
        for r in cursor.fetchall():
            d = {}
            if r[4]:
                try:
                    d = json.loads(r[4])
                except Exception:
                    d = {}
            results.append({
                "audit_id": r[0],
                "routine_id": r[1],
                "event_type": r[2],
                "actor": r[3],
                "details": d,
                "created_at": r[5],
            })
        return results

    list_for_routine = list_by_routine

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        cursor = self.conn.execute(
            """
            SELECT audit_id, routine_id, event_type, actor, details, created_at
            FROM routine_audit
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (limit,),
        )
        results = []
        for r in cursor.fetchall():
            d = {}
            if r[4]:
                try:
                    d = json.loads(r[4])
                except Exception:
                    d = {}
            results.append({
                "audit_id": r[0],
                "routine_id": r[1],
                "event_type": r[2],
                "actor": r[3],
                "details": d,
                "created_at": r[5],
            })
        return results
