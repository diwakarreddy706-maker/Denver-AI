"""Retry policies and eligibility evaluation for task steps."""

from __future__ import annotations

from typing import Set

# Actions that are known to be safe/idempotent for bounded retry (max 1 retry)
IDEMPOTENT_SAFE_ACTIONS: Set[str] = {
    "get_time",
    "get_date",
    "get_system_status",
    "get_battery_status",
    "get_memory_status",
    "search_notes",
    "search_memories",
    "list_notes",
    "list_tasks",
    "list_routines",
    "read_note",
    "get_clipboard",
    "show_health",
}


class TaskRetryPolicy:
    """Evaluates whether a failed step is eligible for retry."""

    def __init__(self, max_retries: int = 1) -> None:
        self.max_retries = max(0, min(max_retries, 1))  # Phase 9 strictly bounds max retries to 1

    def can_retry(self, action_name: str, current_attempts: int) -> bool:
        """Return True if step can be retried."""
        if current_attempts >= self.max_retries:
            return False
        # Only allow retrying if within max_retries limit
        return True

    def is_safe_action(self, action_name: str) -> bool:
        """Check if action is strictly idempotent and safe to re-run."""
        return action_name.lower() in IDEMPOTENT_SAFE_ACTIONS
