"""Production-grade secure logging for Denver AI Assistant."""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# Patterns that match secrets, API keys, tokens, and passwords
_BEARER_TOKEN_PATTERN = re.compile(r"\b(Bearer\s+)([A-Za-z0-9_\-\.]{8,})", re.IGNORECASE)
_GENERIC_KEY_PATTERN = re.compile(r"\b(gsk_[A-Za-z0-9_]{8,}|AIza[0-9A-Za-z-_]{20,}|sk-[A-Za-z0-9_]{8,})\b")
_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)\w*\s*[:=]\s*)([^\s,;'\"]+)",
    re.IGNORECASE,
)


def mask_sensitive_data(text: str) -> str:
    """Mask credentials, tokens, and secrets from string before output."""
    if not isinstance(text, str):
        return text
    masked = _BEARER_TOKEN_PATTERN.sub(r"\1***", text)
    masked = _GENERIC_KEY_PATTERN.sub("***", masked)
    masked = _SENSITIVE_ASSIGNMENT_PATTERN.sub(r"\1***", masked)
    return masked


class DenverMaskingFilter(logging.Filter):
    """Logging filter that redacts sensitive information from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_sensitive_data(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: mask_sensitive_data(str(v)) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(mask_sensitive_data(str(arg)) if isinstance(arg, str) else arg for arg in record.args)
        return True


_logging_configured = False


def setup_logging(
    level: str = "INFO",
    log_file: Path | str | None = Path("logs/denver.log"),
    max_bytes: int = 5 * 1024 * 1024,  # 5 MB
    backup_count: int = 5,
) -> None:
    """Initialize root and Denver loggers with console and rotating file handlers."""
    global _logging_configured
    if _logging_configured:
        return

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger("denver")
    root_logger.setLevel(numeric_level)
    root_logger.propagate = False

    # Clear existing handlers
    root_logger.handlers.clear()

    # Masking filter
    masking_filter = DenverMaskingFilter()
    root_logger.addFilter(masking_filter)

    # Formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console Handler (Streaming to stderr to keep stdout clean for structured JSON/CLI outputs)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(masking_filter)
    root_logger.addHandler(console_handler)

    # Rotating File Handler
    if log_file:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            file_handler = RotatingFileHandler(
                file_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(numeric_level)
            file_handler.setFormatter(formatter)
            file_handler.addFilter(masking_filter)
            root_logger.addHandler(file_handler)
        except OSError as exc:
            # Fallback if file logging cannot be opened
            root_logger.warning("Failed to open rotating log file '%s': %s", file_path, exc)

    _logging_configured = True


def get_logger(name: str = "denver") -> logging.Logger:
    """Get a named logger within the Denver namespace."""
    if not name.startswith("denver"):
        name = f"denver.{name}"
    return logging.getLogger(name)
