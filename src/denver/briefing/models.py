"""Domain models for Proactive Morning & Evening Audio Briefings."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class BriefingType(str, Enum):
    """Classification of briefing period."""
    MORNING = "morning"
    EVENING = "evening"


@dataclass
class BriefingSection:
    """Individual categorical component within a briefing."""
    name: str
    title: str
    icon: str
    text: str
    spoken_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "icon": self.icon,
            "text": self.text,
            "spoken_text": self.spoken_text or self.text,
        }


@dataclass
class AudioBriefing:
    """Comprehensive multi-pillar briefing artifact with spoken narration script."""
    briefing_type: BriefingType
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    greeting: str = ""
    sections: list[BriefingSection] = field(default_factory=list)
    audio_played: bool = False
    audio_voice: str = "Ryan"

    @property
    def spoken_script(self) -> str:
        """Compose conversational, natural narration script for TTS synthesis."""
        parts = [self.greeting]
        for sec in self.sections:
            narration = sec.spoken_text.strip() if sec.spoken_text else sec.text.strip()
            if narration:
                parts.append(narration)
        return " ".join(parts)

    def format_display(self) -> str:
        """Format rich visual markdown summary for UI display."""
        header_icon = "🌅" if self.briefing_type == BriefingType.MORNING else "🌆"
        title_str = "Morning Briefing" if self.briefing_type == BriefingType.MORNING else "Evening Briefing & Wrap-Up"

        lines = [
            f"{header_icon} **Denver {title_str}**",
            f"*{self.greeting}*",
            "",
        ]

        for sec in self.sections:
            lines.append(f"### {sec.icon} {sec.title}")
            lines.append(sec.text)
            lines.append("")

        if self.audio_played:
            lines.append(f"🔊 *Spoken audio narrated via {self.audio_voice} (Edge-TTS).*")

        return "\n".join(lines).strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "briefing_type": self.briefing_type.value,
            "timestamp": self.timestamp,
            "greeting": self.greeting,
            "sections": [s.to_dict() for s in self.sections],
            "audio_played": self.audio_played,
            "audio_voice": self.audio_voice,
            "spoken_script": self.spoken_script,
        }
