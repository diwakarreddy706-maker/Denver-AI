"""Hands-Free Keyboard and Typing Automation for Denver AI Assistant."""

from __future__ import annotations

import time
from typing import Any

from denver.automation.models import AutomationResult, AutomationRisk
from denver.logging.logger import get_logger

logger = get_logger("automation.keyboard")

_ALLOWED_KEYS = {
    "enter": "enter",
    "return": "enter",
    "space": "space",
    "spacebar": "space",
    "tab": "tab",
    "escape": "esc",
    "esc": "esc",
    "backspace": "backspace",
    "delete": "delete",
    "del": "delete",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "pageup": "pageup",
    "pagedown": "pagedown",
    "home": "home",
    "end": "end",
}


class KeyboardController:
    """Automates hands-free typing, key presses, and scrolling into active desktop windows."""

    def __init__(self) -> None:
        pass

    def type_text(self, text: str, interval: float = 0.005) -> AutomationResult:
        """Type specified text into the currently focused desktop window."""
        if not text:
            return AutomationResult(
                success=False,
                action="type_text",
                message="No text provided to type.",
                risk_level=AutomationRisk.LOW,
                error="EmptyText",
            )

        try:
            import pyautogui
            pyautogui.write(text, interval=interval)
            logger.info("Typed %d characters into active window.", len(text))
            return AutomationResult(
                success=True,
                action="type_text",
                message=f"Typed text into active window ({len(text)} characters).",
                data={"text_length": len(text)},
                risk_level=AutomationRisk.LOW,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to type text: %s", exc)
            return AutomationResult(
                success=False,
                action="type_text",
                message=f"Typing error: {exc}",
                risk_level=AutomationRisk.LOW,
                error=str(exc),
            )

    def press_key(self, key_name: str) -> AutomationResult:
        """Press a single keyboard key (e.g. enter, space, tab, escape, backspace)."""
        clean_key = key_name.strip().lower()
        mapped_key = _ALLOWED_KEYS.get(clean_key)
        if not mapped_key:
            return AutomationResult(
                success=False,
                action="press_key",
                message=f"Key '{key_name}' is not recognized or supported.",
                risk_level=AutomationRisk.LOW,
                error="UnsupportedKey",
            )

        try:
            import pyautogui
            pyautogui.press(mapped_key)
            logger.info("Pressed key '%s'.", mapped_key)
            return AutomationResult(
                success=True,
                action="press_key",
                message=f"Pressed {mapped_key.capitalize()} key.",
                data={"key": mapped_key},
                risk_level=AutomationRisk.LOW,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to press key '%s': %s", mapped_key, exc)
            return AutomationResult(
                success=False,
                action="press_key",
                message=f"Key press error: {exc}",
                risk_level=AutomationRisk.LOW,
                error=str(exc),
            )

    def scroll(self, direction: str = "down", amount: int = 5) -> AutomationResult:
        """Scroll mouse wheel in the active window (up or down)."""
        clean_dir = direction.strip().lower()
        clicks = max(1, min(50, amount))
        scroll_amount = -clicks * 100 if clean_dir in ("down", "bottom") else clicks * 100

        try:
            import pyautogui
            pyautogui.scroll(scroll_amount)
            logger.info("Scrolled %s by %d steps.", clean_dir, clicks)
            return AutomationResult(
                success=True,
                action="scroll_window",
                message=f"Scrolled {clean_dir}.",
                data={"direction": clean_dir, "steps": clicks},
                risk_level=AutomationRisk.LOW,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to scroll: %s", exc)
            return AutomationResult(
                success=False,
                action="scroll_window",
                message=f"Scroll error: {exc}",
                risk_level=AutomationRisk.LOW,
                error=str(exc),
            )
