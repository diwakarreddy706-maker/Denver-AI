"""Unit tests for Denver Memory Data Controls and Safe Export."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from denver.commands.router import IntentRouter
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.runtime.event_bus import DenverEventBus


class TestMemoryControls(unittest.IsolatedAsyncioTestCase):
    """Test suite for memory controls, safe JSON export, clear notes, and voice routing."""

    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_memory.sqlite3"
        self.export_path = Path(self.temp_dir.name) / "memory_export.json"
        self.db = DenverDatabase(db_path=self.db_path)
        await self.db.initialize()
        self.event_bus = DenverEventBus()
        self.memory = MemoryService(db=self.db, event_bus=self.event_bus)

    async def asyncTearDown(self) -> None:
        await self.db.close()
        await self.event_bus.shutdown()
        self.temp_dir.cleanup()

    async def test_export_safe_memory_with_redaction(self) -> None:
        # Create sample note and preference with sensitive credential
        await self.memory.create_note("API Secrets", "Here is my key: api_key=sk-secret12345")
        await self.memory.set_preference("editor", "vscode")

        payload = await self.memory.export_safe_memory(export_path=self.export_path)

        self.assertTrue(self.export_path.exists())
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["counts"]["notes"], 1)
        self.assertEqual(payload["counts"]["preferences"], 1)

        # Confirm file content is masked
        saved_json = json.loads(self.export_path.read_text(encoding="utf-8"))
        note_content = saved_json["data"]["notes"][0]["content"]
        self.assertNotIn("sk-secret12345", note_content)
        self.assertIn("api_key=***", note_content)

    async def test_clear_all_notes(self) -> None:
        await self.memory.create_note("Note 1", "Content 1")
        await self.memory.create_note("Note 2", "Content 2")
        self.assertEqual(len(await self.memory.list_notes()), 2)

        cleared = await self.memory.clear_all_notes()
        self.assertEqual(cleared, 2)
        self.assertEqual(len(await self.memory.list_notes()), 0)

    def test_voice_intent_routing_for_memory_controls(self) -> None:
        router = IntentRouter()

        res1 = router.route("export my memory data")
        self.assertEqual(res1.intent_name, "export_memory")

        res2 = router.route("export memories")
        self.assertEqual(res2.intent_name, "export_memory")

        res3 = router.route("clear all my notes")
        self.assertEqual(res3.intent_name, "clear_all_notes")

        res4 = router.route("list my saved memories")
        self.assertEqual(res4.intent_name, "list_memories")

        res5 = router.route("show memories")
        self.assertEqual(res5.intent_name, "list_memories")


if __name__ == "__main__":
    unittest.main()
