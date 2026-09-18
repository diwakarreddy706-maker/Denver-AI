"""Unit tests for Denver Voice Brevity & Response Style Modes."""

from __future__ import annotations

import pytest

from denver.commands.router import IntentRouter
from denver.config.settings import DenverSettings


def test_intent_router_voice_brevity_intents() -> None:
    router = IntentRouter()

    concise_phrases = [
        "be concise",
        "concise mode",
        "switch to concise mode",
        "enable concise responses",
        "set voice mode to concise",
        "be brief",
        "brief mode",
    ]

    for phrase in concise_phrases:
        res = router.route(phrase)
        assert res.intent_name == "set_voice_brevity", f"Failed for '{phrase}'"
        assert res.params.get("mode") == "concise"

    detailed_phrases = [
        "be detailed",
        "detailed mode",
        "switch to detailed mode",
        "enable verbose mode",
        "set voice mode to detailed",
    ]

    for phrase in detailed_phrases:
        res = router.route(phrase)
        assert res.intent_name == "set_voice_brevity", f"Failed for '{phrase}'"
        assert res.params.get("mode") == "detailed"


def test_settings_voice_brevity_defaults() -> None:
    settings = DenverSettings()
    assert settings.voice_brevity == "concise"

    custom_settings = DenverSettings(voice_brevity="detailed")
    assert custom_settings.voice_brevity == "detailed"
