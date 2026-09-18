"""Unit tests for Clipboard Intelligence, Keyboard Automation, and URL Safety."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from denver.automation.clipboard import ClipboardController, summarize_text_locally
from denver.automation.keyboard import KeyboardController
from denver.automation.url_safety import build_google_search_url, is_safe_url, normalize_web_url
from denver.commands.router import IntentRouter


class TestClipboardAndKeyboard(unittest.TestCase):
    """Test suite for Clipboard, Keyboard, and URL Safety guardrails."""

    def setUp(self) -> None:
        self.router = IntentRouter()
        self.clipboard = ClipboardController()
        self.keyboard = KeyboardController()

    def test_url_safety_guardrails(self) -> None:
        """Verify URL validation and dangerous scheme blocking."""
        self.assertTrue(is_safe_url("https://www.google.com"))
        self.assertTrue(is_safe_url("http://github.com"))
        self.assertTrue(is_safe_url("github.com/trending"))

        # Dangerous schemes blocked
        self.assertFalse(is_safe_url("javascript:alert(1)"))
        self.assertFalse(is_safe_url("file:///etc/passwd"))
        self.assertFalse(is_safe_url("data:text/html,<script>"))
        self.assertFalse(is_safe_url("https://example.com; rm -rf /"))

        # Normalization
        self.assertEqual(normalize_web_url("google.com"), "https://google.com")
        self.assertIsNone(normalize_web_url("javascript:void(0)"))

        # Search query builder
        search_url = build_google_search_url("denver ai assistant")
        self.assertIn("q=denver+ai+assistant", search_url)

    def test_local_summarizer(self) -> None:
        """Verify local extractive summarizer."""
        text = "Denver is an AI desktop assistant. It can automate Windows tasks and process voice commands. It is very fast."
        summary = summarize_text_locally(text, sentence_limit=2)
        self.assertIn("Denver is an AI desktop assistant", summary)
        self.assertIn("It can automate Windows tasks", summary)

    @patch("pyperclip.paste", return_value="Sample copied text from browser")
    def test_read_clipboard(self, mock_paste: MagicMock) -> None:
        """Verify reading clipboard content."""
        res = self.clipboard.read_clipboard()
        self.assertTrue(res.success)
        self.assertEqual(res.data.get("text"), "Sample copied text from browser")

    @patch("pyperclip.copy")
    def test_write_clipboard(self, mock_copy: MagicMock) -> None:
        """Verify writing text to clipboard."""
        res = self.clipboard.write_clipboard("Hello Denver")
        self.assertTrue(res.success)
        mock_copy.assert_called_once_with("Hello Denver")

    @patch("pyautogui.write")
    def test_type_text(self, mock_write: MagicMock) -> None:
        """Verify hands-free typing automation."""
        res = self.keyboard.type_text("Testing typing")
        self.assertTrue(res.success)
        mock_write.assert_called_once()

    @patch("pyautogui.press")
    def test_press_key(self, mock_press: MagicMock) -> None:
        """Verify key press automation."""
        res = self.keyboard.press_key("enter")
        self.assertTrue(res.success)
        mock_press.assert_called_once_with("enter")

        # Invalid key returns error
        bad_res = self.keyboard.press_key("nonexistent_key_xyz")
        self.assertFalse(bad_res.success)

    @patch("pyautogui.scroll")
    def test_scroll(self, mock_scroll: MagicMock) -> None:
        """Verify scrolling active window."""
        res = self.keyboard.scroll("down", amount=5)
        self.assertTrue(res.success)
        mock_scroll.assert_called_once_with(-500)

    def test_intent_routing_clipboard_and_keyboard(self) -> None:
        """Verify natural language routing to new actions."""
        self.assertEqual(self.router.route("read clipboard").action_name, "read_clipboard")
        self.assertEqual(self.router.route("what did I copy").action_name, "read_clipboard")
        self.assertEqual(self.router.route("summarize clipboard").action_name, "summarize_clipboard")

        type_intent = self.router.route("type meeting starts at 3 PM")
        self.assertEqual(type_intent.action_name, "type_text")
        self.assertEqual(type_intent.params.get("text"), "meeting starts at 3 PM")

        press_intent = self.router.route("press enter")
        self.assertEqual(press_intent.action_name, "press_key")
        self.assertEqual(press_intent.params.get("key"), "enter")

        scroll_intent = self.router.route("scroll down 10")
        self.assertEqual(scroll_intent.action_name, "scroll_window")
        self.assertEqual(scroll_intent.params.get("direction"), "down")
        self.assertEqual(scroll_intent.params.get("steps"), 10)


if __name__ == "__main__":
    unittest.main()
