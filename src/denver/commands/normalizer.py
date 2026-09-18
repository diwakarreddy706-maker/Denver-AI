"""Deterministic Command Normalization for Denver AI Assistant."""

from __future__ import annotations

import re
import unicodedata

# Matches assistant prefix variations at the beginning of the utterance
_ASSISTANT_PREFIX_PATTERN = re.compile(
    r"^(?:(?:hey|hi|hello|ok|okay|please)\s+)?denver(?:[\s,:\-]+please|\s*,\s*|\s*:\s*|\s+please|\s+)?",
    re.IGNORECASE,
)

# Matches polite leading/trailing words
_POLITE_PREFIX_PATTERN = re.compile(r"^(?:please|could you|would you|can you|kindly)\s+", re.IGNORECASE)
_POLITE_SUFFIX_PATTERN = re.compile(r"\s+(?:please|thank you|thanks)$", re.IGNORECASE)

# Strips surrounding punctuation while preserving meaningful separators (., :, /, \, +, -, _)
_SURROUNDING_PUNCT_PATTERN = re.compile(r"^[^\w/\\:\.\+\-]+|[^\w/\\:\.\+\-]+$")
_WHITESPACE_COLLAPSE_PATTERN = re.compile(r"\s+")


class CommandNormalizer:
    """Normalizes raw user utterances into clean deterministic canonical text."""

    def __init__(self, assistant_name: str = "Denver") -> None:
        self.assistant_name = assistant_name.lower()

    def normalize(self, raw_text: str | None) -> str:
        """Transform raw user command string into normalized canonical form."""
        if not raw_text:
            return ""

        # 1. Unicode normalization (NFKD) and ASCII conversion
        normalized = unicodedata.normalize("NFKD", str(raw_text))

        # 2. Collapse internal whitespace and strip outer whitespace
        normalized = _WHITESPACE_COLLAPSE_PATTERN.sub(" ", normalized).strip()

        # 3. Strip surrounding quotation marks or brackets
        normalized = normalized.strip("\"'()[]{}")

        # 4. Remove assistant name invocation at the start ("Denver, open chrome" -> "open chrome")
        normalized = _ASSISTANT_PREFIX_PATTERN.sub("", normalized).strip()

        # 5. Remove polite conversational filler ("please open chrome" -> "open chrome")
        normalized = _POLITE_PREFIX_PATTERN.sub("", normalized).strip()
        normalized = _POLITE_SUFFIX_PATTERN.sub("", normalized).strip()

        # 6. Final surrounding punctuation strip
        normalized = _SURROUNDING_PUNCT_PATTERN.sub("", normalized).strip()

        # 7. Lowercase representation
        return normalized.lower()
