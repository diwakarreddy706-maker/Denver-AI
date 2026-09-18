"""Unified Memory Service API for Denver AI Assistant (Phase 7 Advanced Intelligence)."""

from __future__ import annotations

import collections
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from denver.logging.logger import get_logger
from denver.memory.database import DenverDatabase
from denver.memory.deduplication import MemoryDeduplicator
from denver.memory.embeddings import (
    DeterministicLexicalEmbedder,
    EmbeddingManager,
    EmbeddingProvider,
    OllamaEmbeddingProvider,
)
from denver.memory.expiration import ExpirationManager, compute_expiration_for_category
from denver.memory.models import (
    AuditRecord,
    CachedLocation,
    CommandHabit,
    MemoryCategory,
    MemoryItem,
    MemorySearchResult,
    Note,
    PrivacyLevel,
    SavedLocation,
    Task,
    UserPreference,
)
from denver.memory.ranking import MemoryRanker
from denver.memory.repositories import (
    AuditLogRepository,
    EmbeddingRepository,
    HabitsRepository,
    LocationCacheRepository,
    MemoryItemRepository,
    NotesRepository,
    SavedLocationRepository,
    TasksRepository,
    UserPreferencesRepository,
)
from denver.memory.search import MemorySearchCoordinator
from denver.runtime.event_bus import DenverEventBus, get_event_bus
from denver.runtime.events import (
    EmbeddingCompleted,
    EmbeddingFailed,
    EmbeddingStarted,
    MemoryCleared,
    MemoryCreated,
    MemoryDeduplicated,
    MemoryDeleted,
    MemoryExpired,
    MemoryRetrieved,
    MemoryUpdated,
)

logger = get_logger("memory")

# Secret redaction pattern for pre-storage sanitization
_SECRET_PATTERN = re.compile(
    r"(?i)\b(api[-_]?key|auth[-_]?token|password|secret|bearer)\b\s*[:=]\s*([^\s,;]+)",
    re.IGNORECASE,
)


def _sanitize_text(text: str) -> str:
    """Pre-save sanitization masking accidental sensitive keys/tokens."""
    if not text:
        return text
    return _SECRET_PATTERN.sub(r"\1=***", text)


class MemoryService:
    """Central Memory Service orchestrating Ephemeral buffer, Relational SQLite, Vector Embeddings, and Privacy Guard."""

    def __init__(
        self,
        db: DenverDatabase,
        event_bus: DenverEventBus | None = None,
        privacy_mode: bool = False,
        embedding_provider: EmbeddingProvider | None = None,
        semantic_enabled: bool = True,
    ) -> None:
        self.db = db
        self.event_bus = event_bus or get_event_bus()
        self._privacy_mode = privacy_mode
        self._short_term_buffer: collections.deque[dict[str, Any]] = collections.deque(maxlen=20)

        # Initialize Phase 7 Embedding & Search Engines
        fallback_embedder = DeterministicLexicalEmbedder()
        self.embedding_manager = EmbeddingManager(
            primary_provider=embedding_provider,
            fallback_provider=fallback_embedder,
            enabled=semantic_enabled,
        )
        self.ranker = MemoryRanker()
        self.search_coordinator = MemorySearchCoordinator(self.embedding_manager, self.ranker)
        self.deduplicator = MemoryDeduplicator()

    @property
    def privacy_mode(self) -> bool:
        """Check if Privacy Mode is currently active."""
        return self._privacy_mode

    def set_privacy_mode(self, enabled: bool) -> None:
        """Toggle Privacy Mode dynamically."""
        self._privacy_mode = enabled
        logger.info("Denver Memory privacy mode set to: %s", enabled)

    # -------------------------------------------------------------------------
    # Ephemeral Short-Term Buffer (Tier 1)
    # -------------------------------------------------------------------------
    def add_conversation_turn(self, role: str, content: str) -> None:
        """Record a single conversational turn in the ephemeral in-memory ring buffer."""
        clean_content = _sanitize_text(content)
        self._short_term_buffer.append({
            "role": role,
            "content": clean_content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_recent_conversation(self, limit: int = 10) -> list[dict[str, Any]]:
        """Retrieve recent conversation turns from the ephemeral buffer."""
        items = list(self._short_term_buffer)
        return items[-limit:]

    def clear_short_term_buffer(self) -> None:
        """Clear the in-memory ephemeral buffer."""
        self._short_term_buffer.clear()

    # -------------------------------------------------------------------------
    # Generic & Semantic Memory Items API (Tier 2)
    # -------------------------------------------------------------------------
    async def create_memory(
        self,
        category: str | MemoryCategory,
        key: str,
        content: str,
        privacy_level: PrivacyLevel = PrivacyLevel.PRIVATE,
        importance: float = 0.5,
        confidence: float = 1.0,
        source: str = "explicit_user",
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        check_dedup: bool = True,
    ) -> MemoryItem | None:
        """Create or update a generic memory item with deduplication, scoring, and embeddings."""
        if not category or not key or content is None:
            raise ValueError("Category, key, and content are required for memory creation.")

        clean_content = _sanitize_text(content)
        cat_val = category.value if isinstance(category, MemoryCategory) else str(category).strip().lower()
        priv_level = PrivacyLevel.from_value(privacy_level)

        # Compute auto-expiration if not provided
        if expires_at is None:
            expires_at = compute_expiration_for_category(cat_val, priv_level)

        if self._privacy_mode:
            logger.debug("Privacy mode active: skipping SQLite persistence for memory (%s:%s).", cat_val, key)
            return MemoryItem(
                id=None,
                category=cat_val,
                key=key.strip(),
                content=clean_content,
                privacy_level=priv_level,
                importance=importance,
                confidence=confidence,
                source=source,
                expires_at=expires_at,
                metadata=metadata or {},
            )

        # 1. Compute embedding vector
        vec, model_name = await self.embedding_manager.embed(clean_content)

        # 2. Check for deduplication / memory correction
        if check_dedup:
            existing_items = await self.list_memories(category=cat_val, limit=200)
            embeddings_map = await self._get_embeddings_map()
            matching_item, match_type = self.deduplicator.find_duplicate(
                new_content=clean_content,
                category=cat_val,
                key=key,
                existing_items=existing_items,
                new_embedding=vec,
                embeddings_map=embeddings_map,
            )
            if matching_item:
                logger.info("Deduplication matched existing memory (id=%s, match=%s). Updating.", matching_item.id, match_type)
                key_to_use = matching_item.key
                # Latest explicit statement wins: update content & timestamps
                item_to_save = MemoryItem(
                    id=matching_item.id,
                    category=cat_val,
                    key=key_to_use,
                    content=clean_content,
                    privacy_level=priv_level,
                    importance=max(matching_item.importance, importance),
                    confidence=confidence,
                    source=source,
                    expires_at=expires_at,
                    embedding_status="embedded" if vec else "none",
                    embedding_model=model_name,
                    metadata=metadata or matching_item.metadata,
                )

                def _update_op(conn) -> MemoryItem:
                    repo = MemoryItemRepository(conn)
                    saved_item = repo.create_or_update(item_to_save)
                    if vec and saved_item.id is not None:
                        emb_repo = EmbeddingRepository(conn)
                        emb_repo.save_embedding("memory_item", saved_item.id, clean_content, vec)
                    return saved_item

                saved = await self.db.run_async(_update_op)
                await self.event_bus.publish(
                    MemoryDeduplicated(category=cat_val, key=key_to_use, match_type=match_type)
                )
                await self.event_bus.publish(
                    MemoryUpdated(category=cat_val, key=key_to_use, privacy_level=priv_level.value)
                )
                return saved

        # 3. Create fresh item
        item = MemoryItem(
            id=None,
            category=cat_val,
            key=key.strip(),
            content=clean_content,
            privacy_level=priv_level,
            importance=importance,
            confidence=confidence,
            source=source,
            expires_at=expires_at,
            embedding_status="embedded" if vec else "none",
            embedding_model=model_name,
            metadata=metadata or {},
        )

        def _insert_op(conn) -> MemoryItem:
            repo = MemoryItemRepository(conn)
            saved_item = repo.create_or_update(item)
            if vec and saved_item.id is not None:
                emb_repo = EmbeddingRepository(conn)
                emb_repo.save_embedding("memory_item", saved_item.id, clean_content, vec)
            return saved_item

        saved = await self.db.run_async(_insert_op)
        logger.debug("Created memory [%s:%s] (id=%s).", saved.category, saved.key, saved.id)

        await self.event_bus.publish(
            MemoryCreated(
                category=saved.category,
                key=saved.key,
                privacy_level=saved.privacy_level.value,
            )
        )
        return saved

    async def _get_embeddings_map(self) -> dict[int, list[float]]:
        def _op(conn) -> dict[int, list[float]]:
            repo = EmbeddingRepository(conn)
            return repo.get_embeddings_map("memory_item")
        return await self.db.run_async(_op)

    async def get_memory(self, category: str, key: str) -> MemoryItem | None:
        """Retrieve a memory item by category and key."""
        if not category or not key:
            return None

        clean_cat = category.strip().lower()
        clean_k = key.strip()

        def _op(conn) -> MemoryItem | None:
            repo = MemoryItemRepository(conn)
            item = repo.get_by_key(clean_cat, clean_k)
            if item and item.id is not None:
                repo.touch_access(item.id)
            return item

        item = await self.db.run_async(_op)
        if item:
            await self.event_bus.publish(
                MemoryRetrieved(
                    category=item.category,
                    key=item.key,
                    privacy_level=item.privacy_level.value,
                )
            )
        return item

    async def update_memory(
        self,
        category: str,
        key: str,
        content: str,
        privacy_level: PrivacyLevel = PrivacyLevel.PRIVATE,
        importance: float = 0.5,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem | None:
        """Update an existing memory item."""
        return await self.create_memory(
            category=category,
            key=key,
            content=content,
            privacy_level=privacy_level,
            importance=importance,
            confidence=confidence,
            metadata=metadata,
            check_dedup=False,
        )

    async def delete_memory(self, category: str, key: str, hard: bool = False) -> bool:
        """Delete a memory item by category and key."""
        clean_cat = category.strip().lower()
        clean_k = key.strip()

        def _op(conn) -> bool:
            repo = MemoryItemRepository(conn)
            return repo.delete_by_key(clean_cat, clean_k, hard=hard)

        deleted = await self.db.run_async(_op)
        if deleted:
            await self.event_bus.publish(
                MemoryDeleted(category=clean_cat, key=clean_k)
            )
        return deleted

    async def list_memories(
        self,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryItem]:
        """List stored memory items."""
        clean_cat = category.strip().lower() if category else None

        def _op(conn) -> list[MemoryItem]:
            repo = MemoryItemRepository(conn)
            return repo.list_all(category=clean_cat, limit=limit, offset=offset)

        return await self.db.run_async(_op)

    async def list_active_memories(self, category: str | None = None) -> list[MemoryItem]:
        """List active, non-expired memory items."""
        clean_cat = category.strip().lower() if category else None

        def _op(conn) -> list[MemoryItem]:
            repo = MemoryItemRepository(conn)
            return repo.list_active(category=clean_cat)

        return await self.db.run_async(_op)

    async def search_memories(
        self,
        query: str,
        category: str | None = None,
        limit: int = 20,
    ) -> list[MemoryItem]:
        """Basic keyword search across memory items."""
        if not query:
            return []

        clean_cat = category.strip().lower() if category else None

        def _op(conn) -> list[MemoryItem]:
            repo = MemoryItemRepository(conn)
            return repo.search(query=query, category=clean_cat, limit=limit)

        return await self.db.run_async(_op)

    async def hybrid_search(
        self,
        query: str,
        category: str | MemoryCategory | None = None,
        allowed_privacy: set[PrivacyLevel] | None = None,
        top_k: int = 8,
        min_score: float = 0.15,
    ) -> list[MemorySearchResult]:
        """Execute hybrid semantic + lexical search with multi-factor ranking."""
        if not query or not query.strip():
            return []

        active_items = await self.list_active_memories()
        embeddings_map = await self._get_embeddings_map()

        results = await self.search_coordinator.search(
            query=query,
            active_items=active_items,
            embeddings_map=embeddings_map,
            category=category,
            allowed_privacy=allowed_privacy,
            top_k=top_k,
            min_score=min_score,
        )

        # Update last_accessed_at for top results
        if results:
            def _touch_op(conn) -> None:
                repo = MemoryItemRepository(conn)
                for res in results[:3]:
                    if res.memory.id is not None:
                        repo.touch_access(res.memory.id)
            await self.db.run_async(_touch_op)

        return results

    async def semantic_search(
        self,
        query: str,
        category: str | None = None,
        top_k: int = 8,
    ) -> list[MemorySearchResult]:
        """Semantic search convenience wrapper."""
        return await self.hybrid_search(query=query, category=category, top_k=top_k)

    async def remember(
        self,
        content: str,
        category: MemoryCategory = MemoryCategory.FACT,
        key: str | None = None,
        importance: float = 0.7,
        confidence: float = 1.0,
        privacy_level: PrivacyLevel = PrivacyLevel.PRIVATE,
    ) -> MemoryItem | None:
        """Natural memory remember API."""
        if not key:
            # Generate deterministic key from first few words or hash
            tokens = re.findall(r"\b\w+\b", content)
            key = "_".join(tokens[:4]).lower() if tokens else f"mem_{int(time.time())}"
        return await self.create_memory(
            category=category,
            key=key,
            content=content,
            privacy_level=privacy_level,
            importance=importance,
            confidence=confidence,
            source="explicit_user",
        )

    async def recall(
        self,
        query: str,
        category: str | None = None,
        top_k: int = 5,
    ) -> list[MemorySearchResult]:
        """Natural memory recall API."""
        return await self.hybrid_search(query=query, category=category, top_k=top_k)

    async def forget(
        self,
        query: str | None = None,
        category: str | None = None,
        key: str | None = None,
    ) -> int:
        """Forget memory by exact key, category, or semantic match."""
        if category and key:
            deleted = await self.delete_memory(category, key, hard=False)
            return 1 if deleted else 0

        if query:
            clean_q = query.strip().lower()
            deleted_count = 0

            # Check if query matches preferences (including aliases)
            candidate_pref_keys = [clean_q, f"favorite_{clean_q}"]
            if clean_q.startswith("favorite_"):
                candidate_pref_keys.append(clean_q[len("favorite_"):])

            for pref_key in candidate_pref_keys:
                if await self.delete_preference(pref_key):
                    deleted_count += 1

            matches = await self.hybrid_search(query=query, category=category, top_k=5, min_score=0.5)
            for match in matches:
                if match.memory.category and match.memory.key:
                    if await self.delete_memory(match.memory.category, match.memory.key, hard=False):
                        deleted_count += 1
            return deleted_count


        if category:
            return await self.clear_memories(category=category)

        return 0

    async def cleanup_expired(self) -> int:
        """Purge expired memories by TTL."""
        def _op(conn) -> int:
            repo = MemoryItemRepository(conn)
            return repo.purge_expired()

        count = await self.db.run_async(_op)
        if count > 0:
            logger.info("Purged %d expired memory records.", count)
            await self.event_bus.publish(MemoryExpired(purged_count=count))
        return count

    async def clear_memories(self, category: str | None = None) -> int:
        """Clear memory items."""
        clean_cat = category.strip().lower() if category else None

        def _op(conn) -> int:
            repo = MemoryItemRepository(conn)
            return repo.clear_all(category=clean_cat)

        count = await self.db.run_async(_op)
        await self.event_bus.publish(
            MemoryCleared(category=clean_cat, count=count)
        )
        return count

    # -------------------------------------------------------------------------
    # Specialized Relational Repositories (Preferences, Notes, Tasks, Habits, Audits)
    # -------------------------------------------------------------------------
    async def set_preference(
        self,
        key: str,
        value: str,
        category: str = "general",
        confidence: float = 1.0,
        source: str = "explicit_user",
    ) -> UserPreference | None:
        """Store or update a user preference."""
        if not key:
            raise ValueError("Preference key cannot be empty.")

        clean_val = _sanitize_text(value)

        if self._privacy_mode:
            logger.debug("Privacy mode active: skipping SQLite persistence for preference '%s'.", key)
            return UserPreference(key=key, value=clean_val, category=category, confidence=confidence, source=source)

        def _op(conn) -> UserPreference:
            repo = UserPreferencesRepository(conn)
            return repo.set_preference(key=key, value=clean_val, category=category, confidence=confidence, source=source)

        saved = await self.db.run_async(_op)
        # Also mirror into memory_items under category 'preference' for unified semantic search
        await self.create_memory(
            category=MemoryCategory.PREFERENCE,
            key=f"pref_{key}",
            content=f"User preference: {key} is {clean_val}",
            privacy_level=PrivacyLevel.PRIVATE,
            importance=0.9,
            confidence=confidence,
            source=source,
            check_dedup=False,
        )
        return saved

    async def get_preference(self, key: str) -> UserPreference | None:
        """Get a user preference by key."""
        def _op(conn) -> UserPreference | None:
            repo = UserPreferencesRepository(conn)
            return repo.get_preference(key)

        return await self.db.run_async(_op)

    async def list_preferences(self, category: str | None = None) -> list[UserPreference]:
        """List user preferences."""
        def _op(conn) -> list[UserPreference]:
            repo = UserPreferencesRepository(conn)
            return repo.list_preferences(category)

        return await self.db.run_async(_op)

    async def delete_preference(self, key: str) -> bool:
        """Delete a user preference."""
        def _op(conn) -> bool:
            repo = UserPreferencesRepository(conn)
            return repo.delete_preference(key)

        deleted = await self.db.run_async(_op)
        if deleted:
            await self.delete_memory(MemoryCategory.PREFERENCE.value, f"pref_{key}", hard=False)
        return deleted

    async def create_note(
        self,
        title: str,
        content: str,
        tags: list[str] | None = None,
        is_pinned: bool = False,
    ) -> Note | None:
        """Create a user note."""
        clean_content = _sanitize_text(content)

        if self._privacy_mode:
            return Note(id=None, title=title, content=clean_content, tags=tags or [], is_pinned=is_pinned)

        def _op(conn) -> Note:
            repo = NotesRepository(conn)
            return repo.create_note(title=title, content=clean_content, tags=tags, is_pinned=is_pinned)

        return await self.db.run_async(_op)

    async def get_note(self, note_id: int) -> Note | None:
        """Get a note by ID."""
        def _op(conn) -> Note | None:
            repo = NotesRepository(conn)
            return repo.get_note(note_id)

        return await self.db.run_async(_op)

    async def list_notes(self, limit: int = 50, pinned_first: bool = True) -> list[Note]:
        """List user notes."""
        def _op(conn) -> list[Note]:
            repo = NotesRepository(conn)
            return repo.list_notes(limit=limit, pinned_first=pinned_first)

        return await self.db.run_async(_op)

    async def search_notes(self, query: str, limit: int = 20) -> list[Note]:
        """Search notes."""
        def _op(conn) -> list[Note]:
            repo = NotesRepository(conn)
            return repo.search_notes(query=query, limit=limit)

        return await self.db.run_async(_op)

    async def update_note(
        self,
        note_id: int,
        title: str | None = None,
        content: str | None = None,
        is_pinned: bool | None = None,
    ) -> Note | None:
        """Update a note."""
        clean_content = _sanitize_text(content) if content else None

        def _op(conn) -> Note | None:
            repo = NotesRepository(conn)
            return repo.update_note(note_id, title=title, content=clean_content, is_pinned=is_pinned)

        return await self.db.run_async(_op)

    async def delete_note(self, note_id: int) -> bool:
        """Delete a note."""
        def _op(conn) -> bool:
            repo = NotesRepository(conn)
            return repo.delete_note(note_id)

        return await self.db.run_async(_op)

    async def create_task(self, task_text: str, due_at: datetime | None = None) -> Task | None:
        """Create a scheduled task."""
        clean_text = _sanitize_text(task_text)

        if self._privacy_mode:
            return Task(id=None, task_text=clean_text, due_at=due_at)

        def _op(conn) -> Task:
            repo = TasksRepository(conn)
            return repo.create_task(task_text=clean_text, due_at=due_at)

        return await self.db.run_async(_op)

    async def list_tasks(self, include_completed: bool = False, limit: int = 50) -> list[Task]:
        """List scheduled tasks."""
        def _op(conn) -> list[Task]:
            repo = TasksRepository(conn)
            return repo.list_tasks(include_completed=include_completed, limit=limit)

        return await self.db.run_async(_op)

    async def complete_task(self, task_id: int) -> bool:
        """Mark a task as completed."""
        def _op(conn) -> bool:
            repo = TasksRepository(conn)
            return repo.complete_task(task_id)

        return await self.db.run_async(_op)

    async def delete_task(self, task_id: int) -> bool:
        """Delete a task."""
        def _op(conn) -> bool:
            repo = TasksRepository(conn)
            return repo.delete_task(task_id)

        return await self.db.run_async(_op)

    async def record_habit(self, command_phrase: str) -> CommandHabit | None:
        """Record command execution frequency."""
        if self._privacy_mode:
            return None

        def _op(conn) -> CommandHabit:
            repo = HabitsRepository(conn)
            return repo.record_habit(command_phrase)

        return await self.db.run_async(_op)

    async def list_habits(self, limit: int = 10) -> list[CommandHabit]:
        """List frequent command habits."""
        def _op(conn) -> list[CommandHabit]:
            repo = HabitsRepository(conn)
            return repo.list_top_habits(limit=limit)

        return await self.db.run_async(_op)

    async def log_audit(
        self,
        raw_command: str,
        routed_action: str,
        provider_used: str,
        status: str,
        latency_ms: float,
    ) -> AuditRecord | None:
        """Record command audit record."""
        clean_cmd = _sanitize_text(raw_command)

        if self._privacy_mode:
            return None

        def _op(conn) -> AuditRecord:
            repo = AuditLogRepository(conn)
            return repo.append_record(
                raw_command=clean_cmd,
                routed_action=routed_action,
                provider_used=provider_used,
                status=status,
                latency_ms=latency_ms,
            )

        return await self.db.run_async(_op)

    async def list_audit_logs(self, limit: int = 50) -> list[AuditRecord]:
        """List audit records."""
        def _op(conn) -> list[AuditRecord]:
            repo = AuditLogRepository(conn)
            return repo.list_recent(limit=limit)

        return await self.db.run_async(_op)

    async def get_memory_stats(self) -> dict[str, Any]:
        """Retrieve total and active memory statistics for health & Cockpit."""
        all_mems = await self.list_memories(limit=10000)
        active_mems = await self.list_active_memories()
        notes = await self.list_notes(limit=1000)
        tasks = await self.list_tasks(limit=1000)
        prefs = await self.list_preferences()

        emb_health = await self.embedding_manager.get_health_status()

        return {
            "total_memories": len(all_mems),
            "active_memories": len(active_mems),
            "notes_count": len(notes),
            "tasks_count": len(tasks),
            "preferences_count": len(prefs),
            "privacy_mode": self._privacy_mode,
            "semantic_enabled": self.embedding_manager.enabled,
            "embedding_provider": emb_health.get("active_provider", "deterministic_lexical"),
        }

    async def get_context_summary(self) -> str:
        """Synthesize compact context summary string for AI prompts."""
        prefs = await self.list_preferences()
        active_mems = await self.list_active_memories()
        notes = await self.list_notes(limit=5)
        habits = await self.list_habits(limit=5)
        recents = self.get_recent_conversation(limit=4)

        pref_dict = {p.key: p.value for p in prefs}
        fact_mems = [m.content for m in active_mems[:5] if m.category in (MemoryCategory.FACT.value, MemoryCategory.PROJECT.value, MemoryCategory.PROFILE.value)]
        notes_list = [f"{n.title}: {n.content}" if n.title else n.content for n in notes]
        habits_list = [h.command_phrase for h in habits]

        lines = ["[SYSTEM CONTEXT: USER PROFILE & DENVER MEMORY]"]
        if pref_dict:
            lines.append(f"- User Preferences: {pref_dict}")
        if fact_mems:
            lines.append(f"- Known Facts/Projects: {fact_mems}")
        if notes_list:
            lines.append(f"- Saved Notes: {notes_list}")
        if habits_list:
            lines.append(f"- Frequent Habits: {habits_list}")
        if recents:
            lines.append("- Recent Conversation:")
            for turn in recents:
                lines.append(f"  {turn.get('role', 'user').capitalize()}: \"{turn.get('content', '')}\"")

        return "\n".join(lines)

    # ---------------------------------------------------------
    # Saved Locations API (Phase 10 Weather & Navigation)
    # ---------------------------------------------------------

    async def save_location(
        self,
        label: str,
        raw_address: str,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> SavedLocation:
        """Persist a named user location with optional geocoded coordinates."""
        def _op(conn: Any) -> SavedLocation:
            repo = SavedLocationRepository(conn)
            return repo.save_location(label, raw_address, latitude, longitude)

        return await self.db.run_async(_op)

    async def get_saved_location(self, label: str) -> SavedLocation | None:
        """Retrieve a saved location by its case-insensitive label (e.g. 'home', 'office')."""
        def _op(conn: Any) -> SavedLocation | None:
            repo = SavedLocationRepository(conn)
            return repo.get_by_label(label)

        return await self.db.run_async(_op)

    async def list_saved_locations(self) -> list[SavedLocation]:
        """List all saved user locations."""
        def _op(conn: Any) -> list[SavedLocation]:
            repo = SavedLocationRepository(conn)
            return repo.list_all()

        return await self.db.run_async(_op)

    async def delete_saved_location(self, label: str) -> bool:
        """Delete a saved location by label."""
        def _op(conn: Any) -> bool:
            repo = SavedLocationRepository(conn)
            return repo.delete_by_label(label)

        return await self.db.run_async(_op)

    # ---------------------------------------------------------
    # Live Location Cache API (Phase 11)
    # ---------------------------------------------------------

    async def get_cached_location(self) -> CachedLocation | None:
        """Retrieve the latest persisted live location cache."""
        def _op(conn: Any) -> CachedLocation | None:
            repo = LocationCacheRepository(conn)
            return repo.get_cached_location()

        return await self.db.run_async(_op)

    async def save_cached_location(
        self,
        latitude: float,
        longitude: float,
        city: str | None = None,
        region: str | None = None,
        country: str | None = None,
        formatted_address: str | None = None,
    ) -> CachedLocation:
        """Persist/upsert the latest detected live location into the SQLite cache."""
        def _op(conn: Any) -> CachedLocation:
            repo = LocationCacheRepository(conn)
            return repo.save_cached_location(
                latitude=latitude,
                longitude=longitude,
                city=city,
                region=region,
                country=country,
                formatted_address=formatted_address,
            )

        return await self.db.run_async(_op)

    async def clear_cached_location(self) -> int:
        """Clear the location cache table."""
        def _op(conn: Any) -> int:
            repo = LocationCacheRepository(conn)
            return repo.clear_cache()

        return await self.db.run_async(_op)

    # ---------------------------------------------------------
    # Safe Memory Export & Lifecycle Controls
    # ---------------------------------------------------------

    async def export_safe_memory(self, export_path: str | Path = "data/memory_export.json") -> dict[str, Any]:
        """Export a privacy-masked, sanitized memory snapshot to JSON."""
        import json
        out_file = Path(export_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        notes = await self.list_notes()
        prefs = await self.list_preferences()
        habits = await self.list_habits()
        locations = await self.list_saved_locations()
        tasks = await self.list_tasks()

        sanitized_notes = [
            {
                "id": n.id,
                "title": _sanitize_text(n.title),
                "content": _sanitize_text(n.content),
                "tags": n.tags,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notes
        ]

        sanitized_prefs = [
            {
                "key": p.key,
                "value": _sanitize_text(str(p.value)),
                "category": p.category,
            }
            for p in prefs
        ]

        payload = {
            "schema_version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "privacy_mode": self._privacy_mode,
            "counts": {
                "notes": len(sanitized_notes),
                "preferences": len(sanitized_prefs),
                "habits": len(habits),
                "saved_locations": len(locations),
                "tasks": len(tasks),
            },
            "data": {
                "notes": sanitized_notes,
                "preferences": sanitized_prefs,
                "habits": [{"command": h.command_phrase, "execution_count": h.execution_count} for h in habits],
                "saved_locations": [{"label": loc.label, "address": loc.raw_address} for loc in locations],
                "tasks": [{"task_text": t.task_text, "is_completed": t.is_completed} for t in tasks],
            },
        }

        from denver.utils.atomic_write import atomic_write_json
        atomic_write_json(out_file, payload)
        return payload

    async def clear_all_notes(self) -> int:
        """Clear all user notes with zero-leakage cleanup."""
        notes = await self.list_notes()
        count = 0
        for n in notes:
            if n.id:
                await self.delete_note(n.id)
                count += 1
        return count


