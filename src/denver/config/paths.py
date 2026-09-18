"""Denver Runtime Path Resolution & Directory Management."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """Return True if running inside a PyInstaller frozen bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def get_app_root() -> Path:
    """Get the root application directory (bundle dir if frozen, or src root in dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # src/denver/config/paths.py -> parents[2] is src/, parents[3] is project root
    return Path(__file__).resolve().parents[3]


def get_user_data_dir() -> Path:
    """Get the standard writable user data directory for Denver.

    On Windows: %LOCALAPPDATA%/Denver (fallback ~/.denver)
    On Linux/Mac: ~/.denver
    """
    if "DENVER_USER_DATA_DIR" in os.environ:
        p = Path(os.environ["DENVER_USER_DATA_DIR"]).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data and os.name == "nt":
        base_dir = Path(local_app_data) / "Denver"
    else:
        base_dir = Path.home() / ".denver"

    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def resolve_runtime_path(path: Path | str, default_relative_to_user_dir: bool = False) -> Path:
    """Resolve a path safely. If relative, leaves as is or anchors appropriately."""
    p = Path(path)
    if p.is_absolute():
        return p
    if default_relative_to_user_dir and is_frozen():
        return get_user_data_dir() / p
    return p
