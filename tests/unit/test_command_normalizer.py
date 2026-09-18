"""Unit tests for CommandNormalizer."""

from __future__ import annotations

import unittest
from denver.commands.normalizer import CommandNormalizer


class TestCommandNormalizer(unittest.TestCase):
    """Test suite for deterministic command text normalization."""

    def setUp(self) -> None:
        self.normalizer = CommandNormalizer(assistant_name="Denver")

    def test_whitespace_and_casing(self) -> None:
        """Verify extra whitespace is collapsed and text is lowercased."""
        self.assertEqual(self.normalizer.normalize("   OPEN    CHROME   "), "open chrome")
        self.assertEqual(self.normalizer.normalize("WHAT IS THE TIME"), "what is the time")

    def test_denver_prefix_stripping(self) -> None:
        """Verify assistant name variations are stripped from the beginning."""
        variations = [
            ("Denver, open Chrome", "open chrome"),
            ("denver open chrome", "open chrome"),
            ("Hey Denver, open Chrome", "open chrome"),
            ("Hello Denver: open Chrome", "open chrome"),
            ("Denver please open Chrome", "open chrome"),
            ("Please Denver open Chrome", "open chrome"),
            ("Please open Chrome", "open chrome"),
            ("Open Chrome, please", "open chrome"),
        ]
        for raw, expected in variations:
            self.assertEqual(self.normalizer.normalize(raw), expected, f"Failed on raw: {raw}")

    def test_punctuation_handling(self) -> None:
        """Verify surrounding punctuation is stripped while keeping paths and URLs intact."""
        self.assertEqual(self.normalizer.normalize("Denver, what time is it???"), "what time is it")
        self.assertEqual(self.normalizer.normalize("open https://github.com/"), "open https://github.com/")
        self.assertEqual(self.normalizer.normalize("open C:\\Dev\\Project"), "open c:\\dev\\project")

    def test_empty_and_null_input(self) -> None:
        """Verify empty and whitespace inputs return empty string."""
        self.assertEqual(self.normalizer.normalize(""), "")
        self.assertEqual(self.normalizer.normalize("   "), "")
        self.assertEqual(self.normalizer.normalize(None), "")


if __name__ == "__main__":
    unittest.main()
