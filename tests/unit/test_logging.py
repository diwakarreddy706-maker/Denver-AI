"""Unit tests for Denver Logging and Secret Redaction."""

from __future__ import annotations

import logging
import unittest
from denver.logging.logger import DenverMaskingFilter, get_logger, mask_sensitive_data


class TestDenverLogging(unittest.TestCase):
    """Test suite for Denver logger masking and filter behavior."""

    def test_mask_sensitive_data_assignments(self) -> None:
        """Verify API keys, tokens, and passwords in key=val strings are masked."""
        raw = "GROQ_API_KEY=gsk_secret_value_12345, GEMINI_KEY: aiza_secret_67890"
        masked = mask_sensitive_data(raw)
        self.assertNotIn("gsk_secret_value_12345", masked)
        self.assertNotIn("aiza_secret_67890", masked)
        self.assertIn("GROQ_API_KEY=***", masked)

    def test_mask_bearer_token(self) -> None:
        """Verify Bearer tokens are redacted."""
        raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        masked = mask_sensitive_data(raw)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", masked)
        self.assertIn("Bearer ***", masked)

    def test_masking_filter_on_log_record(self) -> None:
        """Verify DenverMaskingFilter redacts records."""
        record = logging.LogRecord(
            name="denver.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="User token is TOKEN=super_secret_token_123",
            args=(),
            exc_info=None,
        )
        mask_filter = DenverMaskingFilter()
        mask_filter.filter(record)
        self.assertNotIn("super_secret_token_123", record.msg)
        self.assertIn("TOKEN=***", record.msg)

    def test_get_logger_namespacing(self) -> None:
        """Verify get_logger prepends denver namespace."""
        logger = get_logger("custom_module")
        self.assertEqual(logger.name, "denver.custom_module")


if __name__ == "__main__":
    unittest.main()
