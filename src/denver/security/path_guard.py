"""Path Confinement, Directory Traversal, and ADS Protection for Denver AI Assistant."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Sequence

from denver.logging.logger import get_logger

logger = get_logger("security.path_guard")

# Prohibited directory traversal sequences
_TRAVERSAL_REGEX = re.compile(r"(?:\.\.[\\/]|[\\/]\.\.|\.\.)")

# Windows Alternate Data Stream (ADS) regex e.g. "secret.txt:hidden_stream"
_ADS_REGEX = re.compile(r"[a-zA-Z0-9_\-\.]+:[a-zA-Z0-9_\-\.]+")

# Prohibited dangerous system directories on Windows
_PROTECTED_WINDOWS_DIRS = [
    Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve(),
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")).resolve(),
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")).resolve(),
    Path(os.environ.get("ProgramData", r"C:\ProgramData")).resolve(),
]


class PathGuard:
    """Enforces strict file boundary validation, symlink traversal prevention, and ADS protection."""

    @staticmethod
    def is_traversal_attempt(path_str: str) -> bool:
        """Check if path string contains explicit directory traversal patterns."""
        if not path_str or not isinstance(path_str, str):
            return False
        return bool(_TRAVERSAL_REGEX.search(path_str))

    @staticmethod
    def is_alternate_data_stream(path_str: str) -> bool:
        """Check if target attempts to access a Windows Alternate Data Stream."""
        if not path_str or not isinstance(path_str, str):
            return False
        # Strip drive letter prefix like 'C:'
        norm = path_str
        if len(norm) >= 2 and norm[1] == ":" and norm[0].isalpha():
            norm = norm[2:]
        return bool(_ADS_REGEX.search(norm))

    @staticmethod
    def is_unc_network_path(path_str: str) -> bool:
        r"""Check if target attempts to access a remote UNC network share (e.g. \\evil.com\share)."""
        if not path_str or not isinstance(path_str, str):
            return False
        clean = path_str.strip()
        return clean.startswith(r"\\") or clean.startswith("//")

    @classmethod
    def validate_path(
        cls,
        target_path: str | Path,
        allowed_roots: Sequence[str | Path] | None = None,
        allow_write_system_dirs: bool = False,
    ) -> tuple[bool, Path | None, str | None]:
        """Verify that a path is safe, canonicalized, and strictly confined within allowed boundaries.

        Returns:
            (is_valid, resolved_path, error_reason)
        """
        raw_str = str(target_path).strip()
        if not raw_str:
            return False, None, "Path cannot be empty."

        # Check for UNC network share injection
        if cls.is_unc_network_path(raw_str):
            return False, None, f"Remote UNC network path is prohibited: '{raw_str}'"

        # Check for Alternate Data Streams
        if cls.is_alternate_data_stream(raw_str):
            return False, None, f"Windows Alternate Data Stream access is prohibited: '{raw_str}'"

        # Check raw traversal tokens
        if cls.is_traversal_attempt(raw_str):
            return False, None, f"Directory traversal sequence detected in: '{raw_str}'"

        try:
            resolved = Path(raw_str).resolve()
        except Exception as exc:
            return False, None, f"Failed to resolve path: {exc}"

        # Ensure write is not directed to protected Windows operating system paths
        if not allow_write_system_dirs:
            for sys_dir in _PROTECTED_WINDOWS_DIRS:
                if str(sys_dir) and resolved == sys_dir or sys_dir in resolved.parents:
                    return False, resolved, f"Access to protected operating system directory '{sys_dir}' is blocked."

        # Check confinement within allowed roots if provided
        if allowed_roots:
            is_confined = False
            for root in allowed_roots:
                root_path = Path(root).resolve()
                if resolved == root_path or root_path in resolved.parents:
                    is_confined = True
                    break
            if not is_confined:
                roots_str = ", ".join(str(Path(r).resolve()) for r in allowed_roots)
                return False, resolved, f"Path '{resolved}' escapes allowed directories: [{roots_str}]."

        return True, resolved, None
