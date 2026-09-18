"""Safe Web Browser Launcher and URL Validator for Denver."""

from __future__ import annotations

import urllib.parse
import webbrowser
from typing import Any

from denver.automation.errors import URLSecurityError
from denver.automation.models import AutomationResult, AutomationRisk
from denver.automation.registry import AutomationRegistry
from denver.logging.logger import get_logger

logger = get_logger("automation.browser")

_ALLOWED_SCHEMES = {"http", "https"}
_DISALLOWED_PATTERNS = ["javascript:", "data:", "file:", "vbscript:", "about:", "\n", "\r", "\x00", "`", "$(", ";", "|", "&&"]


def validate_and_normalize_url(raw_url: str) -> str:
    """Validate that a URL strictly obeys safety policies and return its canonical form."""
    raw = raw_url.strip()
    if not raw:
        raise URLSecurityError("URL cannot be empty.")

    # Check for forbidden injection substrings
    lower = raw.lower()
    for pattern in _DISALLOWED_PATTERNS:
        if pattern in lower:
            raise URLSecurityError(f"URL contains forbidden security pattern: '{pattern}'")

    # If scheme omitted and looks like a domain, prepend https://
    if not (lower.startswith("http://") or lower.startswith("https://")):
        raw = f"https://{raw}"

    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise URLSecurityError(f"URL scheme '{parsed.scheme}' is not allowed. Only HTTPS and HTTP are permitted.")

    if not parsed.netloc:
        raise URLSecurityError(f"URL '{raw}' lacks a valid domain host.")

    # Normalize
    return urllib.parse.urlunparse(parsed)


class BrowserController:
    """Controls browser navigation with strict URL validation."""

    def __init__(self, registry: AutomationRegistry | None = None) -> None:
        self.registry = registry or AutomationRegistry()

    def validate_url(self, raw_url: str) -> tuple[bool, str | None]:
        """Verify URL obeys safety policies."""
        try:
            validate_and_normalize_url(raw_url)
            return True, None
        except URLSecurityError as exc:
            return False, str(exc)

    def open_url(self, target: str) -> AutomationResult:
        """Open a web destination, resolving known sites or validating raw URLs."""
        # 1. Check known site registry first (e.g. "youtube", "github")
        known = self.registry.resolve_known_site(target)
        destination = known if known else target

        # 2. Safety validation
        try:
            valid_url = validate_and_normalize_url(destination)
        except URLSecurityError as exc:
            logger.warning("Blocked unsafe URL request '%s': %s", target, exc)
            return AutomationResult(
                success=False,
                action="open_browser",
                target=target,
                message=f"URL security violation: {exc}",
                risk_level=AutomationRisk.LOW,
                error=str(exc),
            )

        # 3. Safe open
        try:
            webbrowser.open(valid_url)
            logger.info("Opened validated browser URL: %s", valid_url)
            return AutomationResult(
                success=True,
                action="open_browser",
                target=valid_url,
                message=f"Opened {target if known else valid_url}.",
                data={"url": valid_url, "resolved_from_alias": bool(known)},
                risk_level=AutomationRisk.LOW,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to open browser URL '%s': %s", valid_url, exc)
            return AutomationResult(
                success=False,
                action="open_browser",
                target=valid_url,
                message=f"Failed to open browser: {exc}",
                risk_level=AutomationRisk.LOW,
                error=str(exc),
            )
