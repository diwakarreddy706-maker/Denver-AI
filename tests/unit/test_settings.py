"""Unit tests for Denver Configuration and Settings."""

from __future__ import annotations

import unittest
from pathlib import Path
from denver.config.settings import DenverSettings


class TestDenverSettings(unittest.TestCase):
    """Test suite for Denver configuration loading and masking."""

    def test_default_settings(self) -> None:
        """Verify default configuration parameters."""
        settings = DenverSettings()
        self.assertEqual(settings.assistant_name, "Denver")
        self.assertEqual(settings.product_name, "Denver AI Assistant")
        self.assertEqual(settings.short_name, "Denver")
        self.assertEqual(settings.wake_word, "Denver")
        self.assertEqual(settings.environment, "development")
        self.assertEqual(settings.log_level, "INFO")
        self.assertEqual(settings.database_path, Path("denver_memory.sqlite3"))
        self.assertFalse(settings.privacy_mode)
        self.assertTrue(settings.voice_enabled)
        self.assertTrue(settings.ui_enabled)

    def test_environment_overrides(self) -> None:
        """Verify environment variable parsing and overrides."""
        mock_env = {
            "DENVER_ENVIRONMENT": "production",
            "DENVER_LOG_LEVEL": "DEBUG",
            "DENVER_DATABASE_PATH": "custom_memory.sqlite3",
            "DENVER_PRIVACY_MODE": "true",
            "DENVER_WAKE_WORD": "Denver",
            "DENVER_AI_MODE": "offline",
            "DENVER_GROQ_API_KEY": "gsk_test_secret_key_12345",
        }
        settings = DenverSettings.from_env(mock_env)
        self.assertEqual(settings.environment, "production")
        self.assertEqual(settings.log_level, "DEBUG")
        self.assertEqual(settings.database_path, Path("custom_memory.sqlite3"))
        self.assertTrue(settings.privacy_mode)
        self.assertEqual(settings.ai_mode, "offline")
        self.assertEqual(settings.groq_api_key, "gsk_test_secret_key_12345")

    def test_to_safe_dict_masking(self) -> None:
        """Verify sensitive credentials are redacted in safe dictionary output."""
        settings = DenverSettings(
            groq_api_key="gsk_secret_123",
            gemini_api_key="aiza_secret_456",
        )
        safe = settings.to_safe_dict()
        self.assertEqual(safe["groq_api_key"], "***")
        self.assertEqual(safe["gemini_api_key"], "***")
        self.assertEqual(safe["assistant_name"], "Denver")


if __name__ == "__main__":
    unittest.main()
