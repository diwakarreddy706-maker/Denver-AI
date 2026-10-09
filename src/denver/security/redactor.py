"""Production Secret & Sensitive Data Redaction Engine for Denver AI Assistant."""

from __future__ import annotations

import re
from typing import Any

# Comprehensive regex patterns matching credentials, tokens, secrets, and private keys
_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Private Key blocks
    ("PRIVATE_KEY", re.compile(r"-----BEGIN\s+[A-Z\s]+PRIVATE\s+KEY-----[\s\S]*?-----END\s+[A-Z\s]+PRIVATE\s+KEY-----", re.IGNORECASE)),
    # JWT tokens (Header.Payload.Signature)
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    # Bearer authorization headers
    ("BEARER", re.compile(r"\b(Bearer\s+)([A-Za-z0-9_\-\.]{8,})", re.IGNORECASE)),
    # Groq API keys
    ("GROQ_KEY", re.compile(r"\b(gsk_[A-Za-z0-9_]{16,})\b")),
    # Google API keys
    ("GOOGLE_KEY", re.compile(r"\b(AIza[0-9A-Za-z-_]{20,})\b")),
    # Anthropic API keys
    ("ANTHROPIC_KEY", re.compile(r"\b(sk-ant-[A-Za-z0-9_\-]{20,})\b")),
    # OpenAI and OpenAI-compatible API keys
    ("OPENAI_KEY", re.compile(r"\b(sk-[A-Za-z0-9_\-]{20,})\b")),
    # GitHub personal access / app tokens
    ("GITHUB_TOKEN", re.compile(r"\b((?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,})\b")),
    # AWS Access Key IDs
    ("AWS_KEY", re.compile(r"\b(AKIA[0-9A-Z]{16})\b")),
    # Hugging Face tokens
    ("HF_TOKEN", re.compile(r"\b(hf_[A-Za-z0-9]{20,})\b")),
    # Slack tokens
    ("SLACK_TOKEN", re.compile(r"\b(xox[baprs]-[0-9A-Za-z]{10,})\b")),
    # Database connection URIs with embedded passwords (e.g. postgres://user:pass@host)
    ("URI_CREDENTIAL", re.compile(r"((?:postgres|postgresql|mysql|mongodb|redis|amqp|smtp):\/\/[^\s:@]+:)([^\s@]+)(@[^\s]+)", re.IGNORECASE)),
    # Generic key-value assignment patterns: token=xyz, password=xyz, secret=xyz, api_key: xyz
    (
        "SENSITIVE_ASSIGNMENT",
        re.compile(
            r"\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|AUTH|CREDENTIAL)\w*\s*[:=]\s*)([\"']?)([^\s,;'\"]{3,})\2",
            re.IGNORECASE,
        ),
    ),
]


class SecretRedactor:
    """Detects and masks sensitive credentials across logs, voice TTS, UI, and external queries."""

    @staticmethod
    def contains_secrets(text: str) -> bool:
        """Check if string contains any recognized secret or credential pattern."""
        if not text or not isinstance(text, str):
            return False
        for _, pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                return True
        return False

    @staticmethod
    def mask_text(text: str, mask_replacement: str = "***") -> str:
        """Sanitize text by replacing all matched credential tokens with a secure mask."""
        if not text or not isinstance(text, str):
            return text

        result = text

        # 1. Mask Private Keys
        result = _SECRET_PATTERNS[0][1].sub(f"[REDACTED_PRIVATE_KEY_{mask_replacement}]", result)

        # 2. Mask Database URI Passwords
        result = _SECRET_PATTERNS[11][1].sub(rf"\g<1>{mask_replacement}\g<3>", result)

        # 3. Mask Bearer Tokens
        result = _SECRET_PATTERNS[2][1].sub(rf"\g<1>{mask_replacement}", result)

        # 4. Mask Explicit Key=Value Assignments
        result = _SECRET_PATTERNS[12][1].sub(rf"\g<1>\g<2>{mask_replacement}\g<2>", result)

        # 5. Mask Provider Specific Keys and JWTs
        for idx in [1, 3, 4, 5, 6, 7, 8, 9, 10]:
            pattern = _SECRET_PATTERNS[idx][1]
            result = pattern.sub(mask_replacement, result)

        return result

    @classmethod
    def mask_object(cls, obj: Any, mask_replacement: str = "***") -> Any:
        """Recursively traverse and redact sensitive data in dictionaries, lists, or strings."""
        if isinstance(obj, str):
            return cls.mask_text(obj, mask_replacement)
        if isinstance(obj, dict):
            masked_dict = {}
            for k, v in obj.items():
                k_str = str(k).lower()
                if any(sec in k_str for sec in ["key", "token", "secret", "password", "auth", "credential"]) and isinstance(v, str):
                    masked_dict[k] = mask_replacement if v else ""
                else:
                    masked_dict[k] = cls.mask_object(v, mask_replacement)
            return masked_dict
        if isinstance(obj, list):
            return [cls.mask_object(item, mask_replacement) for item in obj]
        if isinstance(obj, tuple):
            return tuple(cls.mask_object(item, mask_replacement) for item in obj)
        return obj


def redact_sensitive_text(text: str) -> str:
    """Convenience functional helper for masking sensitive data."""
    return SecretRedactor.mask_text(text)
