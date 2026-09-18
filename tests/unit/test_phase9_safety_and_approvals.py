"""Unit tests for Phase 9 Task Safety, Approvals, Retry Policies, and Cancellation Primitives."""

from __future__ import annotations

import asyncio
import pytest

from denver.tasks.approval import TaskApprovalManager
from denver.tasks.cancellation import CancellationManager, CancellationToken
from denver.tasks.errors import TaskCancelledError
from denver.tasks.retry import TaskRetryPolicy


def test_task_approval_manager_flow():
    """Verify TaskApprovalManager token creation, approval, and rejection."""
    mgr = TaskApprovalManager()
    token = mgr.request_approval(
        task_id="task_1",
        step_id="step_1",
        plan_id="plan_1",
        action_name="lock_workstation",
        params={},
        reason="Sensitive action",
    )
    assert token.startswith("appr_")
    assert not mgr.is_approved(token)

    pending = mgr.get_pending_approvals("task_1")
    assert len(pending) == 1
    assert pending[0]["approval_id"] == token

    # Approve
    assert mgr.approve(token)
    assert mgr.is_approved(token)
    assert len(mgr.get_pending_approvals("task_1")) == 0

    # Test rejection
    token2 = mgr.request_approval(
        task_id="task_2",
        step_id="step_2",
        plan_id="plan_2",
        action_name="format_disk",
        params={},
    )
    assert mgr.reject(token2, reason="Denied by admin")
    assert not mgr.is_approved(token2)
    record = mgr.get_approval(token2)
    assert record is not None
    assert record["status"] == "rejected"
    assert record["rejection_reason"] == "Denied by admin"


@pytest.mark.asyncio
async def test_task_approval_manager_wait_for_decision():
    """Verify asynchronous wait_for_decision unblocks on approval."""
    mgr = TaskApprovalManager()
    token = mgr.request_approval("t1", "s1", "p1", "test_act", {})

    async def delayed_approve():
        await asyncio.sleep(0.05)
        mgr.approve(token)

    asyncio.create_task(delayed_approve())
    approved = await mgr.wait_for_decision(token, timeout_seconds=1.0)
    assert approved is True


def test_task_retry_policy():
    """Verify TaskRetryPolicy strictly limits retries (max 1) and evaluates idempotence."""
    policy = TaskRetryPolicy(max_retries=1)

    assert policy.is_safe_action("get_time")
    assert policy.is_safe_action("get_system_status")
    assert policy.is_safe_action("search_notes")
    assert not policy.is_safe_action("lock_workstation")
    assert not policy.is_safe_action("create_note")

    # Within bounds (attempt 0 -> can retry)
    assert policy.can_retry("get_time", current_attempts=0)
    # Exceeded bounds (attempt 1 -> cannot retry)
    assert not policy.can_retry("get_time", current_attempts=1)


@pytest.mark.asyncio
async def test_cancellation_token_pause_and_cancel():
    """Verify CancellationToken pause/resume events and cancellation triggers."""
    token = CancellationToken("task_123")
    callback_fired = False

    def on_cancel():
        nonlocal callback_fired
        callback_fired = True

    token.add_callback(on_cancel)

    assert not token.is_cancelled
    assert not token.is_paused

    token.pause()
    assert token.is_paused

    token.resume()
    assert not token.is_paused

    token.cancel("Cancelled by test")
    assert token.is_cancelled
    assert callback_fired
    assert token.cancel_reason == "Cancelled by test"

    with pytest.raises(TaskCancelledError):
        await token.check_pause_and_cancellation()

    with pytest.raises(TaskCancelledError):
        token.raise_if_cancelled()


def test_cancellation_manager():
    """Verify CancellationManager coordinates tokens across tasks."""
    mgr = CancellationManager()
    tok1 = mgr.get_or_create("task_1")
    tok2 = mgr.get_or_create("task_2")

    assert mgr.get("task_1") is tok1
    assert mgr.get("task_2") is tok2

    assert mgr.pause_task("task_1")
    assert tok1.is_paused
    assert not tok2.is_paused

    assert mgr.resume_task("task_1")
    assert not tok1.is_paused

    assert mgr.cancel_task("task_2", reason="Test cancel")
    assert tok2.is_cancelled

    mgr.cancel_all(reason="Global shutdown")
    assert tok1.is_cancelled
    assert tok2.is_cancelled
