"""Clipboard Intelligence Subsystem for Denver AI Assistant."""

from __future__ import annotations

import datetime
from typing import Any

from denver.automation.models import AutomationResult, AutomationRisk
from denver.logging.logger import get_logger

logger = get_logger("automation.clipboard")


def summarize_text_locally(text: str, sentence_limit: int = 2) -> str:
    """Return a concise extractive summary without cloud provider overhead."""
    clean_text = " ".join((text or "").split())
    if not clean_text:
        return "Clipboard is empty."
    sentences = [part.strip() for part in clean_text.replace("?", ".").replace("!", ".").split(".") if part.strip()]
    if not sentences:
        return clean_text[:300]
    summary = ". ".join(sentences[: max(1, sentence_limit)])
    return summary + ("." if not summary.endswith(".") else "")


class ClipboardController:
    """Provides safe reading, writing, and summarization of Windows clipboard text."""

    def __init__(self) -> None:
        self._last_copied_text: str = ""

    def read_clipboard(self, max_speech_chars: int = 500) -> AutomationResult:
        """Read and return current text content from the Windows clipboard."""
        try:
            import pyperclip
            text = pyperclip.paste()
            if not text or not text.strip():
                return AutomationResult(
                    success=True,
                    action="read_clipboard",
                    message="The clipboard is currently empty.",
                    data={"text": "", "length": 0},
                    risk_level=AutomationRisk.LOW,
                )

            clean = text.strip()
            self._last_copied_text = clean
            length = len(clean)

            if length > max_speech_chars:
                spoken = f"Your clipboard has {length} characters. Here is the first part: {clean[:max_speech_chars]}..."
            else:
                spoken = clean

            return AutomationResult(
                success=True,
                action="read_clipboard",
                message=spoken,
                data={"text": clean, "length": length, "is_truncated": length > max_speech_chars},
                risk_level=AutomationRisk.LOW,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to read clipboard: %s", exc)
            return AutomationResult(
                success=False,
                action="read_clipboard",
                message=f"Could not access clipboard: {exc}",
                risk_level=AutomationRisk.LOW,
                error=str(exc),
            )

    def write_clipboard(self, text: str) -> AutomationResult:
        """Copy specified text to the Windows clipboard."""
        try:
            import pyperclip
            clean = text.strip()
            pyperclip.copy(clean)
            self._last_copied_text = clean
            return AutomationResult(
                success=True,
                action="write_clipboard",
                message="Text copied to clipboard successfully.",
                data={"length": len(clean)},
                risk_level=AutomationRisk.LOW,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to write to clipboard: %s", exc)
            return AutomationResult(
                success=False,
                action="write_clipboard",
                message=f"Could not copy to clipboard: {exc}",
                risk_level=AutomationRisk.LOW,
                error=str(exc),
            )
