"""Unit tests for Denver SQLite Database, Pragmas, and Migrations."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from denver.memory.database import DenverDatabase
from denver.memory.migrations import MigrationManager
from denver.memory.models import MemoryItem, PrivacyLevel
from denver.memory.repositories import (
    AuditLogRepository,
    HabitsRepository,
    MemoryItemRepository,
    NotesRepository,
    TasksRepository,
    UserPreferencesRepository,
)


class TestDenverDatabase(unittest.IsolatedAsyncioTestCase):
    """Test suite for SQLite connection manager, pragmas, and repositories."""

    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_memory.sqlite3"
        self.db = DenverDatabase(db_path=self.db_path)
        await self.db.initialize()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.temp_dir.cleanup()

    async def test_database_initialization_and_pragmas(self) -> None:
        """Verify database connects with WAL mode, foreign keys, and synchronous normal."""
        conn = self.db.connect_sync()

        # Check journal mode
        cur = conn.execute("PRAGMA journal_mode;")
        journal_mode = cur.fetchone()[0]
        self.assertEqual(journal_mode.lower(), "wal")

        # Check foreign keys
        cur = conn.execute("PRAGMA foreign_keys;")
        foreign_keys = cur.fetchone()[0]
        self.assertEqual(foreign_keys, 1)

        # Check busy timeout
        cur = conn.execute("PRAGMA busy_timeout;")
        busy_timeout = cur.fetchone()[0]
        self.assertEqual(busy_timeout, 5000)

    async def test_schema_migrations_applied(self) -> None:
        """Verify schema version tracking table and tables creation."""
        conn = self.db.connect_sync()
        migrator = MigrationManager(conn)
        version = migrator.get_current_version()
        self.assertGreaterEqual(version, 1)

        # Verify all expected tables exist
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cur.fetchall()}
        expected = {
            "schema_migrations",
            "user_preferences",
            "notes",
            "tasks",
            "command_habits",
            "command_audit_log",
            "memory_items",
            "memory_embeddings",
        }
        for table in expected:
            self.assertIn(table, tables, f"Expected table '{table}' in database.")

    async def test_memory_item_repository(self) -> None:
        """Verify MemoryItemRepository CRUD, search, and constraints."""
        item = MemoryItem(
            id=None,
            category="profile",
            key="user_name",
            content="Alex",
            privacy_level=PrivacyLevel.INTERNAL,
            metadata={"source": "cli"},
        )

        def _insert(conn) -> MemoryItem:
            repo = MemoryItemRepository(conn)
            return repo.create_or_update(item)

        saved = await self.db.run_async(_insert)
        self.assertIsNotNone(saved.id)
        self.assertEqual(saved.category, "profile")
        self.assertEqual(saved.key, "user_name")
        self.assertEqual(saved.content, "Alex")

        # Update same category + key
        item_updated = MemoryItem(
            id=None,
            category="profile",
            key="user_name",
            content="Alexander",
            privacy_level=PrivacyLevel.INTERNAL,
        )

        def _update(conn) -> MemoryItem:
            repo = MemoryItemRepository(conn)
            return repo.create_or_update(item_updated)

        updated = await self.db.run_async(_update)
        self.assertEqual(updated.id, saved.id)
        self.assertEqual(updated.content, "Alexander")

        # Search
        def _search(conn):
            repo = MemoryItemRepository(conn)
            return repo.search("Alex")

        results = await self.db.run_async(_search)
        self.assertEqual(len(results), 1)

        # Delete
        def _delete(conn) -> bool:
            repo = MemoryItemRepository(conn)
            return repo.delete_by_key("profile", "user_name")

        self.assertTrue(await self.db.run_async(_delete))

    async def test_specialized_repositories(self) -> None:
        """Verify preferences, notes, tasks, habits, and audit repositories."""
        def _test_all(conn):
            # 1. Preferences
            pref_repo = UserPreferencesRepository(conn)
            p = pref_repo.set_preference("theme", "dark", "ui")
            self.assertEqual(p.value, "dark")
            self.assertEqual(pref_repo.get_preference("theme").value, "dark")

            # 2. Notes
            notes_repo = NotesRepository(conn)
            n = notes_repo.create_note("Meeting", "Discuss Phase 1 roadmap", tags=["work"], is_pinned=True)
            self.assertIsNotNone(n.id)
            self.assertEqual(len(notes_repo.list_notes()), 1)
            self.assertEqual(len(notes_repo.search_notes("roadmap")), 1)

            # 3. Tasks
            tasks_repo = TasksRepository(conn)
            t = tasks_repo.create_task("Implement Denver vault")
            self.assertFalse(t.is_completed)
            tasks_repo.complete_task(t.id)
            self.assertEqual(len(tasks_repo.list_tasks(include_completed=False)), 0)
            self.assertEqual(len(tasks_repo.list_tasks(include_completed=True)), 1)

            # 4. Habits
            habits_repo = HabitsRepository(conn)
            habits_repo.record_habit("check cpu")
            habits_repo.record_habit("check cpu")
            top = habits_repo.list_top_habits()
            self.assertEqual(top[0].command_phrase, "check cpu")
            self.assertEqual(top[0].execution_count, 2)

            # 5. Audit Log
            audit_repo = AuditLogRepository(conn)
            rec = audit_repo.append_record(
                raw_command="open notepad",
                routed_action="launch_app",
                provider_used="rules",
                status="success",
                latency_ms=12.5,
            )
            self.assertIsNotNone(rec.id)
            self.assertEqual(len(audit_repo.list_recent()), 1)

        await self.db.run_async(_test_all)

    async def test_health_status(self) -> None:
        """Verify database health status inspection."""
        health = self.db.get_health_status()
        self.assertEqual(health["status"], "READY")
        self.assertTrue(health["connected"])
        self.assertEqual(health["journal_mode"].lower(), "wal")
        self.assertGreaterEqual(health["schema_version"], 1)
        self.assertEqual(health["integrity"], "ok")


if __name__ == "__main__":
    unittest.main()
