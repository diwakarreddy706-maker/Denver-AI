"""Unit tests for clean_text_for_speech in Denver TTS subsystem."""

from __future__ import annotations

import pytest
from denver.audio.tts import clean_text_for_speech


def test_clean_repeated_dollar_signs_price_tiers():
    """Verify repeated dollar signs ($$, $$$, $$$$) are converted to spoken terms."""
    text1 = "For a high budget, consider Tier 1 ($$$$) models."
    res1 = clean_text_for_speech(text1)
    assert "$$$$" not in res1
    assert "expensive" in res1

    text2 = "This joystick is rated $$$ for performance."
    res2 = clean_text_for_speech(text2)
    assert "$$$" not in res2
    assert "high-end" in res2

    text3 = "A budget-friendly option is $$."
    res3 = clean_text_for_speech(text3)
    assert "$$" not in res3
    assert "moderate" in res3


def test_preserve_actual_currency_amounts():
    """Verify legitimate currency amounts ($50, $150.99) are kept intact for TTS."""
    text = "The Thrustmaster T16000M costs $80, while the Warthog is $500."
    res = clean_text_for_speech(text)
    assert "$80" in res
    assert "$500" in res


def test_clean_markdown_headers():
    """Verify markdown headers (### Header) are stripped so TTS does not read 'hash'."""
    text = "### Best Gaming Joysticks\n#### Recommended Flight Sticks\nHere are the top picks:"
    res = clean_text_for_speech(text)
    assert "###" not in res
    assert "####" not in res
    assert "Best Gaming Joysticks" in res
    assert "Recommended Flight Sticks" in res


def test_clean_markdown_tables():
    """Verify markdown table formatting (| col | and |---|---|) is cleaned."""
    text = (
        "| Category | Model | Price |\n"
        "|----------|-------|-------|\n"
        "| Flight   | X56   | $250  |\n"
    )
    res = clean_text_for_speech(text)
    assert "|---" not in res
    assert "$250" in res
    assert "X56" in res


def test_clean_markdown_styling_and_links():
    """Verify bold, italics, links, and code blocks are sanitized."""
    text = (
        "Check out **Logitech G X56** and *Thrustmaster* at [their website](https://example.com/item). "
        "Run `setup.exe` to configure."
    )
    res = clean_text_for_speech(text)
    assert "**" not in res
    assert "*" not in res
    assert "[their website]" not in res
    assert "their website" in res
    assert "https://" not in res
    assert "`" not in res
    assert "setup.exe" in res


def test_clean_empty_and_whitespace():
    """Verify empty or whitespace strings return empty string safely."""
    assert clean_text_for_speech("") == ""
    assert clean_text_for_speech("   ") == ""
    assert clean_text_for_speech(None) == ""  # type: ignore
