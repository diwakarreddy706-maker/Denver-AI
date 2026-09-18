"""Self-Healing System Diagnostics & Automated Safe Repair Engine for Denver AI."""

from __future__ import annotations

import os
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from denver.config.settings import DenverSettings, get_settings
from denver.logging.logger import get_logger

logger = get_logger("health.repair")


@dataclass
class RepairAction:
    """Represents a specific repair item to execute."""
    name: str
    description: str
    target: str
    severity: str  # "LOW", "MEDIUM", "HIGH"
    status: str = "PENDING"  # "PENDING", "FIXED", "SKIPPED", "FAILED"
    details: str = ""


@dataclass
class RepairReport:
    """Summary report of diagnostics and executed repair operations."""
    timestamp: float = field(default_factory=time.time)
    issues_detected: int = 0
    issues_fixed: int = 0
    actions: list[RepairAction] = field(default_factory=list)
    database_optimized: bool = False
    directories_created: list[str] = field(default_factory=list)
    logs_rotated: list[str] = field(default_factory=list)
    temp_files_cleared: int = 0
    bytes_freed: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "issues_detected": self.issues_detected,
            "issues_fixed": self.issues_fixed,
            "database_optimized": self.database_optimized,
            "directories_created": self.directories_created,
            "logs_rotated": self.logs_rotated,
            "temp_files_cleared": self.temp_files_cleared,
            "bytes_freed": self.bytes_freed,
            "actions": [
                {
                    "name": a.name,
                    "description": a.description,
                    "target": a.target,
                    "severity": a.severity,
                    "status": a.status,
                    "details": a.details,
                }
                for a in self.actions
            ],
            "error": self.error,
        }

    def format_spoken_summary(self) -> str:
        """Human-friendly summary for TTS voice output."""
        if self.issues_detected == 0:
            return "System diagnosis complete. All Denver subsystems, databases, and directories are in optimal health."

        fixed = self.issues_fixed
        parts = []
        if self.database_optimized:
            parts.append("database vacuumed and re-indexed")
        if self.directories_created:
            parts.append(f"{len(self.directories_created)} required directories created")
        if self.logs_rotated:
            parts.append("oversized logs rotated")
        if self.temp_files_cleared:
            parts.append(f"{self.temp_files_cleared} temporary files cleaned")

        details_str = ", ".join(parts) if parts else "all identified issues resolved"
        return f"System repair complete: {fixed} items repaired, including {details_str}."


class SystemRepairManager:
    """Diagnoses system health bottlenecks and applies safe, allowlisted automated repairs."""

    REQUIRED_DIRECTORIES = [
        Path("data"),
        Path("data/screenshots"),
        Path("data/screenshots/web"),
        Path("data/meetings"),
        Path("data/cache"),
        Path("logs"),
    ]

    def __init__(self, settings: DenverSettings | None = None) -> None:
        self.settings = settings or get_settings()

    def diagnose(self) -> list[RepairAction]:
        """Perform non-destructive inspection of system directories, DB, and logs."""
        actions: list[RepairAction] = []

        # 1. Check Missing Directories
        for directory in self.REQUIRED_DIRECTORIES:
            if not directory.exists():
                actions.append(
                    RepairAction(
                        name="create_directory",
                        description=f"Create missing workspace directory: {directory}",
                        target=str(directory),
                        severity="MEDIUM",
                    )
                )

        # 2. Check SQLite Database Integrity & Compaction
        db_path = Path(self.settings.database_path)
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                cursor.execute("PRAGMA integrity_check;")
                row = cursor.fetchone()
                if row and row[0] != "ok":
                    actions.append(
                        RepairAction(
                            name="repair_database_integrity",
                            description=f"Database integrity warning: {row[0]}",
                            target=str(db_path),
                            severity="HIGH",
                        )
                    )
                # Check DB size
                db_size = db_path.stat().st_size
                if db_size > 10 * 1024 * 1024:  # >10MB
                    actions.append(
                        RepairAction(
                            name="vacuum_database",
                            description=f"Optimize and defragment database ({round(db_size / (1024*1024), 2)} MB)",
                            target=str(db_path),
                            severity="LOW",
                        )
                    )
                conn.close()
            except Exception as exc:
                actions.append(
                    RepairAction(
                        name="check_database",
                        description=f"Could not inspect database: {exc}",
                        target=str(db_path),
                        severity="HIGH",
                    )
                )

        # 3. Check Oversized Logs
        log_file = Path(self.settings.log_file_path)
        if log_file.exists():
            log_size = log_file.stat().st_size
            if log_size > 5 * 1024 * 1024:  # >5MB
                actions.append(
                    RepairAction(
                        name="rotate_log",
                        description=f"Rotate oversized application log file ({round(log_size / (1024*1024), 2)} MB)",
                        target=str(log_file),
                        severity="MEDIUM",
                    )
                )

        # 4. Check Stale Cache / Temp Files
        cache_dir = Path("data/cache")
        if cache_dir.exists():
            stale_count = 0
            now = time.time()
            for file in cache_dir.glob("*"):
                if file.is_file() and (now - file.stat().st_mtime > 86400 * 2):  # >2 days
                    stale_count += 1
            if stale_count > 0:
                actions.append(
                    RepairAction(
                        name="clean_stale_cache",
                        description=f"Remove {stale_count} stale cached temporary files",
                        target=str(cache_dir),
                        severity="LOW",
                    )
                )

        return actions

    def run_repair(self, dry_run: bool = False) -> RepairReport:
        """Execute safe repair operations across all diagnosed areas."""
        report = RepairReport()
        actions = self.diagnose()
        report.issues_detected = len(actions)
        report.actions = actions

        if dry_run:
            logger.info("System repair running in DRY RUN mode (%d issues identified).", len(actions))
            return report

        # Apply allowlisted repairs
        for action in actions:
            try:
                if action.name == "create_directory":
                    dir_path = Path(action.target)
                    dir_path.mkdir(parents=True, exist_ok=True)
                    action.status = "FIXED"
                    action.details = "Directory created successfully."
                    report.directories_created.append(action.target)
                    report.issues_fixed += 1

                elif action.name in ("vacuum_database", "repair_database_integrity"):
                    db_path = Path(action.target)
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                    cursor.execute("VACUUM;")
                    cursor.execute("ANALYZE;")
                    conn.close()
                    action.status = "FIXED"
                    action.details = "VACUUM and ANALYZE completed successfully."
                    report.database_optimized = True
                    report.issues_fixed += 1

                elif action.name == "rotate_log":
                    log_path = Path(action.target)
                    rotated_path = log_path.with_suffix(f".log.{int(time.time())}")
                    shutil.move(str(log_path), str(rotated_path))
                    # Recreate empty log file
                    log_path.touch()
                    action.status = "FIXED"
                    action.details = f"Log rotated to {rotated_path.name}"
                    report.logs_rotated.append(str(rotated_path))
                    report.issues_fixed += 1

                elif action.name == "clean_stale_cache":
                    cache_dir = Path(action.target)
                    now = time.time()
                    freed = 0
                    cleared_count = 0
                    for file in cache_dir.glob("*"):
                        if file.is_file() and (now - file.stat().st_mtime > 86400 * 2):
                            size = file.stat().st_size
                            file.unlink(missing_ok=True)
                            freed += size
                            cleared_count += 1
                    action.status = "FIXED"
                    action.details = f"Deleted {cleared_count} files ({round(freed / 1024, 1)} KB freed)."
                    report.temp_files_cleared += cleared_count
                    report.bytes_freed += freed
                    report.issues_fixed += 1

            except Exception as exc:
                logger.error("Failed to execute repair action '%s': %s", action.name, exc)
                action.status = "FAILED"
                action.details = str(exc)

        # Always ensure base directories exist
        for d in self.REQUIRED_DIRECTORIES:
            d.mkdir(parents=True, exist_ok=True)

        logger.info(
            "System repair complete. Issues diagnosed: %d, Fixed: %d.",
            report.issues_detected,
            report.issues_fixed,
        )
        return report
