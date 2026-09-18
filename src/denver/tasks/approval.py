"""Approval management and confirmation tokens for high-risk task steps."""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timezone
from typing import Any

from denver.logging.logger import get_logger

logger = get_logger("tasks.approval")


class TaskApprovalManager:
    """Manages explicit user confirmation requests for sensitive or impactful actions."""

    def __init__(self) -> None:
        self._pending: dict[str, dict[str, Any]] = {}
        self._waiters: dict[str, asyncio.Event] = {}

    def request_approval(
        self,
        task_id: str,
        step_id: str,
        plan_id: str,
        action_name: str,
        params: dict[str, Any],
        reason: str = "High-impact action requires explicit confirmation",
    ) -> str:
        """Create a pending approval request and return a secure token."""
        approval_id = f"appr_{secrets.token_hex(8)}"
        record = {
            "approval_id": approval_id,
            "task_id": task_id,
            "step_id": step_id,
            "plan_id": plan_id,
            "action_name": action_name,
            "params": params,
            "reason": reason,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._pending[approval_id] = record
        self._waiters[approval_id] = asyncio.Event()
        logger.info(
            "Task approval requested [id=%s, task=%s, step=%s, action=%s]",
            approval_id,
            task_id,
            step_id,
            action_name,
        )
        return approval_id

    def approve(self, approval_id: str) -> bool:
        """Approve a pending request."""
        record = self._pending.get(approval_id)
        if not record or record["status"] != "pending":
            return False
        record["status"] = "accepted"
        record["decided_at"] = datetime.now(timezone.utc).isoformat()
        waiter = self._waiters.get(approval_id)
        if waiter:
            waiter.set()
        logger.info("Task approval ACCEPTED [id=%s, task=%s]", approval_id, record["task_id"])
        return True

    def reject(self, approval_id: str, reason: str = "User rejected confirmation") -> bool:
        """Reject a pending request."""
        record = self._pending.get(approval_id)
        if not record or record["status"] != "pending":
            return False
        record["status"] = "rejected"
        record["rejection_reason"] = reason
        record["decided_at"] = datetime.now(timezone.utc).isoformat()
        waiter = self._waiters.get(approval_id)
        if waiter:
            waiter.set()
        logger.info("Task approval REJECTED [id=%s, task=%s, reason=%s]", approval_id, record["task_id"], reason)
        return True

    def is_approved(self, approval_id: str) -> bool:
        """Check if an approval request has been accepted."""
        record = self._pending.get(approval_id)
        return bool(record and record["status"] == "accepted")

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        return self._pending.get(approval_id)

    def get_pending_approvals(self, task_id: str | None = None) -> list[dict[str, Any]]:
        results = [
            req for req in self._pending.values()
            if req["status"] == "pending"
        ]
        if task_id:
            results = [req for req in results if req["task_id"] == task_id]
        return results

    async def wait_for_decision(self, approval_id: str, timeout_seconds: float = 300.0) -> bool:
        """Asynchronously wait for a user confirmation decision."""
        waiter = self._waiters.get(approval_id)
        if not waiter:
            return False
        try:
            await asyncio.wait_for(waiter.wait(), timeout=timeout_seconds)
            return self.is_approved(approval_id)
        except asyncio.TimeoutError:
            self.reject(approval_id, reason="Approval timed out")
            return False
