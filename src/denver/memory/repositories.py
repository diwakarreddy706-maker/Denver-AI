"""Typed SQLite Repositories for Denver Memory Entities."""

from __future__ import annotations

import json
import sqlite3
import struct
from datetime import datetime, timezone
from typing import Any

from denver.memory.models import (
    AuditRecord,
    CachedLocation,
    CommandHabit,
    MemoryCategory,
    MemoryItem,
    Note,
    PrivacyLevel,
    SavedLocation,
    Task,
    UserPreference,
)


def _parse_dt(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _serialize_vec(vec: list[float]) -> bytes:
    """Pack float array into binary bytes."""
    return struct.pack(f"{len(vec)}f", *vec)


def _deserialize_vec(blob: bytes) -> list[float]:
    """Unpack binary bytes into float array."""
    if not blob:
        return []
    count = len(blob) // 4
    return list(struct.unpack(f"{count}f", blob))


class MemoryItemRepository:
    """Repository for unified generic memory items."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _row_to_item(self, row: Any) -> MemoryItem:
        # Check row length to support both v1 (8 cols) and v2 (16 cols) rows gracefully
        meta = {}
        if row[5]:
            try:
                meta = json.loads(row[5]) if isinstance(row[5], str) else row[5]
            except Exception:
                meta = {}

        if len(row) >= 16:
            return MemoryItem(
                id=row[0],
                category=row[1],
                key=row[2],
                content=row[3],
                privacy_level=PrivacyLevel.from_value(row[4]),
                metadata=meta,
                created_at=_parse_dt(row[6]) or datetime.now(timezone.utc),
                updated_at=_parse_dt(row[7]) or datetime.now(timezone.utc),
                importance=float(row[8]) if row[8] is not None else 0.5,
                confidence=float(row[9]) if row[9] is not None else 1.0,
                source=row[10] or "explicit_user",
                expires_at=_parse_dt(row[11]),
                last_accessed_at=_parse_dt(row[12]) or datetime.now(timezone.utc),
                embedding_status=row[13] or "pending",
                embedding_model=row[14],
                is_deleted=bool(row[15]),
            )
        else:
            return MemoryItem(
                id=row[0],
                category=row[1],
                key=row[2],
                content=row[3],
                privacy_level=PrivacyLevel.from_value(row[4]),
                metadata=meta,
                created_at=_parse_dt(row[6]) or datetime.now(timezone.utc),
                updated_at=_parse_dt(row[7]) or datetime.now(timezone.utc),
            )

    def create_or_update(self, item: MemoryItem) -> MemoryItem:
        """Insert or update a memory item by (category, key)."""
        metadata_json = json.dumps(item.metadata or {})
        privacy_val = item.privacy_level.value if isinstance(item.privacy_level, PrivacyLevel) else str(item.privacy_level)
        cat_val = item.category.value if isinstance(item.category, MemoryCategory) else str(item.category).lower()
        expires_str = item.expires_at.isoformat() if item.expires_at else None

        cursor = self.conn.execute(
            """
            INSERT INTO memory_items (
                category, key, content, privacy_level, metadata,
                importance, confidence, source, expires_at, last_accessed_at,
                embedding_status, embedding_model, is_deleted,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(category, key) DO UPDATE SET
                content = excluded.content,
                privacy_level = excluded.privacy_level,
                metadata = excluded.metadata,
                importance = excluded.importance,
                confidence = excluded.confidence,
                source = excluded.source,
                expires_at = excluded.expires_at,
                last_accessed_at = CURRENT_TIMESTAMP,
                embedding_status = excluded.embedding_status,
                embedding_model = excluded.embedding_model,
                is_deleted = 0,
                updated_at = CURRENT_TIMESTAMP
            RETURNING
                id, category, key, content, privacy_level, metadata, created_at, updated_at,
                importance, confidence, source, expires_at, last_accessed_at, embedding_status, embedding_model, is_deleted;
            """,
            (
                cat_val,
                item.key,
                item.content,
                privacy_val,
                metadata_json,
                item.importance,
                item.confidence,
                item.source,
                expires_str,
                item.embedding_status,
                item.embedding_model,
                1 if item.is_deleted else 0,
            ),
        )
        row = cursor.fetchone()
        return self._row_to_item(row)

    def get_by_id(self, item_id: int) -> MemoryItem | None:
        cursor = self.conn.execute(
            """
            SELECT
                id, category, key, content, privacy_level, metadata, created_at, updated_at,
                importance, confidence, source, expires_at, last_accessed_at, embedding_status, embedding_model, is_deleted
            FROM memory_items WHERE id = ?;
            """,
            (item_id,),
        )
        row = cursor.fetchone()
        return self._row_to_item(row) if row else None

    def get_by_key(self, category: str, key: str) -> MemoryItem | None:
        cursor = self.conn.execute(
            """
            SELECT
                id, category, key, content, privacy_level, metadata, created_at, updated_at,
                importance, confidence, source, expires_at, last_accessed_at, embedding_status, embedding_model, is_deleted
            FROM memory_items WHERE category = ? AND key = ? AND is_deleted = 0;
            """,
            (category.strip().lower(), key.strip()),
        )
        row = cursor.fetchone()
        return self._row_to_item(row) if row else None

    def list_all(self, category: str | None = None, limit: int = 100, offset: int = 0) -> list[MemoryItem]:
        cols = """
            id, category, key, content, privacy_level, metadata, created_at, updated_at,
            importance, confidence, source, expires_at, last_accessed_at, embedding_status, embedding_model, is_deleted
        """
        if category:
            cursor = self.conn.execute(
                f"SELECT {cols} FROM memory_items WHERE category = ? AND is_deleted = 0 ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                (category.strip().lower(), limit, offset),
            )
        else:
            cursor = self.conn.execute(
                f"SELECT {cols} FROM memory_items WHERE is_deleted = 0 ORDER BY updated_at DESC LIMIT ? OFFSET ?;",
                (limit, offset),
            )
        return [self._row_to_item(r) for r in cursor.fetchall()]

    def list_active(self, category: str | None = None) -> list[MemoryItem]:
        """Fetch all active (non-deleted, unexpired) memories."""
        cols = """
            id, category, key, content, privacy_level, metadata, created_at, updated_at,
            importance, confidence, source, expires_at, last_accessed_at, embedding_status, embedding_model, is_deleted
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        if category:
            cursor = self.conn.execute(
                f"""
                SELECT {cols} FROM memory_items
                WHERE category = ? AND is_deleted = 0
                  AND (expires_at IS NULL OR expires_at > ? OR expires_at > CURRENT_TIMESTAMP)
                ORDER BY updated_at DESC;
                """,
                (category.strip().lower(), now_iso),
            )
        else:
            cursor = self.conn.execute(
                f"""
                SELECT {cols} FROM memory_items
                WHERE is_deleted = 0
                  AND (expires_at IS NULL OR expires_at > ? OR expires_at > CURRENT_TIMESTAMP)
                ORDER BY updated_at DESC;
                """,
                (now_iso,),
            )
        return [self._row_to_item(r) for r in cursor.fetchall()]

    def search(self, query: str, category: str | None = None, limit: int = 20) -> list[MemoryItem]:
        pattern = f"%{query}%"
        cols = """
            id, category, key, content, privacy_level, metadata, created_at, updated_at,
            importance, confidence, source, expires_at, last_accessed_at, embedding_status, embedding_model, is_deleted
        """
        if category:
            cursor = self.conn.execute(
                f"""
                SELECT {cols}
                FROM memory_items
                WHERE category = ? AND (key LIKE ? OR content LIKE ?) AND is_deleted = 0
                ORDER BY updated_at DESC
                LIMIT ?;
                """,
                (category.strip().lower(), pattern, pattern, limit),
            )
        else:
            cursor = self.conn.execute(
                f"""
                SELECT {cols}
                FROM memory_items
                WHERE (key LIKE ? OR content LIKE ?) AND is_deleted = 0
                ORDER BY updated_at DESC
                LIMIT ?;
                """,
                (pattern, pattern, limit),
            )
        return [self._row_to_item(r) for r in cursor.fetchall()]

    def touch_access(self, item_id: int) -> None:
        """Update last_accessed_at timestamp."""
        self.conn.execute(
            "UPDATE memory_items SET last_accessed_at = CURRENT_TIMESTAMP WHERE id = ?;",
            (item_id,),
        )

    def delete_by_id(self, item_id: int, hard: bool = False) -> bool:
        if hard:
            cursor = self.conn.execute("DELETE FROM memory_items WHERE id = ?;", (item_id,))
        else:
            cursor = self.conn.execute("UPDATE memory_items SET is_deleted = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?;", (item_id,))
        return cursor.rowcount > 0

    def delete_by_key(self, category: str, key: str, hard: bool = False) -> bool:
        if hard:
            cursor = self.conn.execute("DELETE FROM memory_items WHERE category = ? AND key = ?;", (category.strip().lower(), key.strip()))
        else:
            cursor = self.conn.execute("UPDATE memory_items SET is_deleted = 1, updated_at = CURRENT_TIMESTAMP WHERE category = ? AND key = ?;", (category.strip().lower(), key.strip()))
        return cursor.rowcount > 0

    def clear_all(self, category: str | None = None) -> int:
        if category:
            cursor = self.conn.execute("DELETE FROM memory_items WHERE category = ?;", (category.strip().lower(),))
        else:
            cursor = self.conn.execute("DELETE FROM memory_items;")
        return cursor.rowcount

    def purge_expired(self) -> int:
        """Hard delete expired memories."""
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.execute(
            "DELETE FROM memory_items WHERE expires_at IS NOT NULL AND (expires_at <= ? OR expires_at <= CURRENT_TIMESTAMP);",
            (now_iso,),
        )
        return cursor.rowcount


class EmbeddingRepository:
    """Repository for storing and retrieving float embeddings as BLOBs."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def save_embedding(self, entity_type: str, entity_id: int, content_chunk: str, vector: list[float]) -> None:
        blob = _serialize_vec(vector)
        # Delete existing embedding for entity
        self.conn.execute(
            "DELETE FROM memory_embeddings WHERE entity_type = ? AND entity_id = ?;",
            (entity_type, entity_id),
        )
        self.conn.execute(
            """
            INSERT INTO memory_embeddings (entity_type, entity_id, content_chunk, embedding, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP);
            """,
            (entity_type, entity_id, content_chunk, blob),
        )

    def get_embeddings_map(self, entity_type: str = "memory_item") -> dict[int, list[float]]:
        cursor = self.conn.execute(
            "SELECT entity_id, embedding FROM memory_embeddings WHERE entity_type = ?;",
            (entity_type,),
        )
        res: dict[int, list[float]] = {}
        for row in cursor.fetchall():
            if row[0] is not None and row[1]:
                res[row[0]] = _deserialize_vec(row[1])
        return res

    def delete_embedding(self, entity_type: str, entity_id: int) -> bool:
        cursor = self.conn.execute(
            "DELETE FROM memory_embeddings WHERE entity_type = ? AND entity_id = ?;",
            (entity_type, entity_id),
        )
        return cursor.rowcount > 0


class UserPreferencesRepository:
    """Repository for user configuration preferences."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def set_preference(
        self,
        key: str,
        value: str,
        category: str = "general",
        confidence: float = 1.0,
        source: str = "explicit_user",
    ) -> UserPreference:
        cursor = self.conn.execute(
            """
            INSERT INTO user_preferences (key, value, category, confidence, source, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                category = excluded.category,
                confidence = excluded.confidence,
                source = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            RETURNING key, value, category, confidence, source, updated_at;
            """,
            (key.strip(), value, category.strip().lower(), confidence, source),
        )
        row = cursor.fetchone()
        return UserPreference(
            key=row[0],
            value=row[1],
            category=row[2],
            confidence=float(row[3]) if row[3] is not None else 1.0,
            source=row[4] or "explicit_user",
            updated_at=_parse_dt(row[5]) or datetime.now(timezone.utc),
        )

    def get_preference(self, key: str) -> UserPreference | None:
        cursor = self.conn.execute(
            "SELECT key, value, category, confidence, source, updated_at FROM user_preferences WHERE key = ?;",
            (key.strip(),),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return UserPreference(
            key=row[0],
            value=row[1],
            category=row[2],
            confidence=float(row[3]) if row[3] is not None else 1.0,
            source=row[4] or "explicit_user",
            updated_at=_parse_dt(row[5]) or datetime.now(timezone.utc),
        )

    def list_preferences(self, category: str | None = None) -> list[UserPreference]:
        if category:
            cursor = self.conn.execute(
                "SELECT key, value, category, confidence, source, updated_at FROM user_preferences WHERE category = ? ORDER BY updated_at DESC;",
                (category.strip().lower(),),
            )
        else:
            cursor = self.conn.execute(
                "SELECT key, value, category, confidence, source, updated_at FROM user_preferences ORDER BY updated_at DESC;"
            )
        return [
            UserPreference(
                key=r[0],
                value=r[1],
                category=r[2],
                confidence=float(r[3]) if r[3] is not None else 1.0,
                source=r[4] or "explicit_user",
                updated_at=_parse_dt(r[5]) or datetime.now(timezone.utc),
            )
            for r in cursor.fetchall()
        ]

    def delete_preference(self, key: str) -> bool:
        cursor = self.conn.execute("DELETE FROM user_preferences WHERE key = ?;", (key.strip(),))
        return cursor.rowcount > 0

    def clear_preferences(self) -> int:
        cursor = self.conn.execute("DELETE FROM user_preferences;")
        return cursor.rowcount


class NotesRepository:
    """Repository for user notes."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_note(self, title: str, content: str, tags: list[str] | None = None, is_pinned: bool = False) -> Note:
        tags_json = json.dumps(tags or [])
        cursor = self.conn.execute(
            """
            INSERT INTO notes (title, content, tags, is_pinned, created_at, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id, title, content, tags, is_pinned, created_at, updated_at;
            """,
            (title, content, tags_json, 1 if is_pinned else 0),
        )
        row = cursor.fetchone()
        return self._row_to_note(row)

    def _row_to_note(self, row: Any) -> Note:
        tags = []
        if row[3]:
            try:
                tags = json.loads(row[3]) if isinstance(row[3], str) else row[3]
            except Exception:
                tags = []
        return Note(
            id=row[0],
            title=row[1] or "",
            content=row[2],
            tags=tags,
            is_pinned=bool(row[4]),
            created_at=_parse_dt(row[5]) or datetime.now(timezone.utc),
            updated_at=_parse_dt(row[6]) or datetime.now(timezone.utc),
        )

    def get_note(self, note_id: int) -> Note | None:
        cursor = self.conn.execute(
            "SELECT id, title, content, tags, is_pinned, created_at, updated_at FROM notes WHERE id = ?;",
            (note_id,),
        )
        row = cursor.fetchone()
        return self._row_to_note(row) if row else None

    def list_notes(self, limit: int = 50, pinned_first: bool = True) -> list[Note]:
        order = "is_pinned DESC, updated_at DESC" if pinned_first else "updated_at DESC"
        cursor = self.conn.execute(
            f"SELECT id, title, content, tags, is_pinned, created_at, updated_at FROM notes ORDER BY {order} LIMIT ?;",
            (limit,),
        )
        return [self._row_to_note(r) for r in cursor.fetchall()]

    def search_notes(self, query: str, limit: int = 20) -> list[Note]:
        pattern = f"%{query}%"
        cursor = self.conn.execute(
            """
            SELECT id, title, content, tags, is_pinned, created_at, updated_at
            FROM notes
            WHERE title LIKE ? OR content LIKE ?
            ORDER BY updated_at DESC
            LIMIT ?;
            """,
            (pattern, pattern, limit),
        )
        return [self._row_to_note(r) for r in cursor.fetchall()]

    def update_note(self, note_id: int, title: str | None = None, content: str | None = None, is_pinned: bool | None = None) -> Note | None:
        existing = self.get_note(note_id)
        if not existing:
            return None
        new_title = title if title is not None else existing.title
        new_content = content if content is not None else existing.content
        new_pinned = is_pinned if is_pinned is not None else existing.is_pinned

        cursor = self.conn.execute(
            """
            UPDATE notes
            SET title = ?, content = ?, is_pinned = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING id, title, content, tags, is_pinned, created_at, updated_at;
            """,
            (new_title, new_content, 1 if new_pinned else 0, note_id),
        )
        row = cursor.fetchone()
        return self._row_to_note(row) if row else None

    def delete_note(self, note_id: int) -> bool:
        cursor = self.conn.execute("DELETE FROM notes WHERE id = ?;", (note_id,))
        return cursor.rowcount > 0

    def clear_notes(self) -> int:
        cursor = self.conn.execute("DELETE FROM notes;")
        return cursor.rowcount


class TasksRepository:
    """Repository for scheduled tasks and reminders."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_task(self, task_text: str, due_at: datetime | None = None) -> Task:
        due_str = due_at.isoformat() if due_at else None
        cursor = self.conn.execute(
            """
            INSERT INTO tasks (task_text, due_at, is_completed, reminder_sent, created_at)
            VALUES (?, ?, 0, 0, CURRENT_TIMESTAMP)
            RETURNING id, task_text, due_at, is_completed, reminder_sent, created_at;
            """,
            (task_text, due_str),
        )
        row = cursor.fetchone()
        return Task(
            id=row[0],
            task_text=row[1],
            due_at=_parse_dt(row[2]),
            is_completed=bool(row[3]),
            reminder_sent=bool(row[4]),
            created_at=_parse_dt(row[5]) or datetime.now(timezone.utc),
        )

    def list_tasks(self, include_completed: bool = False, limit: int = 50) -> list[Task]:
        where_clause = "" if include_completed else "WHERE is_completed = 0"
        cursor = self.conn.execute(
            f"SELECT id, task_text, due_at, is_completed, reminder_sent, created_at FROM tasks {where_clause} ORDER BY created_at DESC LIMIT ?;",
            (limit,),
        )
        return [
            Task(
                id=r[0],
                task_text=r[1],
                due_at=_parse_dt(r[2]),
                is_completed=bool(r[3]),
                reminder_sent=bool(r[4]),
                created_at=_parse_dt(r[5]) or datetime.now(timezone.utc),
            )
            for r in cursor.fetchall()
        ]

    def complete_task(self, task_id: int) -> bool:
        cursor = self.conn.execute("UPDATE tasks SET is_completed = 1 WHERE id = ?;", (task_id,))
        return cursor.rowcount > 0

    def delete_task(self, task_id: int) -> bool:
        cursor = self.conn.execute("DELETE FROM tasks WHERE id = ?;", (task_id,))
        return cursor.rowcount > 0

    def clear_tasks(self) -> int:
        cursor = self.conn.execute("DELETE FROM tasks;")
        return cursor.rowcount


class HabitsRepository:
    """Repository for command habits."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def record_habit(self, command_phrase: str) -> CommandHabit:
        phrase = command_phrase.strip().lower()
        cursor = self.conn.execute(
            """
            INSERT INTO command_habits (command_phrase, execution_count, last_executed_at)
            VALUES (?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(command_phrase) DO UPDATE SET
                execution_count = command_habits.execution_count + 1,
                last_executed_at = CURRENT_TIMESTAMP
            RETURNING command_phrase, execution_count, last_executed_at;
            """,
            (phrase,),
        )
        row = cursor.fetchone()
        return CommandHabit(
            command_phrase=row[0],
            execution_count=row[1],
            last_executed_at=_parse_dt(row[2]) or datetime.now(timezone.utc),
        )

    def list_top_habits(self, limit: int = 10) -> list[CommandHabit]:
        cursor = self.conn.execute(
            "SELECT command_phrase, execution_count, last_executed_at FROM command_habits ORDER BY execution_count DESC LIMIT ?;",
            (limit,),
        )
        return [
            CommandHabit(
                command_phrase=r[0],
                execution_count=r[1],
                last_executed_at=_parse_dt(r[2]) or datetime.now(timezone.utc),
            )
            for r in cursor.fetchall()
        ]

    def clear_habits(self) -> int:
        cursor = self.conn.execute("DELETE FROM command_habits;")
        return cursor.rowcount


class AuditLogRepository:
    """Repository for structured command audit records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def append_record(
        self,
        raw_command: str,
        routed_action: str,
        provider_used: str,
        status: str,
        latency_ms: float,
    ) -> AuditRecord:
        cursor = self.conn.execute(
            """
            INSERT INTO command_audit_log (raw_command, routed_action, provider_used, status, latency_ms, created_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            RETURNING id, raw_command, routed_action, provider_used, status, latency_ms, created_at;
            """,
            (raw_command, routed_action, provider_used, status, latency_ms),
        )
        row = cursor.fetchone()
        return AuditRecord(
            id=row[0],
            raw_command=row[1],
            routed_action=row[2],
            provider_used=row[3],
            status=row[4],
            latency_ms=row[5],
            created_at=_parse_dt(row[6]) or datetime.now(timezone.utc),
        )

    def list_recent(self, limit: int = 50) -> list[AuditRecord]:
        cursor = self.conn.execute(
            "SELECT id, raw_command, routed_action, provider_used, status, latency_ms, created_at FROM command_audit_log ORDER BY created_at DESC LIMIT ?;",
            (limit,),
        )
        return [
            AuditRecord(
                id=r[0],
                raw_command=r[1],
                routed_action=r[2],
                provider_used=r[3],
                status=r[4],
                latency_ms=r[5],
                created_at=_parse_dt(r[6]) or datetime.now(timezone.utc),
            )
            for r in cursor.fetchall()
        ]

    def clear_audit_logs(self) -> int:
        cursor = self.conn.execute("DELETE FROM command_audit_log;")
        return cursor.rowcount


class SavedLocationRepository:
    """Repository for user saved locations and addresses."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def save_location(
        self,
        label: str,
        raw_address: str,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> SavedLocation:
        clean_label = label.strip().lower()
        clean_address = raw_address.strip()
        cursor = self.conn.execute(
            """
            INSERT INTO saved_locations (label, raw_address, latitude, longitude, created_at, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(label) DO UPDATE SET
                raw_address = excluded.raw_address,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id, label, raw_address, latitude, longitude, created_at, updated_at;
            """,
            (clean_label, clean_address, latitude, longitude),
        )
        row = cursor.fetchone()
        return SavedLocation(
            id=row[0],
            label=row[1],
            raw_address=row[2],
            latitude=float(row[3]) if row[3] is not None else None,
            longitude=float(row[4]) if row[4] is not None else None,
            created_at=_parse_dt(row[5]) or datetime.now(timezone.utc),
            updated_at=_parse_dt(row[6]) or datetime.now(timezone.utc),
        )

    def get_by_label(self, label: str) -> SavedLocation | None:
        clean_label = label.strip().lower()
        cursor = self.conn.execute(
            "SELECT id, label, raw_address, latitude, longitude, created_at, updated_at FROM saved_locations WHERE label = ?;",
            (clean_label,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return SavedLocation(
            id=row[0],
            label=row[1],
            raw_address=row[2],
            latitude=float(row[3]) if row[3] is not None else None,
            longitude=float(row[4]) if row[4] is not None else None,
            created_at=_parse_dt(row[5]) or datetime.now(timezone.utc),
            updated_at=_parse_dt(row[6]) or datetime.now(timezone.utc),
        )

    def list_all(self) -> list[SavedLocation]:
        cursor = self.conn.execute(
            "SELECT id, label, raw_address, latitude, longitude, created_at, updated_at FROM saved_locations ORDER BY label ASC;"
        )
        return [
            SavedLocation(
                id=r[0],
                label=r[1],
                raw_address=r[2],
                latitude=float(r[3]) if r[3] is not None else None,
                longitude=float(r[4]) if r[4] is not None else None,
                created_at=_parse_dt(r[5]) or datetime.now(timezone.utc),
                updated_at=_parse_dt(r[6]) or datetime.now(timezone.utc),
            )
            for r in cursor.fetchall()
        ]

    def delete_by_label(self, label: str) -> bool:
        clean_label = label.strip().lower()
        cursor = self.conn.execute(
            "DELETE FROM saved_locations WHERE label = ?;",
            (clean_label,),
        )
        return cursor.rowcount > 0

    def clear_locations(self) -> int:
        cursor = self.conn.execute("DELETE FROM saved_locations;")
        return cursor.rowcount


class LocationCacheRepository:
    """Repository for persisting and retrieving the single latest cached live location."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get_cached_location(self) -> CachedLocation | None:
        """Fetch the single cached location row if it exists."""
        cursor = self.conn.execute(
            """
            SELECT id, latitude, longitude, city, region, country, formatted_address, detected_at
            FROM location_cache
            WHERE id = 1;
            """
        )
        row = cursor.fetchone()
        if not row:
            return None
        return CachedLocation(
            id=row[0],
            latitude=float(row[1]),
            longitude=float(row[2]),
            city=row[3],
            region=row[4],
            country=row[5],
            formatted_address=row[6],
            detected_at=_parse_dt(row[7]) or datetime.now(timezone.utc),
        )

    def save_cached_location(
        self,
        latitude: float,
        longitude: float,
        city: str | None = None,
        region: str | None = None,
        country: str | None = None,
        formatted_address: str | None = None,
    ) -> CachedLocation:
        """Upsert the single cached location row at id = 1 with CURRENT_TIMESTAMP."""
        cursor = self.conn.execute(
            """
            INSERT INTO location_cache (id, latitude, longitude, city, region, country, formatted_address, detected_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                city = excluded.city,
                region = excluded.region,
                country = excluded.country,
                formatted_address = excluded.formatted_address,
                detected_at = CURRENT_TIMESTAMP
            RETURNING id, latitude, longitude, city, region, country, formatted_address, detected_at;
            """,
            (latitude, longitude, city, region, country, formatted_address),
        )
        row = cursor.fetchone()
        return CachedLocation(
            id=row[0],
            latitude=float(row[1]),
            longitude=float(row[2]),
            city=row[3],
            region=row[4],
            country=row[5],
            formatted_address=row[6],
            detected_at=_parse_dt(row[7]) or datetime.now(timezone.utc),
        )

    def clear_cache(self) -> int:
        """Clear the location cache table."""
        cursor = self.conn.execute("DELETE FROM location_cache;")
        return cursor.rowcount

