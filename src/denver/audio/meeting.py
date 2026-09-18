"""Live Meeting Intelligence & System Audio Transcriber for Denver.

Captures live meeting audio via WASAPI Loopback / Microphone, transcribes in
sliding windows, detects user mentions, extracts action items in real-time,
and formats comprehensive markdown meeting summaries.
"""

from __future__ import annotations

import asyncio
import datetime
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from denver.audio.loopback import WasapiLoopbackCapture
from denver.audio.models import Transcript
from denver.audio.stt import SpeechToTextProvider
from denver.logging.logger import get_logger

logger = get_logger("audio.meeting")

_ACTION_ITEM_PATTERNS = [
    re.compile(r"(?:action item|todo|to-do|action point)[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"(?:need to|we need to|please ensure|please make sure to|make sure to)\s+([^.?!]+)", re.IGNORECASE),
    re.compile(r"(?:i will|we will|i'll|we'll|i am going to)\s+(?:take care of|follow up on|handle|send|prepare|build|fix|deploy|schedule|review)\s+([^.?!]+)", re.IGNORECASE),
    re.compile(r"(?:assigned to|assign to)\s+([a-zA-Z0-9_]+)[:\s]+([^.?!]+)", re.IGNORECASE),
    re.compile(r"(?:follow[- ]up with|follow[- ]up on|reach out to)\s+([^.?!]+)", re.IGNORECASE),
]

_MENTION_PATTERNS = [
    re.compile(r"\b(?:diwakar|denver|hey diwakar|hey denver)\b", re.IGNORECASE),
]


@dataclass
class MeetingTranscriptSegment:
    """Individual spoken segment in a meeting."""

    timestamp: float
    speaker: str
    text: str
    confidence: float = 1.0

    def formatted_time(self, start_time: float) -> str:
        offset_sec = max(0, int(self.timestamp - start_time))
        mins, secs = divmod(offset_sec, 60)
        return f"{mins:02d}:{secs:02d}"


@dataclass
class MeetingSession:
    """State and records for an active or completed meeting."""

    meeting_id: str
    title: str
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    segments: list[MeetingTranscriptSegment] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    key_points: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    is_active: bool = True

    @property
    def duration_seconds(self) -> float:
        end = self.end_time or time.time()
        return max(0.0, end - self.start_time)

    @property
    def formatted_duration(self) -> str:
        sec = int(self.duration_seconds)
        mins, s = divmod(sec, 60)
        hrs, m = divmod(mins, 60)
        if hrs > 0:
            return f"{hrs}h {m}m {s}s"
        return f"{m}m {s}s"


class MeetingIntelligenceEngine:
    """Coordinates system audio transcription, real-time mention alerts, and note generation."""

    def __init__(
        self,
        loopback_capture: WasapiLoopbackCapture | None = None,
        stt_provider: SpeechToTextProvider | None = None,
        user_name: str = "Diwakar",
        output_dir: Path | str = "data/meetings",
    ) -> None:
        self.loopback = loopback_capture or WasapiLoopbackCapture()
        self.stt = stt_provider
        self.user_name = user_name
        self.output_dir = Path(output_dir)
        self.current_session: MeetingSession | None = None
        self._background_task: asyncio.Task | None = None
        self._mention_callbacks: list[Callable[[str, MeetingTranscriptSegment], None]] = []

    @property
    def is_meeting_active(self) -> bool:
        return self.current_session is not None and self.current_session.is_active

    def register_mention_callback(self, callback: Callable[[str, MeetingTranscriptSegment], None]) -> None:
        """Register a notification hook when user's name is mentioned during a meeting."""
        self._mention_callbacks.append(callback)

    async def start_meeting(self, title: str = "Live Meeting") -> MeetingSession:
        """Start a live meeting intelligence recording session."""
        if self.is_meeting_active:
            logger.info("A meeting session is already active: '%s'", self.current_session.title)
            return self.current_session

        meeting_id = f"mtg_{int(time.time())}"
        self.current_session = MeetingSession(
            meeting_id=meeting_id,
            title=title.strip() or "Live Meeting",
            start_time=time.time(),
            is_active=True,
        )

        await self.loopback.start()
        logger.info("Meeting Intelligence session started: '%s' (ID: %s)", self.current_session.title, meeting_id)
        return self.current_session

    async def stop_meeting(self) -> MeetingSession | None:
        """Stop meeting session, halt audio capture, and persist final notes."""
        if not self.current_session:
            return None

        self.current_session.is_active = False
        self.current_session.end_time = time.time()
        await self.loopback.stop()

        if self._background_task and not self._background_task.done():
            self._background_task.cancel()

        # Generate and save markdown notes
        try:
            self.save_meeting_notes()
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to auto-save meeting notes: %s", exc)

        session = self.current_session
        logger.info("Meeting session '%s' finished. Total duration: %s", session.title, session.formatted_duration)
        return session

    def ingest_transcript_segment(
        self,
        text: str,
        speaker: str = "Remote Participant",
        timestamp: float | None = None,
        confidence: float = 1.0,
    ) -> MeetingTranscriptSegment | None:
        """Ingest a text segment, parse action items, and detect user mentions."""
        if not self.current_session:
            return None

        cleaned = text.strip()
        if not cleaned:
            return None

        seg = MeetingTranscriptSegment(
            timestamp=timestamp or time.time(),
            speaker=speaker,
            text=cleaned,
            confidence=confidence,
        )
        self.current_session.segments.append(seg)

        # 1. Mention Detection
        for pattern in _MENTION_PATTERNS:
            if pattern.search(cleaned):
                mention_str = f"[{seg.formatted_time(self.current_session.start_time)}] {speaker}: {cleaned}"
                if mention_str not in self.current_session.mentions:
                    self.current_session.mentions.append(mention_str)
                    for cb in self._mention_callbacks:
                        try:
                            cb(self.user_name, seg)
                        except Exception as exc:
                            logger.debug("Mention callback failed: %s", exc)
                break

        # 2. Action Item Extraction
        for pat in _ACTION_ITEM_PATTERNS:
            match = pat.search(cleaned)
            if match:
                action_text = match.group(1).strip()
                # Clean trailing punctuation
                action_text = re.sub(r"[.?!]+$", "", action_text)
                if len(action_text) > 4 and action_text not in self.current_session.action_items:
                    self.current_session.action_items.append(action_text)

        # 3. Key Point Extraction (sentences with high informational markers)
        if any(marker in cleaned.lower() for marker in ["agreed", "decided", "important", "deadline", "milestone", "key take", "conclusion"]):
            if cleaned not in self.current_session.key_points:
                self.current_session.key_points.append(cleaned)

        return seg

    async def transcribe_audio_chunk(self, audio_bytes: bytes, speaker: str = "Remote Participant") -> str:
        """Transcribe PCM audio chunk via STT provider and ingest."""
        if not self.stt or not audio_bytes:
            return ""

        try:
            transcript = await self.stt.transcribe(audio_bytes)
            if transcript and transcript.text.strip():
                self.ingest_transcript_segment(
                    text=transcript.text,
                    speaker=speaker,
                    confidence=transcript.confidence,
                )
                return transcript.text.strip()
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Error transcribing meeting audio chunk: %s", exc)

        return ""

    def generate_markdown_notes(self) -> str:
        """Generate structured GitHub-flavored Markdown meeting notes."""
        if not self.current_session:
            return "# No active meeting session"

        session = self.current_session
        date_str = datetime.datetime.fromtimestamp(session.start_time).strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            f"# 📋 Meeting Notes: {session.title}",
            "",
            f"- **Date & Time**: `{date_str}`",
            f"- **Duration**: `{session.formatted_duration}`",
            f"- **Status**: `{'Active' if session.is_active else 'Completed'}`",
            f"- **Meeting ID**: `{session.meeting_id}`",
            "",
            "---",
            "",
        ]

        # Key Decisions & Points
        lines.append("## 💡 Key Highlights & Decisions")
        if session.key_points:
            for kp in session.key_points:
                lines.append(f"- {kp}")
        else:
            lines.append("- *No explicit decisions flagged during session.*")
        lines.append("")

        # Action Items
        lines.append("## ✅ Action Items & Next Steps")
        if session.action_items:
            for item in session.action_items:
                lines.append(f"- [ ] {item}")
        else:
            lines.append("- [ ] *No immediate action items recorded.*")
        lines.append("")

        # Name Mentions
        if session.mentions:
            lines.append(f"## 🔔 Direct Mentions ({self.user_name})")
            for m in session.mentions:
                lines.append(f"- {m}")
            lines.append("")

        # Full Transcript Timeline
        lines.append("## 📜 Full Timeline & Transcript")
        if session.segments:
            for seg in session.segments:
                time_tag = seg.formatted_time(session.start_time)
                lines.append(f"- **[{time_tag}] {seg.speaker}**: {seg.text}")
        else:
            lines.append("*No spoken segments recorded.*")
        lines.append("")

        return "\n".join(lines)

    def save_meeting_notes(self, target_path: Path | str | None = None) -> Path:
        """Save generated markdown notes to disk."""
        if not self.current_session:
            raise RuntimeError("No meeting session to save.")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        if target_path is None:
            safe_title = re.sub(r"[^a-zA-Z0-9_\-]+", "_", self.current_session.title.lower()).strip("_")
            target_path = self.output_dir / f"{self.current_session.meeting_id}_{safe_title}.md"
        else:
            target_path = Path(target_path)

        content = self.generate_markdown_notes()
        target_path.write_text(content, encoding="utf-8")
        logger.info("Meeting notes saved to '%s'", target_path)
        return target_path

    def get_summary_dict(self) -> dict[str, Any]:
        """Return structured summary dictionary of current session."""
        if not self.current_session:
            return {"status": "NO_ACTIVE_SESSION", "message": "No meeting is currently being recorded."}

        session = self.current_session
        return {
            "meeting_id": session.meeting_id,
            "title": session.title,
            "duration": session.formatted_duration,
            "duration_seconds": session.duration_seconds,
            "is_active": session.is_active,
            "total_segments": len(session.segments),
            "action_items": list(session.action_items),
            "key_points": list(session.key_points),
            "mentions": list(session.mentions),
            "markdown_notes": self.generate_markdown_notes(),
        }
