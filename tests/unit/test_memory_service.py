"""Unit tests for Denver Memory Service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.memory.models import PrivacyLevel
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.events import (
    MemoryCleared,
    MemoryCreated,
    MemoryDeleted,
    MemoryRetrieved,
)


class TestDenverMemoryService(unittest.IsolatedAsyncioTestCase):
    """Test suite for MemoryService operations and EventBus integration."""

    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_memory_service.sqlite3"
        self.db = DenverDatabase(db_path=self.db_path)
        await self.db.initialize()

        self.event_bus = DenverEventBus()
        self.memory = MemoryService(
            db=self.db,
            event_bus=self.event_bus,
            privacy_mode=False,
        )

    async def asyncTearDown(self) -> None:
        await self.db.close()
        await self.event_bus.shutdown()
        self.temp_dir.cleanup()

    async def test_create_and_get_memory(self) -> None:
        """Verify creating and retrieving memory items publishes corresponding events."""
        events_received = []

        async def _on_created(event: MemoryCreated) -> None:
            events_received.append(event)

        async def _on_retrieved(event: MemoryRetrieved) -> None:
            events_received.append(event)

        self.event_bus.subscribe(MemoryCreated, _on_created)
        self.event_bus.subscribe(MemoryRetrieved, _on_retrieved)

        # Create
        item = await self.memory.create_memory(
            category="profile",
            key="location",
            content="Seattle, WA",
            privacy_level=PrivacyLevel.INTERNAL,
            metadata={"source": "user_speech"},
        )
        self.assertIsNotNone(item)
        self.assertEqual(item.content, "Seattle, WA")

        # Get
        fetched = await self.memory.get_memory("profile", "location")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.content, "Seattle, WA")

        # Allow event bus to dispatch
        self.assertEqual(len(events_received), 2)
        self.assertIsInstance(events_received[0], MemoryCreated)
        self.assertIsInstance(events_received[1], MemoryRetrieved)

    async def test_update_and_delete_memory(self) -> None:
        """Verify updating and deleting memories."""
        await self.memory.create_memory("config", "editor", "vscode")
        updated = await self.memory.update_memory("config", "editor", "pycharm")
        self.assertEqual(updated.content, "pycharm")

        deleted = await self.memory.delete_memory("config", "editor")
        self.assertTrue(deleted)
        self.assertIsNone(await self.memory.get_memory("config", "editor"))

    async def test_list_and_search_memories(self) -> None:
        """Verify listing and searching memories."""
        await self.memory.create_memory("notes", "k1", "Remember to buy milk")
        await self.memory.create_memory("notes", "k2", "Remember to review pull requests")
        await self.memory.create_memory("facts", "k3", "Denver is a fast Windows assistant")

        notes = await self.memory.list_memories(category="notes")
        self.assertEqual(len(notes), 2)

        search_results = await self.memory.search_memories("review")
        self.assertEqual(len(search_results), 1)
        self.assertEqual(search_results[0].key, "k2")

    async def test_ephemeral_short_term_buffer(self) -> None:
        """Verify in-memory conversation buffer records and retrieves turns."""
        self.memory.add_conversation_turn("user", "Hello Denver")
        self.memory.add_conversation_turn("denver", "Hello Sir, how can I assist you today?")

        history = self.memory.get_recent_conversation(limit=5)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "denver")

        self.memory.clear_short_term_buffer()
        self.assertEqual(len(self.memory.get_recent_conversation()), 0)

    async def test_context_summary_generation(self) -> None:
        """Verify prompt context summary incorporates preferences, notes, habits, and recent turns."""
        await self.memory.set_preference("favorite_music", "synthwave")
        await self.memory.create_note("Project Repo", "Path is at C:/Dev/AI")
        await self.memory.record_habit("open chrome")
        self.memory.add_conversation_turn("user", "What's the weather?")
        self.memory.add_conversation_turn("denver", "It is 72 degrees and sunny.")

        summary = await self.memory.get_context_summary()
        self.assertIn("[SYSTEM CONTEXT: USER PROFILE & DENVER MEMORY]", summary)
        self.assertIn("favorite_music", summary)
        self.assertIn("synthwave", summary)
        self.assertIn("Project Repo", summary)
        self.assertIn("open chrome", summary)
        self.assertIn("What's the weather?", summary)


if __name__ == "__main__":
    unittest.main()
