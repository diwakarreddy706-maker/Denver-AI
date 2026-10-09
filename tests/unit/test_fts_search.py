"""Unit tests for Denver Database Option A: True FTS5 BM25 search & two-stage hybrid RAG."""

from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path

from denver.memory.database import DenverDatabase, sanitize_fts_query
from denver.memory.migrations import MigrationManager
from denver.memory.models import MemoryItem, Note, PrivacyLevel
from denver.memory.repositories import MemoryItemRepository, NotesRepository
from denver.rag.service import DocumentRAGService


def test_sanitize_fts_query() -> None:
    """Test query sanitization for safe SQLite FTS5 MATCH expressions."""
    assert sanitize_fts_query("") == ""
    assert sanitize_fts_query("   ") == ""
    assert sanitize_fts_query("denver") == '"denver"*'
    assert sanitize_fts_query("hello world") == '"hello"* "world"*'
    assert sanitize_fts_query("special: (characters) & 'quotes'*") == '"special"* "characters"* "quotes"*'


def test_migration_v10_applies_cleanly(tmp_path: Path) -> None:
    """Verify migration v10 applies successfully and creates all FTS5 virtual tables."""
    db_file = tmp_path / "test_migration_v10.sqlite3"
    conn = sqlite3.connect(str(db_file))
    migrator = MigrationManager(conn)
    applied = migrator.apply_pending_migrations()
    assert applied >= 10
    assert migrator.get_current_version() >= 10

    # Verify FTS tables exist in sqlite_master
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_fts';")
    fts_tables = {row[0] for row in cursor.fetchall()}
    assert "memory_items_fts" in fts_tables
    assert "notes_fts" in fts_tables
    assert "document_chunks_fts" in fts_tables
    conn.close()


def test_memory_items_fts_search(tmp_path: Path) -> None:
    """Test that MemoryItemRepository search utilizes FTS5 and finds matching records."""
    db_file = tmp_path / "test_mem_fts.sqlite3"
    db = DenverDatabase(db_file)
    conn = db.connect_sync()
    migrator = MigrationManager(conn)
    migrator.apply_pending_migrations()

    repo = MemoryItemRepository(conn)

    # Insert items
    item1 = MemoryItem(
        id=None,
        category="work",
        key="project_deadline",
        content="The annual fiscal report deadline is scheduled for November 15th.",
        privacy_level=PrivacyLevel.INTERNAL,
    )
    item2 = MemoryItem(
        id=None,
        category="personal",
        key="grocery_list",
        content="Buy fresh apples, almond milk, and whole grain bread.",
        privacy_level=PrivacyLevel.PUBLIC,
    )
    repo.create_or_update(item1)
    repo.create_or_update(item2)

    # Search with exact word
    results = repo.search("deadline")
    assert len(results) >= 1
    assert results[0].key == "project_deadline"

    # Search with prefix (stem)
    results_stem = repo.search("schedul")
    assert len(results_stem) >= 1
    assert results_stem[0].key == "project_deadline"

    # Category filtered search
    results_cat = repo.search("apples", category="personal")
    assert len(results_cat) == 1
    assert results_cat[0].key == "grocery_list"

    results_wrong_cat = repo.search("apples", category="work")
    assert len(results_wrong_cat) == 0

    # Fallback search when FTS has no tokens
    empty_results = repo.search("nonexistent_word_xyz")
    assert len(empty_results) == 0

    db.close_sync()


def test_notes_fts_search(tmp_path: Path) -> None:
    """Test NotesRepository FTS5 BM25 ranked search and trigger synchronization."""
    db_file = tmp_path / "test_notes_fts.sqlite3"
    db = DenverDatabase(db_file)
    conn = db.connect_sync()
    migrator = MigrationManager(conn)
    migrator.apply_pending_migrations()

    repo = NotesRepository(conn)

    # Create notes
    n1 = repo.create_note(title="Weekly Sprint", content="Discuss architecture upgrades and database indexes.")
    n2 = repo.create_note(title="Weekend Trip", content="Pack hiking gear and trail maps.")

    # Search by title keyword
    sprint_res = repo.search_notes("Sprint")
    assert len(sprint_res) >= 1
    assert sprint_res[0].id == n1.id

    # Search by content keyword
    hiking_res = repo.search_notes("hiking")
    assert len(hiking_res) >= 1
    assert hiking_res[0].id == n2.id

    # Update note and verify trigger updates FTS table
    assert n2.id is not None
    repo.update_note(n2.id, content="Pack kayak and paddle gear instead.")
    assert len(repo.search_notes("hiking")) == 0
    assert len(repo.search_notes("kayak")) >= 1

    # Delete note and verify removal from search
    assert n1.id is not None
    repo.delete_note(n1.id)
    assert len(repo.search_notes("Sprint")) == 0

    db.close_sync()


@pytest.mark.asyncio
async def test_rag_two_stage_hybrid_search(tmp_path: Path) -> None:
    """Test DocumentRAGService two-stage retrieval (FTS5 BM25 candidate generation + vector re-ranking)."""
    db_file = tmp_path / "test_rag_fts.sqlite3"
    rag = DocumentRAGService(str(db_file))

    # Create dummy files to index
    doc1 = tmp_path / "denver_specs.txt"
    doc1.write_text("Denver AI architecture includes an asynchronous SQLite memory database and HUD wake overlay.")

    doc2 = tmp_path / "cooking_recipes.txt"
    doc2.write_text("Sourdough bread requires flour, water, salt, and active sourdough starter.")

    await rag.index_file(doc1)
    await rag.index_file(doc2)

    # Search query matching first document
    results = await rag.search_chunks(query="database architecture", top_k=2)
    assert len(results) >= 1
    assert results[0].file_name == "denver_specs.txt"
    assert "Denver AI architecture" in results[0].snippet

    # Search query matching second document with file filter
    bread_results = await rag.search_chunks(query="sourdough", file_filter="recipes")
    assert len(bread_results) >= 1
    assert bread_results[0].file_name == "cooking_recipes.txt"
