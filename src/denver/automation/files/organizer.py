"""Downloads & Directory Organizer Engine for Denver Desktop Automation."""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from denver.automation.files.models import (
    DuplicateGroup,
    FileInfo,
    OrganizationAction,
    OrganizationSummary,
)
from denver.logging.logger import get_logger

logger = get_logger("automation.files")

# Extension classification taxonomy
EXTENSION_MAP: dict[str, str] = {
    # Documents
    ".pdf": "Documents",
    ".docx": "Documents",
    ".doc": "Documents",
    ".xlsx": "Documents",
    ".xls": "Documents",
    ".pptx": "Documents",
    ".ppt": "Documents",
    ".txt": "Documents",
    ".csv": "Documents",
    ".rtf": "Documents",
    ".epub": "Documents",
    ".odt": "Documents",
    # Images
    ".png": "Images",
    ".jpg": "Images",
    ".jpeg": "Images",
    ".gif": "Images",
    ".webp": "Images",
    ".bmp": "Images",
    ".svg": "Images",
    ".ico": "Images",
    ".tiff": "Images",
    # Videos
    ".mp4": "Videos",
    ".mkv": "Videos",
    ".avi": "Videos",
    ".mov": "Videos",
    ".wmv": "Videos",
    ".flv": "Videos",
    ".webm": "Videos",
    # Audio
    ".mp3": "Audio",
    ".wav": "Audio",
    ".m4a": "Audio",
    ".flac": "Audio",
    ".aac": "Audio",
    ".ogg": "Audio",
    ".wma": "Audio",
    # Archives
    ".zip": "Archives",
    ".rar": "Archives",
    ".7z": "Archives",
    ".tar": "Archives",
    ".gz": "Archives",
    ".bz2": "Archives",
    ".xz": "Archives",
    # Installers
    ".exe": "Installers",
    ".msi": "Installers",
    ".dmg": "Installers",
    ".pkg": "Installers",
    ".iso": "Installers",
    ".deb": "Installers",
    ".rpm": "Installers",
    # Code
    ".py": "Code",
    ".js": "Code",
    ".ts": "Code",
    ".html": "Code",
    ".css": "Code",
    ".json": "Code",
    ".xml": "Code",
    ".java": "Code",
    ".cpp": "Code",
    ".c": "Code",
    ".rs": "Code",
    ".go": "Code",
    ".sh": "Code",
    ".ps1": "Code",
}

# Standard category directories to protect from recursive reorganization
STANDARD_CATEGORIES = set(EXTENSION_MAP.values()).union({"Others"})


class FileOrganizerService:
    """Manages directory scanning, categorization, file organization, duplicate detection, and undo."""

    def __init__(self, default_downloads_path: str | Path | None = None) -> None:
        self._default_path = (
            Path(default_downloads_path).resolve()
            if default_downloads_path
            else Path.home() / "Downloads"
        )
        self._undo_history: list[list[OrganizationAction]] = []

    def get_target_directory(self, path_arg: str | Path | None = None) -> Path:
        """Resolve target directory or fallback to Downloads folder."""
        if path_arg:
            p = Path(path_arg).resolve()
            if p.exists() and p.is_dir():
                return p
        return self._default_path

    @staticmethod
    def classify_file(file_path: Path) -> str:
        """Determine category name based on file extension."""
        ext = file_path.suffix.lower()
        return EXTENSION_MAP.get(ext, "Others")

    @classmethod
    def get_category(cls, file_path: Path | str) -> str:
        """Convenience helper to get category name from file path or filename."""
        return cls.classify_file(Path(file_path))

    def scan_directory(self, target_dir: str | Path | None = None) -> list[FileInfo]:
        """Scan top-level files in directory, ignoring system files and category subdirectories."""
        dir_path = self.get_target_directory(target_dir)
        if not dir_path.exists():
            return []

        files: list[FileInfo] = []
        for item in dir_path.iterdir():
            # Skip subdirectories, hidden files, and active temporary downloads
            if item.is_dir() or item.name.startswith(".") or item.suffix.lower() in {".tmp", ".crdownload"}:
                continue

            try:
                stat = item.stat()
                mtime_str = datetime.fromtimestamp(stat.st_mtime).isoformat()
                category = self.classify_file(item)
                files.append(
                    FileInfo(
                        path=str(item),
                        name=item.name,
                        extension=item.suffix.lower(),
                        size_bytes=stat.st_size,
                        category=category,
                        modified_at=mtime_str,
                    )
                )
            except (OSError, PermissionError) as exc:
                logger.warning("Could not stat file %s: %s", item, exc)

        return files

    def organize_directory(
        self,
        target_dir: str | Path | None = None,
        dry_run: bool = False,
    ) -> OrganizationSummary:
        """Categorize and move files into subfolders with collision avoidance and undo logging."""
        dir_path = self.get_target_directory(target_dir)
        dir_path.mkdir(parents=True, exist_ok=True)

        scanned = self.scan_directory(dir_path)
        actions: list[OrganizationAction] = []
        by_category: dict[str, int] = {}
        bytes_moved = 0

        for file_info in scanned:
            cat = file_info.category
            cat_dir = dir_path / cat
            dest_path = cat_dir / file_info.name

            # Collision avoidance: append counter if target file already exists
            src = Path(file_info.path)
            if not dry_run:
                cat_dir.mkdir(parents=True, exist_ok=True)
                counter = 1
                stem = src.stem
                suffix = src.suffix
                while dest_path.exists() and dest_path != src:
                    dest_path = cat_dir / f"{stem} ({counter}){suffix}"
                    counter += 1

                try:
                    shutil.move(str(src), str(dest_path))
                except Exception as exc:
                    logger.error("Failed moving %s to %s: %s", src, dest_path, exc)
                    continue

            action = OrganizationAction(
                source_path=str(src),
                destination_path=str(dest_path),
                category=cat,
            )
            actions.append(action)
            by_category[cat] = by_category.get(cat, 0) + 1
            bytes_moved += file_info.size_bytes

        if not dry_run and actions:
            self._undo_history.append(actions)
            logger.info("Organized %d file(s) in %s.", len(actions), dir_path)

        return OrganizationSummary(
            target_directory=str(dir_path),
            total_files_scanned=len(scanned),
            files_moved=len(actions),
            bytes_moved=bytes_moved,
            by_category=by_category,
            actions=actions,
            dry_run=dry_run,
        )

    def undo_last_organization(self) -> tuple[bool, int, str]:
        """Revert the most recent file organization run, moving files back to source paths."""
        if not self._undo_history:
            return False, 0, "No file organization operations available to undo."

        last_actions = self._undo_history.pop()
        reverted_count = 0

        for act in reversed(last_actions):
            dest = Path(act.destination_path)
            orig = Path(act.source_path)
            if dest.exists():
                try:
                    orig.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dest), str(orig))
                    reverted_count += 1
                except Exception as exc:
                    logger.warning("Could not revert move from %s to %s: %s", dest, orig, exc)

        # Cleanup empty category folders
        for act in last_actions:
            cat_folder = Path(act.destination_path).parent
            if cat_folder.exists() and cat_folder.is_dir():
                try:
                    if not any(cat_folder.iterdir()):
                        cat_folder.rmdir()
                except Exception:
                    pass

        return True, reverted_count, f"Successfully undone file organization: restored {reverted_count} file(s) to original locations."

    def find_large_files(
        self,
        target_dir: str | Path | None = None,
        min_size_mb: float = 50.0,
        limit: int = 10,
    ) -> list[FileInfo]:
        """Find the largest files within the target directory."""
        dir_path = self.get_target_directory(target_dir)
        if not dir_path.exists():
            return []

        min_bytes = int(min_size_mb * 1024 * 1024)
        large_files: list[FileInfo] = []

        try:
            for root, _, files in os.walk(dir_path):
                for f in files:
                    full_p = Path(root) / f
                    try:
                        sz = full_p.stat().st_size
                        if sz >= min_bytes:
                            mtime = datetime.fromtimestamp(full_p.stat().st_mtime).isoformat()
                            large_files.append(
                                FileInfo(
                                    path=str(full_p),
                                    name=f,
                                    extension=full_p.suffix.lower(),
                                    size_bytes=sz,
                                    category=self.classify_file(full_p),
                                    modified_at=mtime,
                                )
                            )
                    except (OSError, PermissionError):
                        continue
        except Exception as exc:
            logger.warning("Error walking directory for large files: %s", exc)

        large_files.sort(key=lambda x: x.size_bytes, reverse=True)
        return large_files[:limit]

    def find_duplicates(self, target_dir: str | Path | None = None) -> list[DuplicateGroup]:
        """Scan directory for duplicate files matching both size and SHA-256 content hashes."""
        dir_path = self.get_target_directory(target_dir)
        if not dir_path.exists():
            return []

        # 1. Bucket by size
        by_size: dict[int, list[Path]] = {}
        for root, _, files in os.walk(dir_path):
            for f in files:
                p = Path(root) / f
                try:
                    sz = p.stat().st_size
                    if sz > 0:
                        by_size.setdefault(sz, []).append(p)
                except (OSError, PermissionError):
                    continue

        # 2. Compute SHA-256 for buckets with >= 2 files
        duplicate_groups: list[DuplicateGroup] = []
        for sz, paths in by_size.items():
            if len(paths) < 2:
                continue

            by_hash: dict[str, list[str]] = {}
            for p in paths:
                try:
                    h = hashlib.sha256()
                    with p.open("rb") as fp:
                        for chunk in iter(lambda: fp.read(65536), b""):
                            h.update(chunk)
                    digest = h.hexdigest()
                    by_hash.setdefault(digest, []).append(str(p))
                except Exception:
                    continue

            for digest, dup_paths in by_hash.items():
                if len(dup_paths) >= 2:
                    duplicate_groups.append(
                        DuplicateGroup(
                            file_hash=digest,
                            size_bytes=sz,
                            files=dup_paths,
                        )
                    )

        return duplicate_groups

    def clean_temp_files(self, target_dir: str | Path | None = None) -> tuple[int, int, str]:
        """Remove leftover partial browser downloads (.crdownload, .tmp) and zero-byte files."""
        dir_path = self.get_target_directory(target_dir)
        if not dir_path.exists():
            return 0, 0, f"Directory does not exist: {dir_path}"

        cleaned_count = 0
        bytes_freed = 0

        temp_exts = {".tmp", ".temp", ".crdownload", ".bak", ".part", ".dmp"}
        for item in dir_path.iterdir():
            if item.is_file() and (item.suffix.lower() in temp_exts or item.name.startswith("~$") or item.name.startswith(".~")):
                try:
                    sz = item.stat().st_size
                    item.unlink()
                    cleaned_count += 1
                    bytes_freed += sz
                except Exception as exc:
                    logger.warning("Could not delete temp file %s: %s", item, exc)

        freed_mb = round(bytes_freed / (1024 * 1024), 2)
        return (
            cleaned_count,
            bytes_freed,
            f"Cleaned {cleaned_count} temporary download file(s), freeing {freed_mb} MB.",
        )


# Singleton instance helper
_FILE_ORGANIZER: FileOrganizerService | None = None


def get_file_organizer(default_downloads_path: str | Path | None = None) -> FileOrganizerService:
    """Retrieve or initialize shared FileOrganizerService."""
    global _FILE_ORGANIZER
    if _FILE_ORGANIZER is None or default_downloads_path is not None:
        _FILE_ORGANIZER = FileOrganizerService(default_downloads_path)
    return _FILE_ORGANIZER
