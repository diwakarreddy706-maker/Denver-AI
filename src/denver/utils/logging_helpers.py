"""Denver AI Assistant — Logging & PII Masking Utilities."""

from __future__ import annotations

import re


def mask_phone(phone: str) -> str:
    """Mask phone number to protect PII, preserving prefix and last 4 digits only.

    Examples:
        "+919876543210" -> "+91*******3210"
        "9876543210"    -> "******3210"
        "1234"          -> "****"
        ""              -> ""
    """
    if not phone:
        return ""
    clean = str(phone).strip()
    if len(clean) <= 4:
        return "****"

    if clean.startswith("+"):
        prefix = clean[:3]
        suffix = clean[-4:]
        middle_len = max(len(clean) - len(prefix) - len(suffix), 4)
        return f"{prefix}{'*' * middle_len}{suffix}"

    suffix = clean[-4:]
    middle_len = max(len(clean) - len(suffix), 4)
    return f"{'*' * middle_len}{suffix}"
