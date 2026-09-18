"""Atomic File Writing Helper for Denver AI Assistant.

Prevents file corruption and partial writes on unexpected power outages, crashes,
or concurrent process terminations by writing to a temporary file in the target
directory and replacing the target atomically via os.replace().
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from denver.logging.logger import get_logger

logger = get_logger("utils.atomic_write")


def atomic_write_text(file_path: str | Path, content: str, encoding: str = "utf-8") -> Path:
    """Atomically write text content to file_path using tempfile + os.replace()."""
    target = Path(file_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    # Use target parent directory so os.replace() remains on the same filesystem/drive volume
    temp_handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding=encoding,
        dir=target.parent,
        delete=False,
        prefix=f"{target.stem}_",
        suffix=".tmp",
    )
    temp_path = Path(temp_handle.name)

    try:
        with temp_handle:
            temp_handle.write(content)
            temp_handle.flush()
            os.fsync(temp_handle.fileno())

        # Atomically replace target with temp file
        os.replace(temp_path, target)
        return target
    except Exception as exc:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        logger.error("Atomic write failed for '%s': %s", target, exc)
        raise


def atomic_write_json(
    file_path: str | Path,
    data: Any,
    indent: int = 2,
    ensure_ascii: bool = False,
    sort_keys: bool = False,
) -> Path:
    """Atomically serialize and write data as JSON to file_path."""
    serialized = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii, sort_keys=sort_keys)
    return atomic_write_text(file_path=file_path, content=serialized + "\n")
