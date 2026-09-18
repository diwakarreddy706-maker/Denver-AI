"""Audit logging and historical records for task and workflow operations."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from denver.logging.logger import get_logger

logger = get_logger("tasks.audit")


class TaskAuditLogger:
    """Records immutable audit trail entries for task lifecycle and execution events."""

    def __init__(self, connection_factory: Any = None) -> None:
        self.connection_factory = connection_factory

    def _get_conn(self) -> sqlite3.Connection | None:
        if self.connection_factory:
            if callable(self.connection_factory):
                return self.connection_factory()
            return self.connection_factory
        return None

    def log(
        self,
        task_id: str,
        event_type: str,
        actor: str = "system",
        details: dict[str, Any] | None = None,
    ) -> str:
        """Log an audit event to sqlite and structured logger."""
        audit_id = f"aud_{uuid.uuid4().hex[:12]}"
        details_dict = details or {}
        details_json = json.dumps(details_dict)
        now = datetime.now(timezone.utc).isoformat()

        logger.info(
            "TASK_AUDIT [%s] task=%s event=%s actor=%s details=%s",
            audit_id,
            task_id,
            event_type,
            actor,
            details_json,
        )

        conn = self._get_conn()
        if conn:
            try:
                conn.execute(
                    """
                    INSERT INTO task_audit (audit_id, task_id, event_type, actor, details, created_at)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (audit_id, task_id, event_type, actor, details_json, now),
                )
                conn.commit()
            except Exception as exc:
                logger.error("Failed to write to task_audit table: %s", exc)

        return audit_id

    def get_audit_trail(self, task_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve audit log history for a specific task."""
        conn = self._get_conn()
        if not conn:
            return []
        try:
            cursor = conn.execute(
                """
                SELECT audit_id, task_id, event_type, actor, details, created_at
                FROM task_audit
                WHERE task_id = ?
                ORDER BY created_at ASC
                LIMIT ?;
                """,
                (task_id, limit),
            )
            rows = cursor.fetchall()
            results = []
            for row in rows:
                try:
                    details_obj = json.loads(row[4])
                except Exception:
                    details_obj = {}
                results.append({
                    "audit_id": row[0],
                    "task_id": row[1],
                    "event_type": row[2],
                    "actor": row[3],
                    "details": details_obj,
                    "created_at": row[5],
                })
            return results
        except Exception as exc:
            logger.error("Error querying task_audit: %s", exc)
            return []
