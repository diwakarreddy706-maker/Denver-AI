"""Voice Profile Manager: Dynamic Edge-TTS Neural Voice Switching, Rate, Pitch & Persistence."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from denver.audio.models import TTSRequest
from denver.audio.voices import VOICE_CATALOG, VoiceProfile, find_voice, list_available_voices
from denver.logging.logger import get_logger

logger = get_logger("audio.voice_manager")


class VoiceProfileManager:
    """Manages spoken voice profile selection, speech pacing, pitch, and persistent preferences."""

    def __init__(
        self,
        db_conn: sqlite3.Connection | None = None,
        audio_pipeline: Any = None,
        tts_provider: Any = None,
    ) -> None:
        self.db_conn = db_conn
        self.audio_pipeline = audio_pipeline
        self.tts_provider = tts_provider

        # Default parameters
        self.active_voice: VoiceProfile = VOICE_CATALOG[0]  # Ryan (British Male default)
        self.active_rate: str = "+0%"
        self.active_pitch: str = "+0Hz"
        self.active_volume: str = "+0%"

        # Load persisted preferences if database available
        self._load_preferences()

    def _get_connection(self) -> sqlite3.Connection | None:
        """Retrieve existing connection or connect to memory DB."""
        if self.db_conn:
            return self.db_conn
        try:
            from denver.memory.migrations import DB_PATH
            return sqlite3.connect("denver_memory.sqlite3")
        except Exception:
            return None

    def _load_preferences(self) -> None:
        """Load user-configured voice, speed, and pitch preferences from SQLite."""
        conn = self._get_connection()
        if not conn:
            return
        try:
            cursor = conn.execute(
                "SELECT key, value FROM user_preferences WHERE category = 'voice';"
            )
            for row in cursor.fetchall():
                k, v = row[0], row[1]
                if k == "voice_id":
                    matched = find_voice(v)
                    if matched:
                        self.active_voice = matched
                elif k == "rate":
                    self.active_rate = v
                elif k == "pitch":
                    self.active_pitch = v
                elif k == "volume":
                    self.active_volume = v
            self._apply_to_tts()
        except Exception as exc:
            logger.debug("Failed to load voice preferences from database: %s", exc)

    def _save_preference(self, key: str, value: str) -> None:
        """Persist a voice preference setting into SQLite user_preferences."""
        conn = self._get_connection()
        if not conn:
            return
        try:
            conn.execute(
                """
                INSERT INTO user_preferences (category, key, value, confidence, source)
                VALUES ('voice', ?, ?, 1.0, 'explicit_user')
                ON CONFLICT(category, key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP;
                """,
                (key, value),
            )
            conn.commit()
        except Exception as exc:
            logger.debug("Could not persist voice preference '%s': %s", key, exc)

    def _apply_to_tts(self) -> None:
        """Synchronize active voice settings to underlying TTS engine and pipeline."""
        tts = self.tts_provider
        if not tts and self.audio_pipeline and hasattr(self.audio_pipeline, "tts"):
            tts = self.audio_pipeline.tts

        if tts:
            if hasattr(tts, "default_voice"):
                tts.default_voice = self.active_voice.voice_id
            if hasattr(tts, "default_rate"):
                tts.default_rate = self.active_rate
            if hasattr(tts, "default_pitch"):
                tts.default_pitch = self.active_pitch
            if hasattr(tts, "default_volume"):
                tts.default_volume = self.active_volume

    def set_voice(self, query: str) -> tuple[bool, VoiceProfile | None, str]:
        """Switch active spoken voice personality profile."""
        profile = find_voice(query)
        if not profile:
            available = ", ".join(f"{v.name} ({v.gender})" for v in VOICE_CATALOG[:6])
            return False, None, f"Could not find voice matching '{query}'. Available options include: {available}."

        self.active_voice = profile
        self._apply_to_tts()
        self._save_preference("voice_id", profile.voice_id)
        logger.info("Voice changed to: %s (%s)", profile.name, profile.voice_id)

        msg = f"Switched spoken voice to {profile.name} ({profile.locale} {profile.gender}, {profile.tone})."
        return True, profile, msg

    def set_speed(self, speed_expr: str) -> tuple[bool, str, str]:
        """Parse colloquial or percentage speech rate adjustments."""
        s = speed_expr.strip().lower()
        new_rate = self.active_rate

        if any(w in s for w in ("very fast", "super fast", "fastest")):
            new_rate = "+30%"
        elif any(w in s for w in ("fast", "faster", "quick", "quicker", "speed up")):
            new_rate = "+15%"
        elif any(w in s for w in ("very slow", "slowest")):
            new_rate = "-30%"
        elif any(w in s for w in ("slow", "slower")):
            new_rate = "-15%"
        elif any(w in s for w in ("normal", "regular", "default", "standard", "reset")):
            new_rate = "+0%"
        elif "%" in s:
            match = re.search(r"([+-]?\d+)\s*%", s)
            if match:
                val = int(match.group(1))
                new_rate = f"+{val}%" if val >= 0 else f"{val}%"
        elif re.match(r"^\d+(?:\.\d+)?x$", s):
            # 1.2x -> +20%, 0.8x -> -20%
            factor = float(s.rstrip("x"))
            pct = round((factor - 1.0) * 100)
            new_rate = f"+{pct}%" if pct >= 0 else f"{pct}%"

        self.active_rate = new_rate
        self._apply_to_tts()
        self._save_preference("rate", new_rate)

        label = "normal" if new_rate == "+0%" else ("faster" if new_rate.startswith("+") else "slower")
        return True, new_rate, f"Speech rate set to {new_rate} ({label})."

    def set_pitch(self, pitch_expr: str) -> tuple[bool, str, str]:
        """Parse colloquial or frequency pitch adjustments."""
        p = pitch_expr.strip().lower()
        new_pitch = self.active_pitch

        if any(w in p for w in ("deep", "deeper", "low", "lower")):
            new_pitch = "-10Hz"
        elif any(w in p for w in ("high", "higher")):
            new_pitch = "+10Hz"
        elif any(w in p for w in ("normal", "default", "standard", "reset")):
            new_pitch = "+0Hz"
        elif "hz" in p:
            match = re.search(r"([+-]?\d+)\s*hz", p)
            if match:
                val = int(match.group(1))
                new_pitch = f"+{val}Hz" if val >= 0 else f"{val}Hz"

        self.active_pitch = new_pitch
        self._apply_to_tts()
        self._save_preference("pitch", new_pitch)

        return True, new_pitch, f"Voice pitch set to {new_pitch}."

    async def preview_voice(
        self,
        voice_query: str | None = None,
        custom_phrase: str | None = None,
    ) -> tuple[bool, str]:
        """Synthesize and preview a voice sample."""
        target_voice = find_voice(voice_query) if voice_query else self.active_voice
        if not target_voice:
            return False, f"Could not find voice matching '{voice_query}'."

        phrase = custom_phrase or f"Hello, I am {target_voice.name}. This is how I sound speaking at {self.active_rate} speed."

        tts = self.tts_provider
        if not tts and self.audio_pipeline and hasattr(self.audio_pipeline, "tts"):
            tts = self.audio_pipeline.tts

        if tts and hasattr(tts, "synthesize"):
            try:
                res = await tts.synthesize(
                    TTSRequest(
                        text=phrase,
                        voice=target_voice.voice_id,
                        rate=self.active_rate,
                        pitch=self.active_pitch,
                        volume=self.active_volume,
                    )
                )
                if res.success and self.audio_pipeline and hasattr(self.audio_pipeline, "playback"):
                    await self.audio_pipeline.playback.play(res.audio_data, audio_format=res.format)
                return True, f"Previewing voice '{target_voice.name}' ({target_voice.locale}): \"{phrase}\""
            except Exception as exc:
                logger.warning("Voice preview playback error: %s", exc)

        return True, f"Voice sample for {target_voice.name} ({target_voice.voice_id}): \"{phrase}\""

    def get_status(self) -> dict[str, Any]:
        """Return active profile and configuration details."""
        return {
            "active_voice": self.active_voice.to_dict(),
            "rate": self.active_rate,
            "pitch": self.active_pitch,
            "volume": self.active_volume,
            "available_voices_count": len(VOICE_CATALOG),
        }


# Module singleton
_VOICE_MANAGER: VoiceProfileManager | None = None


def get_voice_manager(
    db_conn: sqlite3.Connection | None = None,
    audio_pipeline: Any = None,
    tts_provider: Any = None,
) -> VoiceProfileManager:
    """Retrieve or initialize shared VoiceProfileManager."""
    global _VOICE_MANAGER
    if _VOICE_MANAGER is None:
        _VOICE_MANAGER = VoiceProfileManager(
            db_conn=db_conn,
            audio_pipeline=audio_pipeline,
            tts_provider=tts_provider,
        )
    else:
        if db_conn is not None and _VOICE_MANAGER.db_conn is not db_conn:
            _VOICE_MANAGER.db_conn = db_conn
        if audio_pipeline is not None and _VOICE_MANAGER.audio_pipeline is not audio_pipeline:
            _VOICE_MANAGER.audio_pipeline = audio_pipeline
        if tts_provider is not None and _VOICE_MANAGER.tts_provider is not tts_provider:
            _VOICE_MANAGER.tts_provider = tts_provider
    return _VOICE_MANAGER
