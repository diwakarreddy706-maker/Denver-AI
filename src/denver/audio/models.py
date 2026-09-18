"""Typed data models and contracts for Denver Voice & Audio Engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Any


@unique
class AudioDeviceType(str, Enum):
    """Classification of audio endpoints."""

    INPUT = "input"
    OUTPUT = "output"


@dataclass(frozen=True)
class AudioDevice:
    """Hardware audio endpoint discovery representation."""

    index: int
    name: str
    channels: int
    default_samplerate: int = 16000
    is_input: bool = False
    is_output: bool = False
    is_default: bool = False
    host_api: str = "WASAPI"

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "channels": self.channels,
            "sample_rate": self.default_samplerate,
            "is_input": self.is_input,
            "is_output": self.is_output,
            "is_default": self.is_default,
            "host_api": self.host_api,
        }


@dataclass(frozen=True)
class AudioFormat:
    """Standardized audio encoding format for Denver Voice Engine."""

    sample_rate: int = 16000
    channels: int = 1
    sample_width: int = 2  # 16-bit signed integer PCM
    chunk_size: int = 800  # 50ms at 16kHz (800 samples)

    @property
    def bytes_per_sample(self) -> int:
        return self.sample_width * self.channels

    @property
    def chunk_bytes(self) -> int:
        return self.chunk_size * self.bytes_per_sample

    @property
    def frame_duration_ms(self) -> float:
        return (self.chunk_size / self.sample_rate) * 1000.0


@dataclass
class AudioChunk:
    """A discrete temporal frame of raw PCM audio data."""

    data: bytes
    sample_rate: int = 16000
    channels: int = 1
    sample_width: int = 2
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 50.0
    energy: float = 0.0

    @property
    def sample_count(self) -> int:
        return len(self.data) // (self.sample_width * self.channels)


@unique
class VoiceActivityState(str, Enum):
    """State of voice activity detection for a frame."""

    SILENCE = "SILENCE"
    SPEECH_START = "SPEECH_START"
    SPEECH_ACTIVE = "SPEECH_ACTIVE"
    SPEECH_END = "SPEECH_END"


@dataclass(frozen=True)
class VoiceActivity:
    """Voice activity detection result for a chunk/utterance."""

    state: VoiceActivityState
    confidence: float = 0.0
    energy: float = 0.0
    is_speech: bool = False
    speech_duration_ms: float = 0.0
    silence_duration_ms: float = 0.0


@dataclass(frozen=True)
class WakeWordResult:
    """Result of an acoustic wake-word matching pass."""

    detected: bool
    wake_word: str = "Denver"
    confidence: float = 0.0
    audio_offset_ms: float = 0.0
    detector_type: str = "acoustic"  # acoustic, trained, deterministic, fake


@dataclass(frozen=True)
class Transcript:
    """Recognized text transcript output produced by an STT engine."""

    text: str
    is_final: bool = True
    confidence: float = 1.0
    language: str = "en"
    latency_ms: float = 0.0
    provider: str = "whisper"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "is_final": self.is_final,
            "confidence": self.confidence,
            "language": self.language,
            "latency_ms": self.latency_ms,
            "provider": self.provider,
        }


@dataclass
class SpeechResult:
    """End-to-end result of a speech recognition capture session."""

    success: bool
    transcript: str = ""
    duration_seconds: float = 0.0
    audio_bytes: bytes = b""
    confidence: float = 1.0
    error: str | None = None


@dataclass(frozen=True)
class TTSRequest:
    """Request to synthesize audio from text."""

    text: str
    voice: str = "en-GB-RyanNeural"
    rate: str = "+0%"
    volume: str = "+0%"
    pitch: str = "+0Hz"


@dataclass
class TTSResult:
    """Output generated from text-to-speech synthesis."""

    success: bool
    audio_data: bytes = b""
    format: str = "mp3"  # mp3, wav, pcm
    sample_rate: int = 24000
    duration_seconds: float = 0.0
    latency_ms: float = 0.0
    provider: str = "edge"
    error: str | None = None


@dataclass
class AudioPipelineStatus:
    """Comprehensive diagnostic status of the entire audio engine."""

    status: str = "READY"  # READY, DEGRADED, NOT_CONFIGURED, UNAVAILABLE, ERROR
    capture_active: bool = False
    vad_active: bool = False
    wakeword_active: bool = False
    stt_active: bool = False
    tts_active: bool = False
    playback_active: bool = False
    devices: dict[str, str] = field(default_factory=dict)
    components: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "capture_active": self.capture_active,
            "vad_active": self.vad_active,
            "wakeword_active": self.wakeword_active,
            "stt_active": self.stt_active,
            "tts_active": self.tts_active,
            "playback_active": self.playback_active,
            "devices": self.devices,
            "components": self.components,
        }
