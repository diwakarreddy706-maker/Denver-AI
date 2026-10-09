"""Curated Edge-TTS Neural Voice Profiles and Locale Catalog for Denver AI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VoiceProfile:
    """Represents a neural voice personality profile."""
    voice_id: str
    name: str
    locale: str
    gender: str
    tone: str
    description: str
    sample_phrase: str = "Hello, I am Denver, your personal AI assistant on Windows."

    def to_dict(self) -> dict[str, Any]:
        return {
            "voice_id": self.voice_id,
            "name": self.name,
            "locale": self.locale,
            "gender": self.gender,
            "tone": self.tone,
            "description": self.description,
            "sample_phrase": self.sample_phrase,
        }

    def display_label(self) -> str:
        return f"{self.name} ({self.locale} {self.gender}) - {self.tone}"


# Curated catalog of Microsoft Edge Neural voices optimized for English desktop assistance
VOICE_CATALOG: list[VoiceProfile] = [
    VoiceProfile(
        voice_id="en-GB-RyanNeural",
        name="Ryan",
        locale="en-GB",
        gender="Male",
        tone="Composed & Formal",
        description="British English male voice, classic Denver default.",
    ),
    VoiceProfile(
        voice_id="en-GB-SoniaNeural",
        name="Sonia",
        locale="en-GB",
        gender="Female",
        tone="Crisp & Professional",
        description="British English female voice, articulate and warm.",
    ),
    VoiceProfile(
        voice_id="en-US-ChristopherNeural",
        name="Christopher",
        locale="en-US",
        gender="Male",
        tone="Deep & Conversational",
        description="American English male voice, natural podcast/assistant tone.",
    ),
    VoiceProfile(
        voice_id="en-US-JennyNeural",
        name="Jenny",
        locale="en-US",
        gender="Female",
        tone="Friendly & Expressive",
        description="American English female voice, standard expressive assistant.",
    ),
    VoiceProfile(
        voice_id="en-US-GuyNeural",
        name="Guy",
        locale="en-US",
        gender="Male",
        tone="Direct & Casual",
        description="American English male voice, direct and clear.",
    ),
    VoiceProfile(
        voice_id="en-US-AriaNeural",
        name="Aria",
        locale="en-US",
        gender="Female",
        tone="Confident & Clear",
        description="American English female voice, energetic and clear.",
    ),
    VoiceProfile(
        voice_id="en-AU-NatNeural",
        name="Nat",
        locale="en-AU",
        gender="Female",
        tone="Calm & Natural",
        description="Australian English female voice, relaxed and friendly.",
    ),
    VoiceProfile(
        voice_id="en-IN-NeerjaNeural",
        name="Neerja",
        locale="en-IN",
        gender="Female",
        tone="Melodic & Articulate",
        description="Indian English female voice, natural cadence.",
    ),
    VoiceProfile(
        voice_id="en-IN-PrabhatNeural",
        name="Prabhat",
        locale="en-IN",
        gender="Male",
        tone="Professional & Smooth",
        description="Indian English male voice, formal and clear.",
    ),
]


def list_available_voices() -> list[VoiceProfile]:
    """Return all curated neural voice profiles."""
    return list(VOICE_CATALOG)


def find_voice(query: str) -> VoiceProfile | None:
    """Find voice by ID, name, gender, or locale with case-insensitive fuzzy matching."""
    q = query.strip().lower()
    if not q:
        return None

    # 1. Exact or substring match on voice_id
    for v in VOICE_CATALOG:
        if v.voice_id.lower() == q or q in v.voice_id.lower():
            return v

    # 2. Match on voice name (e.g. "christopher", "ryan", "jenny", "sonia")
    for v in VOICE_CATALOG:
        if v.name.lower() == q or q in v.name.lower():
            return v

    # 3. Match on descriptors (e.g. "british female", "american male", "australian", "indian")
    q_words = set(q.split())
    for v in VOICE_CATALOG:
        desc_lower = f"{v.locale} {v.gender} {v.tone} {v.description}".lower()
        if all(w in desc_lower for w in q_words):
            return v

    # 4. Partial word matches
    for v in VOICE_CATALOG:
        if any(w in v.name.lower() or w in v.gender.lower() for w in q_words):
            return v

    return None
