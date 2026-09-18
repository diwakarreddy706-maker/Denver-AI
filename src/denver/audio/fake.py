"""Deterministic fake implementations of all audio components for offline unit and integration testing."""

from __future__ import annotations

import asyncio
from typing import Any

from denver.audio.capture import AudioCapture
from denver.audio.models import (
    AudioChunk,
    AudioDevice,
    AudioFormat,
    Transcript,
    TTSRequest,
    TTSResult,
    VoiceActivity,
    VoiceActivityState,
    WakeWordResult,
)
from denver.audio.playback import AudioPlayback
from denver.audio.stt import SpeechToTextProvider
from denver.audio.tts import TextToSpeechProvider
from denver.audio.vad import VADEngine
from denver.audio.wakeword import WakeWordDetector


class FakeAudioCapture(AudioCapture):
    """Deterministic simulated audio capture allowing programmatic chunk injection."""

    def __init__(self, audio_format: AudioFormat | None = None) -> None:
        super().__init__(audio_format=audio_format or AudioFormat())
        self._is_capturing = False
        self.injected_chunks: list[AudioChunk] = []

    async def start(self) -> bool:
        self._is_capturing = True
        return True

    async def stop(self) -> None:
        self._is_capturing = False

    def inject_chunk(self, chunk: AudioChunk) -> None:
        """Add a synthetic audio chunk to the queue."""
        self._buffer.append(chunk)
        self._async_queue.put_nowait(chunk)

    def inject_synthetic_speech(self, duration_ms: float = 1000.0, energy: float = 0.08) -> list[AudioChunk]:
        """Generate and inject a sequence of speech frames."""
        chunks = []
        count = int(duration_ms // self.format.frame_duration_ms)
        sample_bytes = b"\x10\x00" * (self.format.chunk_size)  # Non-zero synthetic PCM
        for _ in range(count):
            c = AudioChunk(
                data=sample_bytes,
                sample_rate=self.format.sample_rate,
                channels=self.format.channels,
                duration_ms=self.format.frame_duration_ms,
                energy=energy,
            )
            self.inject_chunk(c)
            chunks.append(c)
        return chunks


class FakeVAD(VADEngine):
    """Deterministic fake VAD engine with programmable state sequence."""

    def __init__(self, default_state: VoiceActivityState = VoiceActivityState.SILENCE) -> None:
        self.default_state = default_state
        self.sequence: list[VoiceActivityState] = []
        self._index = 0

    @property
    def name(self) -> str:
        return "fake_vad"

    def set_sequence(self, states: list[VoiceActivityState]) -> None:
        self.sequence = list(states)
        self._index = 0

    def reset(self) -> None:
        self._index = 0

    def process_chunk(self, chunk: AudioChunk) -> VoiceActivity:
        if self.sequence and self._index < len(self.sequence):
            state = self.sequence[self._index]
            self._index += 1
        else:
            state = self.default_state

        is_speech = state in {VoiceActivityState.SPEECH_START, VoiceActivityState.SPEECH_ACTIVE}
        return VoiceActivity(
            state=state,
            confidence=1.0 if is_speech else 0.0,
            energy=chunk.energy,
            is_speech=is_speech,
        )


class FakeWakeWordDetector(WakeWordDetector):
    """Deterministic wake-word detector test double."""

    def __init__(self, wake_word: str = "Denver", should_detect: bool = False) -> None:
        self.wake_word = wake_word
        self.should_detect = should_detect
        self.call_count = 0

    @property
    def name(self) -> str:
        return "fake_wakeword"

    @property
    def detector_type(self) -> str:
        return "fake"

    @property
    def is_available(self) -> bool:
        return True

    def reset(self) -> None:
        self.call_count = 0

    def trigger(self) -> None:
        self.should_detect = True

    def process_chunk(self, chunk: AudioChunk) -> WakeWordResult:
        self.call_count += 1
        if self.should_detect:
            self.should_detect = False  # single-shot trigger
            return WakeWordResult(
                detected=True,
                wake_word=self.wake_word,
                confidence=1.0,
                detector_type=self.detector_type,
            )
        return WakeWordResult(
            detected=False,
            wake_word=self.wake_word,
            confidence=0.0,
            detector_type=self.detector_type,
        )


class FakeSTTProvider(SpeechToTextProvider):
    """Deterministic STT provider test double."""

    def __init__(self, canned_transcript: str = "Denver, what time is it?", should_fail: bool = False) -> None:
        self.canned_transcript = canned_transcript
        self.should_fail = should_fail
        self.transcribe_count = 0

    @property
    def name(self) -> str:
        return "fake_stt"

    @property
    def is_available(self) -> bool:
        return not self.should_fail

    async def transcribe(self, audio_bytes: bytes, audio_format: AudioFormat | None = None) -> Transcript:
        self.transcribe_count += 1
        if self.should_fail:
            raise RuntimeError("Fake STT simulated failure")

        return Transcript(
            text=self.canned_transcript,
            is_final=True,
            confidence=1.0,
            language="en",
            latency_ms=10.0,
            provider=self.name,
        )


class FakeTTSProvider(TextToSpeechProvider):
    """Deterministic TTS provider test double."""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.synthesize_count = 0
        self.last_request: TTSRequest | None = None

    @property
    def name(self) -> str:
        return "fake_tts"

    @property
    def is_available(self) -> bool:
        return not self.should_fail

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        self.synthesize_count += 1
        self.last_request = request
        if self.should_fail:
            return TTSResult(success=False, latency_ms=5.0, provider=self.name, error="Fake TTS failure")

        return TTSResult(
            success=True,
            audio_data=b"FAKE_WAV_AUDIO_BYTES",
            format="wav",
            sample_rate=16000,
            duration_seconds=0.5,
            latency_ms=5.0,
            provider=self.name,
        )


class FakeAudioPlayback(AudioPlayback):
    """Deterministic audio playback test double."""

    def __init__(self) -> None:
        super().__init__()
        self.play_count = 0
        self.played_payloads: list[bytes] = []

    async def play_bytes(self, audio_data: bytes, format: str = "wav", sample_rate: int = 24000) -> bool:
        self.play_count += 1
        self.played_payloads.append(audio_data)
        self._is_playing = True
        await asyncio.sleep(0.01)
        self._is_playing = False
        return True

    async def stop(self) -> None:
        self._is_playing = False
