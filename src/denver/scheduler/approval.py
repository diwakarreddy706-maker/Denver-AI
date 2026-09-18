"""Approval & Confirmation Manager for Scheduled Routine Executions."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from denver.logging.logger import get_logger
from denver.runtime.event_bus import DenverEventBus, get_event_bus
from denver.runtime.events import (
    RoutineConfirmationAccepted,
    RoutineConfirmationRejected,
    RoutineConfirmationRequested,
)

logger = get_logger("scheduler.approval")


@dataclass
class RoutineApprovalRequest:
    """A pending user approval request for scheduled high-risk actions."""

    token: str
    routine_id: str
    action_summary: str
    created_at: float = field(default_factory=time.time)
    timeout_seconds: float = 60.0
    confirmed: bool | None = None  # None=Pending, True=Approved, False=Rejected

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.timeout_seconds

    @property
    def is_pending(self) -> bool:
        return self.confirmed is None and not self.is_expired


class RoutineApprovalManager:
    """Manages explicit user confirmation tokens for high-risk scheduled routines."""

    def __init__(self, event_bus: DenverEventBus | None = None) -> None:
        self.event_bus = event_bus or get_event_bus()
        self._pending: dict[str, RoutineApprovalRequest] = {}

    async def request_approval(
        self,
        routine_id: str,
        action_summary: str,
        timeout_seconds: float = 60.0,
    ) -> RoutineApprovalRequest:
        """Create a pending approval request and publish confirmation event."""
        token = f"rtn_cnf_{uuid.uuid4().hex[:8]}"
        req = RoutineApprovalRequest(
            token=token,
            routine_id=routine_id,
            action_summary=action_summary,
            timeout_seconds=timeout_seconds,
        )
        self._pending[token] = req
        logger.info("Approval requested for routine '%s' (Token: %s): %s", routine_id, token, action_summary)
        await self.event_bus.publish(
            RoutineConfirmationRequested(
                routine_id=routine_id,
                token=token,
                action_summary=action_summary,
            )
        )
        return req

    async def confirm(self, token: str) -> bool:
        """User confirms and approves routine execution."""
        clean_tok = token.strip()
        req = self._pending.get(clean_tok)
        if not req or req.is_expired:
            logger.warning("Attempted to confirm invalid or expired token '%s'.", clean_tok)
            return False

        req.confirmed = True
        logger.info("Approval GRANTED for routine '%s' (Token: %s).", req.routine_id, clean_tok)
        await self.event_bus.publish(
            RoutineConfirmationAccepted(
                routine_id=req.routine_id,
                token=clean_tok,
            )
        )
        return True

    async def reject(self, token: str) -> bool:
        """User explicitly rejects routine execution."""
        clean_tok = token.strip()
        req = self._pending.get(clean_tok)
        if not req or req.is_expired:
            logger.warning("Attempted to reject invalid or expired token '%s'.", clean_tok)
            return False

        req.confirmed = False
        logger.info("Approval REJECTED for routine '%s' (Token: %s).", req.routine_id, clean_tok)
        await self.event_bus.publish(
            RoutineConfirmationRejected(
                routine_id=req.routine_id,
                token=clean_tok,
            )
        )
        return True

    def get_pending(self, token: str) -> RoutineApprovalRequest | None:
        """Get pending request if still valid."""
        req = self._pending.get(token.strip())
        if req and req.is_pending:
            return req
        return None

    def list_pending(self) -> list[RoutineApprovalRequest]:
        """List all active, non-expired pending requests."""
        now = time.time()
        # Clean up stale tokens
        self._pending = {
            t: r for t, r in self._pending.items()
            if (now - r.created_at) < (r.timeout_seconds + 300)
        }
        return [r for r in self._pending.values() if r.is_pending]
