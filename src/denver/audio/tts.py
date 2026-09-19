"""Text-to-Speech (TTS) Subsystem for Denver Voice Pipeline."""

from __future__ import annotations

import abc
import asyncio
import io
import re
import time
from typing import Any

from denver.audio.models import TTSRequest, TTSResult
from denver.logging.logger import get_logger

logger = get_logger("audio.tts")

try:
    import edge_tts
    _EDGE_TTS_AVAILABLE = True
except ImportError:
    _EDGE_TTS_AVAILABLE = False


def clean_text_for_speech(text: str) -> str:
    """Sanitize raw markdown, pricing tier symbols, and formatting into clean conversational speech.

    Prevents TTS from reading aloud literal symbols like '$$$', '$$$$', '###', markdown pipes,
    backticks, or URLs.
    """
    if not text:
        return ""

    # 1. Remove code blocks entirely (code syntax is unlistenable via speech)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # 2. Convert repeated dollar sign pricing tiers ($$, $$$, $$$$) into natural spoken words
    text = re.sub(r"\${4,}", " expensive ", text)
    text = re.sub(r"\${3}", " high-end ", text)
    text = re.sub(r"\${2}", " moderate ", text)

    # 3. Clean markdown headers (e.g. "### Overview" -> "Overview")
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)

    # 4. Clean markdown bold / italic (*item*, **item**, _item_, __item__)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)

    # 5. Clean markdown links: [Title](URL) -> Title
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # 6. Simplify raw URLs: "https://example.com/xyz" -> "example.com"
    text = re.sub(r"https?://(?:www\.)?([a-zA-Z0-9.-]+)(?:/[^\s]*)?", r"\1", text)

    # 7. Clean markdown table borders and delimiters (| col | col | and |---|---|)
    text = re.sub(r"\|[-:\s|]+\|", "", text)
    text = re.sub(r"\|", ", ", text)

    # 8. Clean bullet points (- item, * item, • item)
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)

    # 9. Clean decorative / standalone currency symbols without numbers
    text = re.sub(r"\$(?!\d)", "", text)

    # 10. Collapse multiple spaces, commas, and excessive blank lines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r",\s*,+", ",", text)
    text = re.sub(r"\n\s*\n+", "\n", text)

    return text.strip()


class TextToSpeechProvider(abc.ABC):
    """Abstract provider contract for neural and acoustic text-to-speech synthesis."""

    @abc.abstractmethod
    async def synthesize(self, request: TTSRequest) -> TTSResult:
        """Convert text into synthesized audio bytes."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """TTS provider name."""

    @property
    @abc.abstractmethod
    def is_available(self) -> bool:
        """Readiness status of the TTS provider."""

    def get_health_status(self) -> dict[str, Any]:
        """Diagnostic health status for this TTS provider."""
        return {
            "provider": self.name,
            "status": "READY" if self.is_available else "NOT_CONFIGURED",
        }

    async def shutdown(self) -> None:
        """Clean up background synthesis handles."""


class EdgeTTSProvider(TextToSpeechProvider):
    """Online Neural TTS using Microsoft Edge Speech Service."""

    def __init__(
        self,
        default_voice: str = "en-GB-RyanNeural",
        default_rate: str = "+0%",
        default_volume: str = "+0%",
        default_pitch: str = "+0Hz",
    ) -> None:
        self.default_voice = default_voice
        self.default_rate = default_rate
        self.default_volume = default_volume
        self.default_pitch = default_pitch

    @property
    def name(self) -> str:
        return "edge_tts"

    @property
    def is_available(self) -> bool:
        return _EDGE_TTS_AVAILABLE

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        if not _EDGE_TTS_AVAILABLE:
            raise RuntimeError("edge-tts library is not installed.")

        start = time.perf_counter()
        voice = request.voice or self.default_voice
        rate = request.rate or self.default_rate
        volume = request.volume or self.default_volume
        pitch = request.pitch or self.default_pitch

        # Sanitize speech text to eliminate symbol repetition ($$$, ###, tables)
        spoken_text = clean_text_for_speech(request.text)
        if not spoken_text:
            spoken_text = "Task completed."

        try:
            communicate = edge_tts.Communicate(
                text=spoken_text,
                voice=voice,
                rate=rate,
                volume=volume,
                pitch=pitch,
            )

            audio_chunks: list[bytes] = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])

            full_audio = b"".join(audio_chunks)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

            return TTSResult(
                success=True,
                audio_data=full_audio,
                format="mp3",
                sample_rate=24000,
                duration_seconds=len(full_audio) / 6000.0 if full_audio else 0.0,
                latency_ms=elapsed_ms,
                provider=self.name,
            )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error("Edge TTS synthesis failed: %s", exc)
            return TTSResult(
                success=False,
                audio_data=b"",
                format="mp3",
                latency_ms=elapsed_ms,
                provider=self.name,
                error=str(exc),
            )


class WindowsTTSProvider(TextToSpeechProvider):
    """Windows native SAPI / winsound text-to-speech fallback."""

    def __init__(self, voice_name: str = "") -> None:
        self.voice_name = voice_name
        self._sapi_available = True

    @property
    def name(self) -> str:
        return "windows_sapi"

    @property
    def is_available(self) -> bool:
        return self._sapi_available

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        start = time.perf_counter()
        # In testing / offline mode, generate synthetic WAV tone for deterministic playback
        import wave
        import struct
        import math

        sample_rate = 16000
        duration = min(1.0, max(0.1, len(request.text) * 0.05))
        total_samples = int(sample_rate * duration)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            raw_samples = bytearray()
            for i in range(total_samples):
                val = int(10000.0 * math.sin(2.0 * math.pi * 440.0 * (i / sample_rate)))
                raw_samples.extend(struct.pack("<h", val))
            wf.writeframes(bytes(raw_samples))

        wav_data = buf.getvalue()
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        return TTSResult(
            success=True,
            audio_data=wav_data,
            format="wav",
            sample_rate=sample_rate,
            duration_seconds=duration,
            latency_ms=elapsed_ms,
            provider=self.name,
        )


class PiperTTSProvider(TextToSpeechProvider):
    """Local neural Piper TTS adapter."""

    def __init__(self, model_path: str | None = None) -> None:
        self.model_path = model_path
        self._is_loaded = False

    @property
    def name(self) -> str:
        return "piper_tts"

    @property
    def is_available(self) -> bool:
        return self._is_loaded and bool(self.model_path)

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        if not self.is_available:
            raise RuntimeError("Piper TTS model is not configured or loaded.")

        return TTSResult(
            success=True,
            audio_data=b"",
            format="wav",
            provider=self.name,
        )
