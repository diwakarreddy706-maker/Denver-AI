"""Unit tests for Action Confirmation Manager."""

from __future__ import annotations

import time
import unittest
from denver.automation.confirmation import ConfirmationManager
from denver.automation.errors import ConfirmationInvalidError


class TestConfirmationManager(unittest.TestCase):
    """Test suite for ephemeral confirmation token lifecycle, timeouts, single-use, and action binding."""

    def setUp(self) -> None:
        self.mgr = ConfirmationManager(default_timeout_seconds=2.0)

    def test_create_and_get_pending(self) -> None:
        """Verify creating pending confirmation stores requirement correctly."""
        req = self.mgr.create_pending(
            action_name="lock_workstation",
            action_params={},
            prompt_message="Lock computer?",
        )
        self.assertTrue(req.token.startswith("cnf_"))
        self.assertEqual(req.action_name, "lock_workstation")

        fetched = self.mgr.get_pending(req.token)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.token, req.token)

    def test_validate_and_consume_success(self) -> None:
        """Verify token is consumed on validation and cannot be reused."""
        req = self.mgr.create_pending(
            action_name="lock_workstation",
            action_params={},
            prompt_message="Lock computer?",
        )
        consumed = self.mgr.validate_and_consume(req.token, expected_action="lock_workstation")
        self.assertEqual(consumed.token, req.token)

        # Attempting to reuse the token must raise ConfirmationInvalidError
        with self.assertRaises(ConfirmationInvalidError):
            self.mgr.validate_and_consume(req.token, expected_action="lock_workstation")

    def test_token_mismatched_action_rejected(self) -> None:
        """Verify token cannot be used for an action different from the one it was issued for."""
        req = self.mgr.create_pending(
            action_name="lock_workstation",
            action_params={},
            prompt_message="Lock computer?",
        )
        with self.assertRaises(ConfirmationInvalidError):
            self.mgr.validate_and_consume(req.token, expected_action="shutdown")

    def test_token_expiration(self) -> None:
        """Verify expired tokens are rejected."""
        req = self.mgr.create_pending(
            action_name="lock_workstation",
            action_params={},
            prompt_message="Lock computer?",
            timeout_seconds=0.01,
        )
        time.sleep(0.05)
        with self.assertRaises(ConfirmationInvalidError):
            self.mgr.validate_and_consume(req.token, expected_action="lock_workstation")

    def test_get_latest_pending(self) -> None:
        """Verify get_latest_pending finds the most recent valid pending token."""
        req1 = self.mgr.create_pending("lock_workstation", {}, "Lock 1?")
        time.sleep(0.01)
        req2 = self.mgr.create_pending("lock_workstation", {}, "Lock 2?")

        latest = self.mgr.get_latest_pending("lock_workstation")
        self.assertIsNotNone(latest)
        self.assertEqual(latest.token, req2.token)


if __name__ == "__main__":
    unittest.main()
