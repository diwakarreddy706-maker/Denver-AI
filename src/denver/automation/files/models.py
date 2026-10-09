"""Data models for Denver File System Assistant & Downloads Organizer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class FileInfo:
    """Metadata regarding a local file."""
    path: str
    name: str
    extension: str
    size_bytes: int
    category: str
    modified_at: str

    @property
    def size_mb(self) -> float:
        return round(self.size_bytes / (1024 * 1024), 2)

    def format_size(self) -> str:
        if self.size_bytes < 1024:
            return f"{self.size_bytes} B"
        elif self.size_bytes < 1024 * 1024:
            return f"{round(self.size_bytes / 1024, 1)} KB"
        elif self.size_bytes < 1024 * 1024 * 1024:
            return f"{round(self.size_bytes / (1024 * 1024), 1)} MB"
        else:
            return f"{round(self.size_bytes / (1024 * 1024 * 1024), 2)} GB"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "size_formatted": self.format_size(),
            "category": self.category,
            "modified_at": self.modified_at,
        }


@dataclass
class OrganizationAction:
    """Represents an atomic file move operation."""
    source_path: str
    destination_path: str
    category: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "destination_path": self.destination_path,
            "category": self.category,
            "timestamp": self.timestamp,
        }


@dataclass
class OrganizationSummary:
    """Summary result of a directory organization operation."""
    target_directory: str
    total_files_scanned: int
    files_moved: int
    bytes_moved: int
    by_category: dict[str, int] = field(default_factory=dict)
    actions: list[OrganizationAction] = field(default_factory=list)
    dry_run: bool = False

    @property
    def total_scanned(self) -> int:
        return self.total_files_scanned

    @property
    def total_moved(self) -> int:
        return self.files_moved

    def format_display(self) -> str:
        mode_str = " (PREVIEW - Dry Run)" if self.dry_run else ""
        if self.files_moved == 0:
            return f"Directory '{Path(self.target_directory).name}' is already clean and organized."

        lines = [
            f"📁 Downloads Organization Summary{mode_str}:",
            f"Target: {self.target_directory}",
            f"Files Organized: {self.files_moved} of {self.total_files_scanned}",
            "\nCategorized Into:",
        ]
        for cat, count in sorted(self.by_category.items()):
            lines.append(f"  • {cat}: {count} file(s)")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_directory": self.target_directory,
            "total_files_scanned": self.total_files_scanned,
            "files_moved": self.files_moved,
            "bytes_moved": self.bytes_moved,
            "by_category": self.by_category,
            "dry_run": self.dry_run,
            "actions": [a.to_dict() for a in self.actions],
        }


@dataclass
class DuplicateGroup:
    """Group of identical files by size and SHA-256 hash."""
    file_hash: str
    size_bytes: int
    files: list[str]

    @property
    def count(self) -> int:
        return len(self.files)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_hash": self.file_hash,
            "size_bytes": self.size_bytes,
            "files": self.files,
            "count": self.count,
        }
