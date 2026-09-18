"""Unit tests for Denver Privacy Controls and Secret Redaction."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.runtime.event_bus import DenverEventBus


class TestDenverPrivacyControls(unittest.IsolatedAsyncioTestCase):
    """Test suite for privacy modes, zero-persistence, and secret redaction."""

    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_privacy.sqlite3"
        self.db = DenverDatabase(db_path=self.db_path)
        await self.db.initialize()
        self.event_bus = DenverEventBus()
        self.memory = MemoryService(db=self.db, event_bus=self.event_bus, privacy_mode=False)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        await self.event_bus.shutdown()
        self.temp_dir.cleanup()

    async def test_privacy_mode_prevents_persistence(self) -> None:
        """Verify that when privacy mode is enabled, items are NOT committed to SQLite."""
        self.memory.set_privacy_mode(True)
        self.assertTrue(self.memory.privacy_mode)

        # Attempt to create memory
        mem = await self.memory.create_memory("sensitive_cat", "secret_key", "Confidential user thought")
        self.assertIsNone(mem.id)

        # Query database directly to confirm 0 records written
        stored_items = await self.memory.list_memories(category="sensitive_cat")
        self.assertEqual(len(stored_items), 0)

        # Attempt preference write
        pref = await self.memory.set_preference("private_pref", "val")
        stored_pref = await self.memory.get_preference("private_pref")
        self.assertIsNone(stored_pref)

    async def test_pre_save_secret_redaction(self) -> None:
        """Verify secret tokens and API keys are masked before saving to SQLite."""
        raw_text = "My OpenAI key is api_key=sk-proj-123456789 and password: mySuperSecretPassword123"
        item = await self.memory.create_memory("credentials", "test_note", raw_text)

        # Verify persisted content in DB
        fetched = await self.memory.get_memory("credentials", "test_note")
        self.assertIsNotNone(fetched)
        self.assertNotIn("sk-proj-123456789", fetched.content)
        self.assertNotIn("mySuperSecretPassword123", fetched.content)
        self.assertIn("api_key=***", fetched.content)

    async def test_short_term_buffer_secret_redaction(self) -> None:
        """Verify ephemeral conversation buffer also redacts secrets."""
        self.memory.add_conversation_turn("user", "Here is my secret token: auth_token=secret_abc123xyz")
        history = self.memory.get_recent_conversation()
        self.assertNotIn("secret_abc123xyz", history[0]["content"])
        self.assertIn("auth_token=***", history[0]["content"])


if __name__ == "__main__":
    unittest.main()
