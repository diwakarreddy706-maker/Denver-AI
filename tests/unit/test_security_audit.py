"""Security and Credential Leakage Audit Tests for Denver."""

from __future__ import annotations

import io
import json
import logging
import tempfile
import unittest
from pathlib import Path

from denver.config.settings import DenverSettings
from denver.health.health_service import DenverHealthService
from denver.logging.logger import DenverMaskingFilter
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.security.vault import DenverVault


class TestDenverSecurityAudit(unittest.IsolatedAsyncioTestCase):
    """Rigorous audit verifying zero credential leakage across all subsystems."""

    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "audit_memory.sqlite3"
        self.vault_path = Path(self.temp_dir.name) / "audit_vault.dat"
        self.db = DenverDatabase(db_path=self.db_path)
        await self.db.initialize()
        self.vault = DenverVault(vault_path=self.vault_path)
        self.memory = MemoryService(db=self.db)
        self.health = DenverHealthService(database=self.db)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.temp_dir.cleanup()

    def test_secrets_masked_in_logging_filter(self) -> None:
        """Verify DenverMaskingFilter strips sensitive API keys from logs."""
        mask_filter = DenverMaskingFilter()

        log_record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Connecting using GROQ_API_KEY=gsk_secretKey987654321 and Bearer token123456",
            args=(),
            exc_info=None,
        )
        mask_filter.filter(log_record)

        self.assertNotIn("gsk_secretKey987654321", log_record.msg)
        self.assertNotIn("token123456", log_record.msg)
        self.assertIn("***", log_record.msg)

    def test_secrets_masked_in_config_export(self) -> None:
        """Verify DenverSettings.to_safe_dict() never dumps raw API keys."""
        settings = DenverSettings(
            groq_api_key="gsk_super_secret_groq_key",
            gemini_api_key="AIzaSySuperSecretGeminiKey",
        )
        safe_dict = settings.to_safe_dict()

        self.assertNotIn("gsk_super_secret_groq_key", json.dumps(safe_dict))
        self.assertNotIn("AIzaSySuperSecretGeminiKey", json.dumps(safe_dict))
        self.assertEqual(safe_dict["groq_api_key"], "***")
        self.assertEqual(safe_dict["gemini_api_key"], "***")

    def test_health_report_never_leaks_secrets_or_memory_contents(self) -> None:
        """Verify health report contains telemetry only, never private database contents or keys."""
        report = self.health.get_health_report()
        report_json = json.dumps(report)

        self.assertNotIn("gsk_", report_json)
        self.assertNotIn("AIza", report_json)
        self.assertNotIn("password", report_json)
        self.assertIn("subsystems", report)
        self.assertIn("database", report)
        self.assertEqual(report["database"]["status"], "READY")

    async def test_secrets_never_stored_in_sqlite_tables(self) -> None:
        """Verify credentials stored in DenverVault are not in the SQLite database."""
        secret_name = "GROQ_API_KEY"
        secret_value = "gsk_very_secret_cloud_token_abc123"
        self.vault.set_secret(secret_name, secret_value)

        # Inspect raw SQLite database bytes/text
        conn = self.db.connect_sync()
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cur.fetchall()]

        for table in tables:
            cur = conn.execute(f"SELECT * FROM {table};")
            rows = cur.fetchall()
            for row in rows:
                for col in row:
                    if isinstance(col, str):
                        self.assertNotIn(secret_value, col, f"Found raw secret in SQLite table '{table}' column '{col}'")


if __name__ == "__main__":
    unittest.main()
