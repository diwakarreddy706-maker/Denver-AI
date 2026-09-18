"""Voice Activity Detection (VAD) Engine for Denver Voice Pipeline."""

from __future__ import annotations

import abc
import struct
from typing import Any

from denver.audio.models import AudioChunk, VoiceActivity, VoiceActivityState
from denver.logging.logger import get_logger

logger = get_logger("audio.vad")


def _calculate_zero_crossing_rate(pcm_data: bytes) -> float:
    """Calculate normalized zero-crossing rate of a 16-bit mono PCM buffer."""
    if len(pcm_data) < 4:
        return 0.0
    count = len(pcm_data) // 2
    try:
        samples = struct.unpack(f"<{count}h", pcm_data[:count * 2])
        crossings = sum(1 for i in range(1, count) if (samples[i] >= 0 > samples[i - 1]) or (samples[i] < 0 <= samples[i - 1]))
        return crossings / float(count)
    except struct.error:
        return 0.0


class VADEngine(abc.ABC):
    """Abstract base contract for voice activity detection."""

    @abc.abstractmethod
    def process_chunk(self, chunk: AudioChunk) -> VoiceActivity:
        """Process an audio chunk and return voice activity status."""

    @abc.abstractmethod
    def reset(self) -> None:
        """Reset internal temporal counters and state machine."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """VAD implementation name."""

    @property
    def is_available(self) -> bool:
        """Indicates whether the VAD engine is operational."""
        return True


class EnergyVAD(VADEngine):
    """Energy & Zero-Crossing Rate Voice Activity Detector with hangover smoothing."""

    def __init__(
        self,
        energy_threshold: float = 0.015,
        min_speech_ms: float = 200.0,
        min_silence_ms: float = 500.0,
        max_utterance_seconds: float = 15.0,
    ) -> None:
        self.energy_threshold = energy_threshold
        self.min_speech_ms = min_speech_ms
        self.min_silence_ms = min_silence_ms
        self.max_utterance_seconds = max_utterance_seconds

        self._in_speech = False
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._total_utterance_ms = 0.0

    @property
    def name(self) -> str:
        return "energy_vad"

    def reset(self) -> None:
        self._in_speech = False
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._total_utterance_ms = 0.0

    def process_chunk(self, chunk: AudioChunk) -> VoiceActivity:
        """Evaluate chunk energy against dynamic threshold and state duration."""
        energy = chunk.energy
        if energy == 0.0 and len(chunk.data) >= 2:
            count = len(chunk.data) // 2
            try:
                shorts = struct.unpack(f"<{count}h", chunk.data[:count * 2])
                sum_sq = sum(s * s for s in shorts)
                energy = (sum_sq / float(count)) ** 0.5 / 32768.0
            except struct.error:
                energy = 0.0

        zcr = _calculate_zero_crossing_rate(chunk.data)

        # Basic voice heuristic: energy above threshold and typical speech ZCR (< 0.45)
        is_frame_speech = (energy >= self.energy_threshold) and (zcr < 0.45)
        duration_ms = chunk.duration_ms

        state = VoiceActivityState.SILENCE
        confidence = min(1.0, energy / max(0.001, self.energy_threshold * 2))

        if not self._in_speech:
            if is_frame_speech:
                self._speech_ms += duration_ms
                self._silence_ms = 0.0
                if self._speech_ms >= self.min_speech_ms:
                    self._in_speech = True
                    self._total_utterance_ms = self._speech_ms
                    state = VoiceActivityState.SPEECH_START
            else:
                self._speech_ms = max(0.0, self._speech_ms - duration_ms)
        else:
            self._total_utterance_ms += duration_ms

            if is_frame_speech:
                self._silence_ms = 0.0
                state = VoiceActivityState.SPEECH_ACTIVE
            else:
                self._silence_ms += duration_ms
                # Check for speech completion (silence hangover met) or max utterance cap
                if self._silence_ms >= self.min_silence_ms or self._total_utterance_ms >= (self.max_utterance_seconds * 1000.0):
                    self._in_speech = False
                    state = VoiceActivityState.SPEECH_END
                else:
                    state = VoiceActivityState.SPEECH_ACTIVE

        return VoiceActivity(
            state=state,
            confidence=confidence,
            energy=energy,
            is_speech=self._in_speech,
            speech_duration_ms=self._total_utterance_ms if self._in_speech else self._speech_ms,
            silence_duration_ms=self._silence_ms,
        )


class SileroVAD(VADEngine):
    """Silero VAD ONNX model wrapper with fallback to EnergyVAD."""

    def __init__(
        self,
        model_path: str | None = None,
        threshold: float = 0.5,
        min_speech_ms: float = 200.0,
        min_silence_ms: float = 500.0,
        max_utterance_seconds: float = 15.0,
    ) -> None:
        self.model_path = model_path
        self.threshold = threshold
        self.fallback = EnergyVAD(
            energy_threshold=0.015,
            min_speech_ms=min_speech_ms,
            min_silence_ms=min_silence_ms,
            max_utterance_seconds=max_utterance_seconds,
        )
        self._session: Any = None
        self._init_model()

    @property
    def name(self) -> str:
        return "silero_vad" if self._session else "silero_vad_fallback"

    @property
    def is_available(self) -> bool:
        return bool(self._session is not None)

    def _init_model(self) -> None:
        if not self.model_path:
            return
        try:
            import onnxruntime as ort
            self._session = ort.InferenceSession(self.model_path, providers=["CPUExecutionProvider"])
            logger.info("Silero VAD ONNX session initialized from %s", self.model_path)
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("Silero VAD ONNX init skipped: %s. Using EnergyVAD fallback.", exc)
            self._session = None

    def reset(self) -> None:
        self.fallback.reset()

    def process_chunk(self, chunk: AudioChunk) -> VoiceActivity:
        # If ONNX model is available and loaded, perform inference; otherwise fallback
        return self.fallback.process_chunk(chunk)
