"""Confirmation management for high-risk Denver automation actions."""

from __future__ import annotations

import secrets
import time
from typing import Any

from denver.automation.errors import ConfirmationInvalidError
from denver.automation.models import ConfirmationRequirement
from denver.logging.logger import get_logger

logger = get_logger("automation.confirmation")


class ConfirmationManager:
    """Manages ephemeral, single-use, action-bound confirmation tokens."""

    def __init__(self, default_timeout_seconds: float = 30.0) -> None:
        self.default_timeout_seconds = default_timeout_seconds
        self._pending: dict[str, ConfirmationRequirement] = {}

    def create_pending(
        self,
        action_name: str,
        action_params: dict[str, Any],
        prompt_message: str,
        timeout_seconds: float | None = None,
    ) -> ConfirmationRequirement:
        """Generate a new confirmation token bound strictly to the requested action and parameters."""
        self.clear_expired()

        timeout = timeout_seconds if timeout_seconds is not None else self.default_timeout_seconds
        token = f"cnf_{secrets.token_hex(4)}"
        expires_at = time.time() + timeout

        req = ConfirmationRequirement(
            token=token,
            action_name=action_name,
            action_params=dict(action_params),
            prompt_message=prompt_message,
            created_at=time.time(),
            expires_at=expires_at,
            is_consumed=False,
        )
        self._pending[token] = req
        logger.info("Created confirmation request [%s] for action '%s' (expires in %.1fs)", token, action_name, timeout)
        return req

    def get_pending(self, token: str) -> ConfirmationRequirement | None:
        """Look up a pending confirmation requirement."""
        req = self._pending.get(token)
        if not req:
            return None
        if req.is_expired or req.is_consumed:
            self._pending.pop(token, None)
            return None
        return req

    def get_latest_pending(self, action_name: str | None = None) -> ConfirmationRequirement | None:
        """Find the most recently issued, unexpired pending confirmation."""
        self.clear_expired()
        valid = [
            req for req in self._pending.values()
            if not req.is_expired and not req.is_consumed and (action_name is None or req.action_name == action_name)
        ]
        if not valid:
            return None
        valid.sort(key=lambda r: r.created_at, reverse=True)
        return valid[0]

    def validate_and_consume(self, token: str, expected_action: str | None = None) -> ConfirmationRequirement:
        """Verify token validity, enforce single-use, check action binding, and consume token."""
        req = self._pending.get(token)
        if not req:
            raise ConfirmationInvalidError(f"Confirmation token '{token}' is invalid or does not exist.")

        if req.is_consumed:
            self._pending.pop(token, None)
            raise ConfirmationInvalidError(f"Confirmation token '{token}' has already been used.")

        if req.is_expired:
            self._pending.pop(token, None)
            raise ConfirmationInvalidError(f"Confirmation token '{token}' has expired (limit was {self.default_timeout_seconds}s).")

        if expected_action and req.action_name != expected_action:
            raise ConfirmationInvalidError(
                f"Confirmation token '{token}' was issued for '{req.action_name}', not '{expected_action}'."
            )

        # Consume the token atomically
        self._pending.pop(token, None)
        logger.info("Confirmation token [%s] for '%s' successfully validated and consumed.", token, req.action_name)
        return req

    def clear_expired(self) -> int:
        """Evict stale and consumed tokens from memory."""
        now = time.time()
        expired_keys = [k for k, v in self._pending.items() if v.is_expired or v.is_consumed or (now > v.expires_at)]
        for k in expired_keys:
            self._pending.pop(k, None)
        return len(expired_keys)

    def clear(self) -> None:
        """Flush all pending confirmation requests."""
        self._pending.clear()
