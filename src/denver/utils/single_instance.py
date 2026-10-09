"""Single-instance guard for Denver AI Assistant using Windows Named Mutex."""

from __future__ import annotations

import atexit
import ctypes
import os
import sys
from pathlib import Path
from typing import Any

from denver.logging.logger import get_logger

logger = get_logger("single_instance")

_MUTEX_NAME = "Local\\DenverAIAssistant_SingleInstance_Mutex"
_ERROR_ALREADY_EXISTS = 183


class SingleInstanceGuard:
    """Ensures only one instance of Denver runs simultaneously per Windows user session."""

    def __init__(self, mutex_name: str = _MUTEX_NAME) -> None:
        self.mutex_name = mutex_name
        self._mutex_handle: int | None = None
        self._lock_file: Path | None = None
        self._lock_fd: int | None = None
        self._is_owner: bool = False

    def acquire(self) -> bool:
        """Acquire the single-instance mutex. Returns True if successfully acquired, False if already running."""
        if sys.platform == "win32":
            try:
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.CreateMutexW(None, False, self.mutex_name)
                last_error = kernel32.GetLastError()
                if last_error == _ERROR_ALREADY_EXISTS:
                    logger.warning("Another instance of Denver is already active (mutex '%s' held).", self.mutex_name)
                    if handle:
                        kernel32.CloseHandle(handle)
                    return False
                self._mutex_handle = handle
                self._is_owner = True
                atexit.register(self.release)
                return True
            except Exception as exc:
                logger.warning("Failed to create Windows named mutex (%s); using lockfile fallback.", exc)

        # Cross-platform / fallback file lock
        try:
            lock_dir = Path.home() / ".denver"
            lock_dir.mkdir(parents=True, exist_ok=True)
            self._lock_file = lock_dir / "denver.lock"
            
            # On Windows without mutex or on POSIX
            if self._lock_file.exists():
                try:
                    # Check if process is still alive
                    pid = int(self._lock_file.read_text(encoding="utf-8").strip())
                    import psutil
                    if psutil.pid_exists(pid):
                        logger.warning("Another Denver process is running with PID %d.", pid)
                        return False
                except Exception:
                    pass

            self._lock_file.write_text(str(os.getpid()), encoding="utf-8")
            self._is_owner = True
            atexit.register(self.release)
            return True
        except Exception as exc:
            logger.error("Failed to acquire single-instance lockfile: %s", exc)
            return True  # Avoid blocking launch on non-critical lock error

    def release(self) -> None:
        """Release the mutex and clean up locks."""
        if not self._is_owner:
            return
        self._is_owner = False

        if sys.platform == "win32" and self._mutex_handle:
            try:
                ctypes.windll.kernel32.CloseHandle(self._mutex_handle)
            except Exception:
                pass
            self._mutex_handle = None

        if self._lock_file and self._lock_file.exists():
            try:
                self._lock_file.unlink()
            except Exception:
                pass
            self._lock_file = None

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()
