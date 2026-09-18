"""Denver SQLite Database Connection & Async Execution Manager."""

from __future__ import annotations

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, TypeVar

from denver.logging.logger import get_logger
from denver.memory.migrations import MigrationManager

logger = get_logger("database")

T = TypeVar("T")


class DenverDatabase:
    """Manages SQLite connection lifecycle, pragmas, migrations, and async execution."""

    def __init__(self, db_path: Path | str = "denver_memory.sqlite3") -> None:
        self.db_path = Path(db_path)
        self._connection: sqlite3.Connection | None = None
        self._is_initialized = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="denver_db_worker")

    @property
    def is_connected(self) -> bool:
        return self._connection is not None

    def connect_sync(self) -> sqlite3.Connection:
        """Create and configure the synchronous SQLite connection with proper pragmas."""
        if self._connection is not None:
            return self._connection

        if self.db_path.parent != Path("."):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(
            str(self.db_path),
            timeout=10.0,
            check_same_thread=False,
            isolation_level=None,  # Autocommit mode; transactions managed explicitly
        )
        conn.row_factory = sqlite3.Row

        # Configure essential Pragmas
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")

        self._connection = conn
        return self._connection

    def initialize_sync(self) -> None:
        """Synchronously initialize connection and apply pending migrations."""
        conn = self.connect_sync()
        migrator = MigrationManager(conn)
        migrator.apply_pending_migrations()
        self._is_initialized = True
        logger.info("Denver database initialized at '%s'.", self.db_path)

    async def initialize(self) -> None:
        """Asynchronously initialize the database on a worker thread."""
        await asyncio.to_thread(self.initialize_sync)

    async def run_async(self, func: Callable[[sqlite3.Connection], T]) -> T:
        """Execute a database query/function safely on the background DB thread worker."""
        if not self._connection:
            await self.initialize()

        assert self._connection is not None

        def _runner() -> T:
            assert self._connection is not None
            result = func(self._connection)
            try:
                self._connection.commit()
            except Exception:
                pass
            return result

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, _runner)

    def close_sync(self) -> None:
        """Close database connection and shutdown thread executor."""
        if self._connection:
            try:
                self._connection.close()
            except Exception as exc:
                logger.warning("Error closing database connection: %s", exc)
            finally:
                self._connection = None
                self._is_initialized = False

        self._executor.shutdown(wait=False)
        logger.debug("Closed database connection for '%s'.", self.db_path)

    async def close(self) -> None:
        """Asynchronously close database connection."""
        await asyncio.to_thread(self.close_sync)

    def get_health_status(self) -> dict[str, Any]:
        """Inspect database health without exposing sensitive user data."""
        try:
            if not self.is_connected:
                if not self.db_path.exists():
                    # Attempt safe connection/migration probe
                    self.initialize_sync()
                else:
                    self.connect_sync()

            assert self._connection is not None
            # Probe WAL mode
            wal_cursor = self._connection.execute("PRAGMA journal_mode;")
            wal_mode = wal_cursor.fetchone()[0]

            # Probe schema version
            migrator = MigrationManager(self._connection)
            schema_version = migrator.get_current_version()

            # Integrity check
            check_cursor = self._connection.execute("PRAGMA quick_check;")
            integrity_result = check_cursor.fetchone()[0]
            is_healthy = (integrity_result == "ok")

            return {
                "status": "READY" if is_healthy else "DEGRADED",
                "database_path": str(self.db_path),
                "connected": True,
                "sqlite_version": sqlite3.sqlite_version,
                "journal_mode": wal_mode,
                "schema_version": schema_version,
                "integrity": integrity_result,
            }
        except Exception as exc:
            logger.error("Database health check failed: %s", exc)
            return {
                "status": "ERROR",
                "database_path": str(self.db_path),
                "connected": False,
                "error": str(exc),
                "sqlite_version": sqlite3.sqlite_version,
            }
