"""Speech-to-Text (STT) Subsystem for Denver Voice Pipeline."""

from __future__ import annotations

import abc
import asyncio
import json
import time
import urllib.request
from typing import Any

from denver.audio.models import AudioFormat, Transcript
from denver.logging.logger import get_logger
from denver.security.vault import DenverVault, get_vault

logger = get_logger("audio.stt")


class SpeechToTextProvider(abc.ABC):
    """Abstract provider contract for speech-to-text recognition."""

    @abc.abstractmethod
    async def transcribe(self, audio_bytes: bytes, audio_format: AudioFormat | None = None) -> Transcript:
        """Convert raw PCM audio bytes to recognized text transcript."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider name."""

    @property
    @abc.abstractmethod
    def is_available(self) -> bool:
        """Readiness status of the STT engine."""

    def get_health_status(self) -> dict[str, Any]:
        """Diagnostic health status for this STT provider."""
        return {
            "provider": self.name,
            "status": "READY" if self.is_available else "NOT_CONFIGURED",
        }

    async def shutdown(self) -> None:
        """Clean up background resources and model handles."""


class WhisperSTTProvider(SpeechToTextProvider):
    """Local offline STT engine using faster-whisper or standard Whisper."""

    def __init__(
        self,
        model_size: str = "base",
        language: str = "en",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        self.model_size = model_size
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self._model: Any = None
        self._is_loaded = False

    @property
    def name(self) -> str:
        return "whisper"

    @property
    def is_available(self) -> bool:
        return self._is_loaded

    def load_model(self) -> bool:
        """Explicitly load the Whisper model into memory (never auto-downloaded on startup)."""
        try:
            import importlib
            fw_module = importlib.import_module("faster_whisper")
            whisper_model_cls = getattr(fw_module, "WhisperModel")
            self._model = whisper_model_cls(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                local_files_only=True,
            )
            self._is_loaded = True
            logger.info("Faster-Whisper model '%s' successfully loaded.", self.model_size)
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("Faster-Whisper model load deferred or missing: %s", exc)
            self._is_loaded = False
            return False

    async def transcribe(self, audio_bytes: bytes, audio_format: AudioFormat | None = None) -> Transcript:
        if not self._is_loaded or not self._model:
            return Transcript(text="", is_final=True, confidence=0.0, provider=self.name)

        start = time.perf_counter()
        fmt = audio_format or AudioFormat()

        def _sync_transcribe() -> str:
            import io
            import numpy as np
            samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            segments, _ = self._model.transcribe(samples, language=self.language, beam_size=5)
            return " ".join(s.text.strip() for s in segments)

        text = await asyncio.to_thread(_sync_transcribe)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return Transcript(
            text=text,
            is_final=True,
            confidence=0.95,
            language=self.language,
            latency_ms=elapsed_ms,
            provider=self.name,
        )


class GroqWhisperSTTProvider(SpeechToTextProvider):
    """Cloud-accelerated Whisper STT using Groq API with Denver Vault authentication."""

    def __init__(
        self,
        vault: DenverVault | None = None,
        model_name: str = "whisper-large-v3",
        language: str = "en",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.vault = vault or get_vault()
        self.model_name = model_name
        self.language = language
        self.timeout_seconds = timeout_seconds

    @property
    def name(self) -> str:
        return "groq_whisper"

    @property
    def is_available(self) -> bool:
        return bool(self.vault.get_secret("GROQ_API_KEY"))

    async def transcribe(self, audio_bytes: bytes, audio_format: AudioFormat | None = None) -> Transcript:
        api_key = self.vault.get_secret("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not configured in Denver Vault.")

        start = time.perf_counter()
        fmt = audio_format or AudioFormat()

        # Build WAV in-memory buffer
        def _build_wav() -> bytes:
            import io
            import wave
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(fmt.channels)
                wf.setsampwidth(fmt.sample_width)
                wf.setframerate(fmt.sample_rate)
                wf.writeframes(audio_bytes)
            return buf.getvalue()

        wav_bytes = _build_wav()

        # Execute multipart POST via urllib
        boundary = "----DenverAudioBoundary" + str(int(time.time()))
        body = []
        body.append(f"--{boundary}\r\n".encode("utf-8"))
        body.append(b'Content-Disposition: form-data; name="model"\r\n\r\n')
        body.append(self.model_name.encode("utf-8") + b"\r\n")

        body.append(f"--{boundary}\r\n".encode("utf-8"))
        body.append(b'Content-Disposition: form-data; name="language"\r\n\r\n')
        body.append(self.language.encode("utf-8") + b"\r\n")

        body.append(f"--{boundary}\r\n".encode("utf-8"))
        body.append(b'Content-Disposition: form-data; name="file"; filename="speech.wav"\r\n')
        body.append(b"Content-Type: audio/wav\r\n\r\n")
        body.append(wav_bytes + b"\r\n")
        body.append(f"--{boundary}--\r\n".encode("utf-8"))

        full_body = b"".join(body)
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        req = urllib.request.Request(
            url,
            data=full_body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "Denver/1.0 (Windows NT 10.0; Win64; x64)",
            },
            method="POST",
        )

        def _do_request() -> dict[str, Any]:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))

        try:
            res_data = await asyncio.to_thread(_do_request)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            transcript_text = res_data.get("text", "").strip()
            logger.info("Groq Whisper STT recognized: '%s' in %.2fms", transcript_text, elapsed_ms)
            return Transcript(
                text=transcript_text,
                is_final=True,
                confidence=0.95,
                language=self.language,
                latency_ms=elapsed_ms,
                provider=self.name,
            )
        except Exception as exc:
            logger.error("Groq Whisper transcription failed: %s", exc)
            raise RuntimeError(f"Cloud STT failed: {exc}") from exc
