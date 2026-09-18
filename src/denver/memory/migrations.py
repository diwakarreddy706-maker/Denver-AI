"""Database schema migrations for Denver Memory."""

from __future__ import annotations

import sqlite3
from typing import Callable

from denver.logging.logger import get_logger

logger = get_logger("migrations")

SCHEMA_V1_SQL = """
-- 1. User Preferences Table
CREATE TABLE IF NOT EXISTS user_preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Notes & Persistent Reminders
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    content TEXT NOT NULL,
    tags TEXT DEFAULT '[]',
    is_pinned BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Scheduled Tasks & Reminders
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_text TEXT NOT NULL,
    due_at TIMESTAMP,
    is_completed BOOLEAN DEFAULT 0,
    reminder_sent BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Command Habit Frequency & Time-Series
CREATE TABLE IF NOT EXISTS command_habits (
    command_phrase TEXT PRIMARY KEY,
    execution_count INTEGER DEFAULT 1,
    last_executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Structured Audit Trail
CREATE TABLE IF NOT EXISTS command_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_command TEXT NOT NULL,
    routed_action TEXT NOT NULL,
    provider_used TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Generic Memory Items (Unified Key-Value & Categorized Memory with Privacy Classifications)
CREATE TABLE IF NOT EXISTS memory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL DEFAULT 'general',
    key TEXT NOT NULL,
    content TEXT NOT NULL,
    privacy_level TEXT NOT NULL DEFAULT 'internal',
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_memory_category_key UNIQUE (category, key)
);

-- 7. Vector Embeddings Table (Semantic Recall)
CREATE TABLE IF NOT EXISTS memory_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    content_chunk TEXT NOT NULL,
    embedding BLOB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_preferences_category ON user_preferences(category);
CREATE INDEX IF NOT EXISTS idx_notes_pinned ON notes(is_pinned);
CREATE INDEX IF NOT EXISTS idx_tasks_due_completed ON tasks(due_at, is_completed);
CREATE INDEX IF NOT EXISTS idx_memory_category ON memory_items(category);
CREATE INDEX IF NOT EXISTS idx_memory_privacy ON memory_items(privacy_level);
CREATE INDEX IF NOT EXISTS idx_audit_created_at ON command_audit_log(created_at);
"""


def _apply_v1(conn: sqlite3.Connection) -> None:
    """Apply initial Denver Memory schema version 1."""
    conn.executescript(SCHEMA_V1_SQL)


def _apply_v2(conn: sqlite3.Connection) -> None:
    """Apply Phase 7 Advanced Intelligence & Semantic Memory schema upgrades."""
    # Check existing columns in memory_items to add missing columns idempotently
    cursor = conn.execute("PRAGMA table_info(memory_items);")
    existing_cols = {row[1] for row in cursor.fetchall()}

    columns_to_add = [
        ("importance", "REAL DEFAULT 0.5"),
        ("confidence", "REAL DEFAULT 1.0"),
        ("source", "TEXT DEFAULT 'explicit_user'"),
        ("expires_at", "TIMESTAMP DEFAULT NULL"),
        ("last_accessed_at", "TIMESTAMP DEFAULT NULL"),
        ("embedding_status", "TEXT DEFAULT 'pending'"),
        ("embedding_model", "TEXT DEFAULT NULL"),
        ("is_deleted", "BOOLEAN DEFAULT 0"),
    ]


    for col_name, col_def in columns_to_add:
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE memory_items ADD COLUMN {col_name} {col_def};")

    # Check existing columns in user_preferences
    pref_cursor = conn.execute("PRAGMA table_info(user_preferences);")
    pref_cols = {row[1] for row in pref_cursor.fetchall()}

    if "confidence" not in pref_cols:
        conn.execute("ALTER TABLE user_preferences ADD COLUMN confidence REAL DEFAULT 1.0;")
    if "source" not in pref_cols:
        conn.execute("ALTER TABLE user_preferences ADD COLUMN source TEXT DEFAULT 'explicit_user';")

    # Add Phase 7 indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_importance ON memory_items(importance);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_confidence ON memory_items(confidence);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_expires ON memory_items(expires_at);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_last_accessed ON memory_items(last_accessed_at);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_deleted ON memory_items(is_deleted);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_entity ON memory_embeddings(entity_type, entity_id);")

    # Setup FTS5 Full Text Search if available
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_items_fts USING fts5(
                content,
                key,
                category,
                content=memory_items,
                content_rowid=id
            );
            """
        )
        # Create triggers to sync FTS
        conn.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS memory_items_ai AFTER INSERT ON memory_items BEGIN
                INSERT INTO memory_items_fts(rowid, content, key, category) VALUES (new.id, new.content, new.key, new.category);
            END;

            CREATE TRIGGER IF NOT EXISTS memory_items_ad AFTER DELETE ON memory_items BEGIN
                INSERT INTO memory_items_fts(memory_items_fts, rowid, content, key, category) VALUES('delete', old.id, old.content, old.key, old.category);
            END;

            CREATE TRIGGER IF NOT EXISTS memory_items_au AFTER UPDATE ON memory_items BEGIN
                INSERT INTO memory_items_fts(memory_items_fts, rowid, content, key, category) VALUES('delete', old.id, old.content, old.key, old.category);
                INSERT INTO memory_items_fts(rowid, content, key, category) VALUES (new.id, new.content, new.key, new.category);
            END;
            """
        )
        # Populate FTS with existing data if empty
        conn.execute("INSERT OR IGNORE INTO memory_items_fts(rowid, content, key, category) SELECT id, content, key, category FROM memory_items;")
        logger.info("SQLite FTS5 full-text index successfully initialized.")
    except sqlite3.OperationalError as exc:
        logger.warning("FTS5 table initialization skipped (not compiled or supported in current SQLite): %s", exc)


def _apply_v3(conn: sqlite3.Connection) -> None:
    """Phase 8 Migration: Persistent scheduler, routines, executions, and routine audit trail."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS routines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            routine_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            status TEXT DEFAULT 'active',
            trigger_type TEXT NOT NULL,
            trigger_config TEXT NOT NULL,
            actions TEXT NOT NULL,
            timezone TEXT DEFAULT 'UTC',
            next_run_at TIMESTAMP NULL,
            last_run_at TIMESTAMP NULL,
            last_status TEXT DEFAULT 'PENDING',
            failure_count INTEGER DEFAULT 0,
            max_runtime_seconds REAL DEFAULT 60.0,
            notification_policy TEXT DEFAULT 'ON_FAILURE',
            requires_confirmation INTEGER DEFAULT 0,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_routines_enabled ON routines(enabled);
        CREATE INDEX IF NOT EXISTS idx_routines_next_run ON routines(next_run_at);
        CREATE INDEX IF NOT EXISTS idx_routines_lookup ON routines(routine_id);

        CREATE TABLE IF NOT EXISTS routine_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id TEXT UNIQUE NOT NULL,
            routine_id TEXT NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP NULL,
            status TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            confirmation_status TEXT DEFAULT 'NOT_REQUIRED',
            action_count INTEGER DEFAULT 0,
            successful_actions INTEGER DEFAULT 0,
            failed_actions INTEGER DEFAULT 0,
            error_summary TEXT DEFAULT '',
            duration_ms REAL DEFAULT 0.0,
            FOREIGN KEY(routine_id) REFERENCES routines(routine_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_executions_routine_id ON routine_executions(routine_id);
        CREATE INDEX IF NOT EXISTS idx_executions_started_at ON routine_executions(started_at);
        CREATE INDEX IF NOT EXISTS idx_executions_status ON routine_executions(status);

        CREATE TABLE IF NOT EXISTS routine_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_id TEXT UNIQUE NOT NULL,
            routine_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor TEXT DEFAULT 'system',
            details TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_routine_audit_routine_id ON routine_audit(routine_id);
        CREATE INDEX IF NOT EXISTS idx_routine_audit_created_at ON routine_audit(created_at);
        """
    )

    # Ensure status column exists if table was created in earlier schemas
    cursor = conn.execute("PRAGMA table_info(routines);")
    existing_cols = {row[1] for row in cursor.fetchall()}
    if "status" not in existing_cols:
        conn.execute("ALTER TABLE routines ADD COLUMN status TEXT DEFAULT 'active';")


def _apply_v4(conn: sqlite3.Connection) -> None:
    """Phase 9 Migration: Task and Workflow Orchestration schema."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS orchestrated_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            origin TEXT NOT NULL DEFAULT 'user_chat',
            priority TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'draft',
            current_plan_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_orchestrated_tasks_lookup ON orchestrated_tasks(task_id);
        CREATE INDEX IF NOT EXISTS idx_orchestrated_tasks_status ON orchestrated_tasks(status);

        CREATE TABLE IF NOT EXISTS task_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id TEXT UNIQUE NOT NULL,
            task_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'proposed',
            failure_policy TEXT NOT NULL DEFAULT 'stop_on_failure',
            max_retries INTEGER NOT NULL DEFAULT 1,
            timeout_seconds REAL NOT NULL DEFAULT 600.0,
            concurrency_limit INTEGER NOT NULL DEFAULT 2,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(task_id) REFERENCES orchestrated_tasks(task_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_task_plans_lookup ON task_plans(plan_id);
        CREATE INDEX IF NOT EXISTS idx_task_plans_task_id ON task_plans(task_id);

        CREATE TABLE IF NOT EXISTS task_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            step_id TEXT NOT NULL,
            plan_id TEXT NOT NULL,
            action_name TEXT NOT NULL,
            params TEXT NOT NULL DEFAULT '{}',
            depends_on TEXT NOT NULL DEFAULT '[]',
            timeout_seconds REAL NOT NULL DEFAULT 60.0,
            requires_approval INTEGER NOT NULL DEFAULT 0,
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(plan_id) REFERENCES task_plans(plan_id) ON DELETE CASCADE,
            UNIQUE(plan_id, step_id)
        );

        CREATE INDEX IF NOT EXISTS idx_task_steps_lookup ON task_steps(step_id);
        CREATE INDEX IF NOT EXISTS idx_task_steps_plan_id ON task_steps(plan_id);

        CREATE TABLE IF NOT EXISTS task_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id TEXT UNIQUE NOT NULL,
            task_id TEXT NOT NULL,
            plan_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP NULL,
            error_summary TEXT DEFAULT '',
            result_data TEXT DEFAULT '{}',
            FOREIGN KEY(task_id) REFERENCES orchestrated_tasks(task_id) ON DELETE CASCADE,
            FOREIGN KEY(plan_id) REFERENCES task_plans(plan_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_task_executions_lookup ON task_executions(execution_id);
        CREATE INDEX IF NOT EXISTS idx_task_executions_task_id ON task_executions(task_id);
        CREATE INDEX IF NOT EXISTS idx_task_executions_status ON task_executions(status);

        CREATE TABLE IF NOT EXISTS step_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            step_execution_id TEXT UNIQUE NOT NULL,
            execution_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            result_data TEXT DEFAULT '{}',
            error_message TEXT DEFAULT '',
            duration_ms REAL DEFAULT 0.0,
            FOREIGN KEY(execution_id) REFERENCES task_executions(execution_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_step_executions_execution ON step_executions(execution_id);
        CREATE INDEX IF NOT EXISTS idx_step_executions_step ON step_executions(step_id);

        CREATE TABLE IF NOT EXISTS task_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_id TEXT UNIQUE NOT NULL,
            task_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'system',
            details TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_task_audit_task_id ON task_audit(task_id);
        CREATE INDEX IF NOT EXISTS idx_task_audit_created_at ON task_audit(created_at);
        """
    )


def _apply_v5(conn: sqlite3.Connection) -> None:
    """Phase 10 Migration: Saved locations memory for Weather & Navigation."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS saved_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT UNIQUE NOT NULL,
            raw_address TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_saved_locations_label ON saved_locations(label);
        """
    )


def _apply_v6(conn: sqlite3.Connection) -> None:
    """Phase 11: Location Cache for Live Geolocation."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS location_cache (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            city TEXT,
            region TEXT,
            country TEXT,
            formatted_address TEXT,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


MIGRATIONS: list[tuple[int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, "Initial Denver schema: preferences, notes, tasks, habits, audit_log, memory_items, embeddings", _apply_v1),
    (2, "Phase 7 Advanced Intelligence: memory metadata, importance, confidence, TTL, FTS5 indexing", _apply_v2),
    (3, "Phase 8 Proactive Intelligence: persistent scheduler, routines, executions, audit trail", _apply_v3),
    (4, "Phase 9 Task and Workflow Orchestration: orchestrated_tasks, task_plans, task_steps, executions, audit", _apply_v4),
    (5, "Phase 10: Saved Locations for Weather & Navigation", _apply_v5),
    (6, "Phase 11: Location Cache for Live Geolocation", _apply_v6),
]



class MigrationManager:
    """Manages database schema initialization and idempotent version upgrades."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.conn = connection

    def init_migration_table(self) -> None:
        """Create schema_migrations tracking table if it doesn't exist."""
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def get_current_version(self) -> int:
        """Get highest applied schema version, or 0 if none applied."""
        self.init_migration_table()
        cursor = self.conn.execute("SELECT MAX(version) FROM schema_migrations;")
        row = cursor.fetchone()
        if row and row[0] is not None:
            return int(row[0])
        return 0

    def apply_pending_migrations(self) -> int:
        """Apply all unapplied migrations in ascending order inside a transaction."""
        self.init_migration_table()
        current_version = self.get_current_version()
        applied_count = 0

        for version, description, migration_func in sorted(MIGRATIONS, key=lambda m: m[0]):
            if version > current_version:
                logger.info("Applying migration v%d: %s", version, description)
                try:
                    migration_func(self.conn)
                    self.conn.execute(
                        "INSERT INTO schema_migrations (version, description) VALUES (?, ?);",
                        (version, description),
                    )
                    self.conn.commit()
                    applied_count += 1
                except Exception as exc:
                    self.conn.rollback()
                    logger.error("Migration v%d failed: %s", version, exc)
                    raise

        if applied_count > 0:
            logger.info("Successfully applied %d migration(s). Current schema version: %d", applied_count, self.get_current_version())
        return applied_count
