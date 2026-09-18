"""URL Safety Sanitization and Web Guardrails for Denver AI Assistant."""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

from denver.logging.logger import get_logger

logger = get_logger("automation.url_safety")

_ALLOWED_SCHEMES = {"http", "https"}
_DANGEROUS_SCHEMES = {"javascript:", "data:", "file:", "vbscript:", "about:", "blob:", "chrome:"}
_DANGEROUS_CHARACTERS = ["\n", "\r", "\x00", "`", "$(", ";", "|", "&&"]


def is_safe_url(raw_url: str) -> bool:
    """Return True if raw_url uses permitted schemes and contains no forbidden characters."""
    if not raw_url or not isinstance(raw_url, str):
        return False
    clean = raw_url.strip()
    lower = clean.lower()

    for pattern in _DANGEROUS_SCHEMES:
        if lower.startswith(pattern) or pattern in lower:
            return False

    for char in _DANGEROUS_CHARACTERS:
        if char in clean:
            return False

    if not (lower.startswith("http://") or lower.startswith("https://")):
        clean = f"https://{clean}"

    try:
        parsed = urllib.parse.urlparse(clean)
        return parsed.scheme.lower() in _ALLOWED_SCHEMES and bool(parsed.netloc)
    except Exception:
        return False


def normalize_web_url(raw_url: str) -> str | None:
    """Normalize and sanitize a web URL, returning a valid https/http URL or None if blocked."""
    if not is_safe_url(raw_url):
        logger.warning("Blocked unsafe URL: %s", raw_url)
        return None

    clean = raw_url.strip()
    lower = clean.lower()
    if not (lower.startswith("http://") or lower.startswith("https://")):
        clean = f"https://{clean}"

    try:
        parsed = urllib.parse.urlparse(clean)
        if parsed.scheme.lower() not in _ALLOWED_SCHEMES or not parsed.netloc:
            return None
        return urllib.parse.urlunparse(parsed)
    except Exception as exc:
        logger.warning("Failed to normalize URL '%s': %s", raw_url, exc)
        return None


def build_google_search_url(query: str) -> str:
    """Build a sanitized Google Search URL for the given query."""
    encoded_query = urllib.parse.quote_plus((query or "").strip())
    return f"https://www.google.com/search?q={encoded_query}"
