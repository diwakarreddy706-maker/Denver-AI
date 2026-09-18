"""Unit tests for Denver Credential Vault."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from denver.security.vault import DenverVault


class TestDenverVault(unittest.TestCase):
    """Test suite for Windows DPAPI backed DenverVault."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault_path = Path(self.temp_dir.name) / "vault.dat"
        self.vault = DenverVault(vault_path=self.vault_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_store_and_retrieve_secret(self) -> None:
        """Verify storing and retrieving a secret returns the original plaintext."""
        self.vault.set_secret("GROQ_API_KEY", "gsk_test_api_key_12345")
        retrieved = self.vault.get_secret("GROQ_API_KEY")
        self.assertEqual(retrieved, "gsk_test_api_key_12345")

    def test_overwrite_secret(self) -> None:
        """Verify overwriting an existing secret updates the decrypted value."""
        self.vault.set_secret("GEMINI_API_KEY", "initial_key_secret")
        self.vault.set_secret("GEMINI_API_KEY", "updated_key_secret")
        self.assertEqual(self.vault.get_secret("GEMINI_API_KEY"), "updated_key_secret")

    def test_delete_secret(self) -> None:
        """Verify deleting a secret removes it from the vault."""
        self.vault.set_secret("TEMP_SECRET", "temp_val")
        self.assertTrue(self.vault.has_secret("TEMP_SECRET"))
        deleted = self.vault.delete_secret("TEMP_SECRET")
        self.assertTrue(deleted)
        self.assertFalse(self.vault.has_secret("TEMP_SECRET"))
        self.assertIsNone(self.vault.get_secret("TEMP_SECRET"))

    def test_missing_secret(self) -> None:
        """Verify retrieving non-existent secret returns None."""
        self.assertIsNone(self.vault.get_secret("NON_EXISTENT_KEY"))
        self.assertFalse(self.vault.has_secret("NON_EXISTENT_KEY"))

    def test_list_secret_names(self) -> None:
        """Verify listing secret names returns all stored keys without values."""
        self.vault.set_secret("KEY_B", "val_b")
        self.vault.set_secret("KEY_A", "val_a")
        self.vault.set_secret("KEY_C", "val_c")
        names = self.vault.list_secret_names()
        self.assertEqual(names, ["KEY_A", "KEY_B", "KEY_C"])

    def test_clear_all_secrets(self) -> None:
        """Verify clearing vault purges all keys."""
        self.vault.set_secret("KEY_1", "v1")
        self.vault.set_secret("KEY_2", "v2")
        cleared_count = self.vault.clear_all_secrets()
        self.assertEqual(cleared_count, 2)
        self.assertEqual(self.vault.list_secret_names(), [])

    def test_plaintext_never_written_to_disk(self) -> None:
        """CRITICAL SECURITY TEST: Ensure raw secret string never appears in vault file."""
        secret_value = "super_confidential_token_987654321"
        self.vault.set_secret("TEST_SECRET", secret_value)

        raw_file_content = self.vault_path.read_text(encoding="utf-8")
        self.assertNotIn(secret_value, raw_file_content)

        # File should be valid JSON containing base64 ciphertext
        data = json.loads(raw_file_content)
        self.assertIn("TEST_SECRET", data)
        self.assertNotEqual(data["TEST_SECRET"], secret_value)

    def test_invalid_arguments_raise_error(self) -> None:
        """Verify invalid secret names or values raise ValueError."""
        with self.assertRaises(ValueError):
            self.vault.set_secret("", "valid_val")
        with self.assertRaises(ValueError):
            self.vault.set_secret("VALID_NAME", None)  # type: ignore


if __name__ == "__main__":
    unittest.main()
