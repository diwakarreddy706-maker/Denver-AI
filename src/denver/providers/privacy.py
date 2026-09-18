"""Privacy and Cloud Sanitization Guard for Denver AI Providers."""

from __future__ import annotations

import re
from typing import Any

# Pattern targeting sensitive credentials and tokens
_CLOUD_MASK_PATTERN = re.compile(
    r"(?i)\b(api[-_]?key|auth[-_]?token|password|secret|bearer)\b\s*[:=]\s*([^\s,;'\"]+)",
    re.IGNORECASE,
)
_KEY_PREFIX_PATTERN = re.compile(
    r"\b(gsk_[A-Za-z0-9_]{10,}|AIza[0-9A-Za-z-_]{20,}|sk-[A-Za-z0-9_\-]{10,})\b"
)


def sanitize_text_for_cloud(text: str) -> str:
    """Mask credentials and sensitive key patterns from strings before sending to cloud providers."""
    if not text:
        return text
    sanitized = _CLOUD_MASK_PATTERN.sub(r"\1=***", text)
    sanitized = _KEY_PREFIX_PATTERN.sub("***", sanitized)
    return sanitized


def sanitize_messages_for_cloud(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Sanitize all message contents in a conversation history before cloud API dispatch."""
    cleaned = []
    for msg in messages:
        cleaned.append({
            "role": msg.get("role", "user"),
            "content": sanitize_text_for_cloud(msg.get("content", "")),
        })
    return cleaned
