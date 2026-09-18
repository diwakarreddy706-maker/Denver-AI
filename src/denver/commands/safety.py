"""Safety Layer and Action Security Guard for Denver AI Assistant."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from denver.commands.models import ActionRequest, CommandRiskLevel
from denver.logging.logger import get_logger

logger = get_logger("safety")

# Blacklisted binaries and dangerous shell commands
_BLOCKED_COMMAND_PATTERNS = [
    re.compile(r"\b(cmd(?:\.exe)?\s+/(?:c|k))\b", re.IGNORECASE),
    re.compile(r"\b(powershell(?:\.exe)?\b.*)", re.IGNORECASE),
    re.compile(r"\b(bash|sh|zsh)\s+-c\b", re.IGNORECASE),
    re.compile(r"\b(format(?:\s+[a-z]:|\s+[a-z]))\b", re.IGNORECASE),
    re.compile(r"\b(diskpart|vssadmin|bcdedit)\b", re.IGNORECASE),
    re.compile(r"\b(del\s+/[fqs]|rmdir\s+/[sq]|rm\s+-rf)\b", re.IGNORECASE),
    re.compile(r"\b(eval\(|exec\(|__import__|os\.system|subprocess\.)\b", re.IGNORECASE),
    re.compile(r"(?:^|\s|[=;\"\'])[a-zA-Z]:[\\/]", re.IGNORECASE),
    re.compile(r"^\\\\[^\\\s]+", re.IGNORECASE),
]

# Directory traversal pattern
_DIRECTORY_TRAVERSAL_PATTERN = re.compile(r"(?:\.\.[\\/]|[\\/]\.\.|\.\.)")

# Permitted URL schemes
_ALLOWED_URL_SCHEMES = {"http", "https"}


class SafetyValidator:
    """Validates action requests and arguments against the Denver Security Architecture."""

    def __init__(self, allow_destructive_actions: bool = False) -> None:
        self.allow_destructive_actions = allow_destructive_actions

    def check_for_dangerous_patterns(self, text: str, is_url: bool = False) -> str | None:
        """Scan string parameters for prohibited shell executions, code injections, or destructive operations."""
        if not text:
            return None

        for pattern in _BLOCKED_COMMAND_PATTERNS:
            if is_url and pattern.pattern == r"(?:^|\s|[=;\"\'])[a-zA-Z]:[\\/]":
                continue
            if pattern.search(text):
                return f"Prohibited dangerous command pattern detected: '{pattern.pattern}'"

        if _DIRECTORY_TRAVERSAL_PATTERN.search(text):
            return "Directory traversal sequence ('..') is prohibited in action parameters."

        return None

    def validate_url(self, url: str) -> tuple[bool, str | None]:
        """Verify URL uses safe http/https protocol schemes."""
        if not url:
            return False, "URL cannot be empty."

        for char in [";", "|", "&&", "`", "$("]:
            if char in url:
                return False, f"URL contains prohibited command chaining operator '{char}'."

        try:
            parsed = urlparse(url)
            scheme = parsed.scheme.lower()
            if scheme not in _ALLOWED_URL_SCHEMES:
                return False, f"URL scheme '{scheme}' is not permitted. Only HTTP/HTTPS protocols are allowed."
            if not parsed.netloc:
                return False, "Invalid URL structure: missing network location/domain."
            return True, None
        except Exception as exc:
            return False, f"Invalid URL format: {exc}"

    def validate(
        self,
        action: ActionRequest,
        allow_destructive: bool | None = None,
    ) -> tuple[bool, str | None]:
        """Validate an action request before execution."""
        if action.risk_level == CommandRiskLevel.BLOCKED:
            return False, "Action is classified as BLOCKED by Denver security policy."

        # Check all string parameters for dangerous patterns
        for param_key, param_value in action.params.items():
            if isinstance(param_value, str):
                is_url_param = param_key in {"url", "target"} and (param_value.startswith("http://") or param_value.startswith("https://") or action.action_name == "open_browser")
                violation = self.check_for_dangerous_patterns(param_value, is_url=is_url_param)
                if violation:
                    logger.warning("Safety violation in action '%s' param '%s': %s", action.action_name, param_key, violation)
                    return False, violation

                if param_key in {"url"}:
                    is_valid_url, url_err = self.validate_url(param_value)
                    if not is_valid_url:
                        logger.warning("Invalid URL in action '%s': %s", action.action_name, url_err)
                        return False, url_err

        # Check confirmation gates
        allow_dest = self.allow_destructive_actions if allow_destructive is None else allow_destructive
        if action.requires_confirmation and not allow_dest:
            return False, f"Action '{action.action_name}' requires explicit user confirmation and is blocked."

        return True, None
