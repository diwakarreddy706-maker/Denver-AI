"""Unit tests for Phase 7 memory models, PrivacyLevel compatibility, and SQLite migration v2."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from denver.memory.expiration import compute_expiration_for_category
from denver.memory.migrations import MigrationManager, SCHEMA_V1_SQL
from denver.memory.models import (
    MemoryCategory,
    MemoryItem,
    MemorySearchResult,
    PrivacyLevel,
    UserPreference,
)
from denver.memory.repositories import MemoryItemRepository, UserPreferencesRepository


def test_privacy_level_backward_compatibility() -> None:
    """Verify legacy privacy values (PUBLIC, INTERNAL, SENSITIVE, CONFIDENTIAL) and new Phase 7 values."""
    assert PrivacyLevel.PUBLIC.value == "public"
    assert PrivacyLevel.INTERNAL.value == "internal"
    assert PrivacyLevel.SENSITIVE.value == "sensitive"
    assert PrivacyLevel.CONFIDENTIAL.value == "confidential"

    assert PrivacyLevel.PUBLIC_CONTEXT.value == "public_context"
    assert PrivacyLevel.PRIVATE.value == "private"
    assert PrivacyLevel.EPHEMERAL.value == "ephemeral"

    # Coercion tests
    assert PrivacyLevel.from_value("public") == PrivacyLevel.PUBLIC
    assert PrivacyLevel.from_value("PUBLIC") == PrivacyLevel.PUBLIC
    assert PrivacyLevel.from_value("internal") == PrivacyLevel.INTERNAL
    assert PrivacyLevel.from_value("private") == PrivacyLevel.PRIVATE
    assert PrivacyLevel.from_value("sensitive") == PrivacyLevel.SENSITIVE
    assert PrivacyLevel.from_value("unknown_val") == PrivacyLevel.PRIVATE

    # Cloud eligibility
    assert PrivacyLevel.PUBLIC.is_cloud_eligible is True
    assert PrivacyLevel.PUBLIC_CONTEXT.is_cloud_eligible is True
    assert PrivacyLevel.PRIVATE.is_cloud_eligible is False
    assert PrivacyLevel.SENSITIVE.is_cloud_eligible is False


def test_memory_category_enums() -> None:
    """Verify structured memory categories."""
    assert MemoryCategory.FACT.value == "fact"
    assert MemoryCategory.PREFERENCE.value == "preference"
    assert MemoryCategory.PROFILE.value == "profile"
    assert MemoryCategory.PROJECT.value == "project"
    assert MemoryCategory.TASK.value == "task"
    assert MemoryCategory.PERSON.value == "person"
    assert MemoryCategory.CONTEXT.value == "context"
    assert MemoryCategory.CONVERSATION.value == "conversation"
    assert MemoryCategory.SYSTEM.value == "system"

    assert MemoryCategory.from_value("PROJECT") == MemoryCategory.PROJECT
    assert MemoryCategory.from_value("invalid_cat") == MemoryCategory.GENERAL


def test_memory_item_initialization_and_bounds() -> None:
    """Verify importance, confidence clamping and expiration check."""
    item = MemoryItem(
        id=1,
        category=MemoryCategory.FACT,
        key="test_key",
        content="Test content",
        importance=1.5,  # should clamp to 1.0
        confidence=-0.5,  # should clamp to 0.0
        privacy_level="sensitive",
    )
    assert item.importance == 1.0
    assert item.confidence == 0.0
    assert item.privacy_level == PrivacyLevel.SENSITIVE
    assert item.category == "fact"
    assert item.is_expired is False

    # Test expired item
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    expired_item = MemoryItem(
        id=2,
        category="fact",
        key="exp_key",
        content="Expired",
        expires_at=past_time,
    )
    assert expired_item.is_expired is True


def test_compute_expiration_rules() -> None:
    """Verify category-based and privacy-based expiration rules."""
    # Ephemeral expires in ~2 hours
    exp_eph = compute_expiration_for_category(MemoryCategory.FACT, PrivacyLevel.EPHEMERAL)
    assert exp_eph is not None
    assert (exp_eph - datetime.now(timezone.utc)).total_seconds() > 3600

    # Conversation expires in ~24 hours
    exp_conv = compute_expiration_for_category(MemoryCategory.CONVERSATION, PrivacyLevel.PRIVATE)
    assert exp_conv is not None
    assert (exp_conv - datetime.now(timezone.utc)).total_seconds() > 3600 * 20

    # Permanent categories do not expire by default
    exp_pref = compute_expiration_for_category(MemoryCategory.PREFERENCE, PrivacyLevel.PRIVATE)
    assert exp_pref is None

    exp_proj = compute_expiration_for_category(MemoryCategory.PROJECT, PrivacyLevel.PRIVATE)
    assert exp_proj is None


def test_migration_v1_to_v2_preserves_data(tmp_path: Path) -> None:
    """Verify that MigrationManager upgrades a v1 database to v2 while preserving existing data."""
    db_file = tmp_path / "test_mig.sqlite3"
    conn = sqlite3.connect(db_file)

    # 1. Initialize strictly schema v1
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            description TEXT NOT NULL
        );
        """
    )
    conn.executescript(SCHEMA_V1_SQL)
    conn.execute("INSERT INTO schema_migrations (version, description) VALUES (1, 'Initial Denver schema');")

    # Insert v1 data
    conn.execute(
        "INSERT INTO user_preferences (key, value, category) VALUES ('theme', 'cyber_cyan', 'ui');"
    )
    conn.execute(
        "INSERT INTO memory_items (category, key, content, privacy_level) VALUES ('general', 'fav_color', 'Blue', 'internal');"
    )
    conn.commit()

    # 2. Run MigrationManager to apply pending v2 migration
    mgr = MigrationManager(conn)
    applied = mgr.apply_pending_migrations()
    assert applied >= 1
    assert mgr.get_current_version() >= 2

    # 3. Verify existing data preserved
    pref_repo = UserPreferencesRepository(conn)
    pref = pref_repo.get_preference("theme")
    assert pref is not None
    assert pref.value == "cyber_cyan"
    assert pref.confidence == 1.0  # default added

    mem_repo = MemoryItemRepository(conn)
    mem = mem_repo.get_by_key("general", "fav_color")
    assert mem is not None
    assert mem.content == "Blue"
    assert mem.importance == 0.5  # default added
    assert mem.confidence == 1.0  # default added
    assert mem.is_deleted is False

    # 4. Insert new Phase 7 memory record
    new_mem = MemoryItem(
        id=None,
        category=MemoryCategory.PROJECT,
        key="sentinel_job",
        content="SentinelJob is an AI-based Fake Job Detection Platform",
        importance=0.9,
        confidence=1.0,
        privacy_level=PrivacyLevel.PRIVATE,
    )
    saved = mem_repo.create_or_update(new_mem)
    assert saved.id is not None
    assert saved.importance == 0.9
    assert saved.category == "project"

    conn.close()
