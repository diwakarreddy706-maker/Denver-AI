"""Security Audit Logging for Scheduler & Routine Operations."""

from __future__ import annotations

from typing import Any

from denver.logging.logger import get_logger, mask_sensitive_data
from denver.memory.database import DenverDatabase
from denver.scheduler.persistence import RoutineAuditRepository

logger = get_logger("scheduler.audit")


class RoutineAuditLogger:
    """Records security-relevant scheduler mutations and execution audit events."""

    def __init__(self, db: DenverDatabase) -> None:
        self.db = db

    async def log_event(
        self,
        routine_id: str,
        event_type: str,
        actor: str = "system",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Persist an audit record to SQLite asynchronously."""
        safe_details = {}
        if details:
            for k, v in details.items():
                if isinstance(v, str):
                    safe_details[k] = mask_sensitive_data(v)
                else:
                    safe_details[k] = v

        def _op(conn) -> None:
            repo = RoutineAuditRepository(conn)
            repo.record(
                routine_id=routine_id,
                event_type=event_type,
                actor=actor,
                details=safe_details,
            )

        try:
            await self.db.run_async(_op)
            logger.debug("Audit logged [%s] for routine '%s' by '%s'.", event_type, routine_id, actor)
        except Exception as exc:
            logger.error("Failed to write scheduler audit log: %s", exc)

    async def get_recent_audit_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve recent scheduler audit trail entries."""
        def _op(conn) -> list[dict[str, Any]]:
            repo = RoutineAuditRepository(conn)
            return repo.list_recent(limit=limit)

        return await self.db.run_async(_op)
