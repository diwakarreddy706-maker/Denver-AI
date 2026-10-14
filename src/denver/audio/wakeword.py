"""Acoustic Wake-Word Detection Engine for Denver AI Assistant."""

from __future__ import annotations

import abc
import re
import time
from typing import Any, Sequence

from denver.audio.models import AudioChunk, WakeWordResult
from denver.logging.logger import get_logger

logger = get_logger("audio.wakeword")

DEFAULT_ACCEPTED_WAKE_PHRASES: tuple[str, ...] = (
    "denver",
    "hey denver",
    "denvar",
    "danver",
    "denber",
    "hay denver",
)


def check_strict_wake_phrase(
    transcript_text: str,
    accepted_phrases: Sequence[str] = DEFAULT_ACCEPTED_WAKE_PHRASES,
) -> tuple[bool, str, str]:
    """Strictly verify whether a transcript contains an accepted wake word.

    Returns:
        (is_valid, matched_phrase, trailing_command)
    """
    if not transcript_text:
        return False, "", ""
    raw = transcript_text.strip()
    if not raw:
        return False, "", ""

    # Sort phrases by word length descending so "hey denver" is matched before "denver"
    sorted_phrases = sorted(accepted_phrases, key=lambda p: len(p.split()), reverse=True)
    for phrase in sorted_phrases:
        p_clean = phrase.strip().lower()
        if not p_clean:
            continue
        words_pattern = r"[,\s]+".join(re.escape(w) for w in p_clean.split())
        pattern = rf"^(?:(?:oh|um|ah)\s+)?{words_pattern}\b[,\s]*(.*)$"
        m = re.match(pattern, raw, flags=re.IGNORECASE)
        if m:
            trailing = m.group(1).strip()
            trailing = re.sub(r"^[^\w]+", "", trailing).strip()
            return True, p_clean, trailing

    return False, "", ""


class WakeWordDetector(abc.ABC):
    """Abstract contract for streaming wake-word detection."""

    @abc.abstractmethod
    def process_chunk(self, chunk: AudioChunk) -> WakeWordResult:
        """Process streaming audio chunk and return wake detection result."""

    @abc.abstractmethod
    def reset(self) -> None:
        """Reset detector state and temporal buffers."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Detector engine name."""

    @property
    @abc.abstractmethod
    def detector_type(self) -> str:
        """Classifier type: 'trained', 'acoustic_fallback', 'fake'."""

    @property
    @abc.abstractmethod
    def is_available(self) -> bool:
        """Indicates whether the underlying model/engine is loaded and ready."""


class FallbackWakeWordDetector(WakeWordDetector):
    """Deterministic acoustic fallback wake-word detector with debounced cooldown.

    NOTE: This is an acoustic energy-pattern fallback and does not claim
    to be an acoustic neural model trained on the phonemes of 'Denver'.
    """

    def __init__(
        self,
        wake_word: str = "Denver",
        threshold: float = 0.5,
        cooldown_seconds: float = 1.5,
    ) -> None:
        self.wake_word = wake_word
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self._last_trigger_time = 0.0
        self._accumulated_energy = 0.0
        self._frame_count = 0

    @property
    def name(self) -> str:
        return "fallback_acoustic_detector"

    @property
    def detector_type(self) -> str:
        return "acoustic_fallback"

    @property
    def is_available(self) -> bool:
        return True

    def reset(self) -> None:
        self._accumulated_energy = 0.0
        self._frame_count = 0

    def trigger_wake(self) -> WakeWordResult:
        """Manually trigger wake-word activation (for push-to-talk or hotkey)."""
        now = time.time()
        self._last_trigger_time = now
        self.reset()
        return WakeWordResult(
            detected=True,
            wake_word=self.wake_word,
            confidence=1.0,
            audio_offset_ms=0.0,
            detector_type=self.detector_type,
        )

    def process_chunk(self, chunk: AudioChunk) -> WakeWordResult:
        """Process streaming frame with cooldown check."""
        now = time.time()
        if now - self._last_trigger_time < self.cooldown_seconds:
            return WakeWordResult(
                detected=False,
                wake_word=self.wake_word,
                confidence=0.0,
                detector_type=self.detector_type,
            )

        # Monitor sudden acoustic energy burst
        if chunk.energy >= self.threshold:
            self._frame_count += 1
            self._accumulated_energy += chunk.energy
            if self._frame_count >= 3:  # 150ms of sustained acoustic energy
                self._last_trigger_time = now
                confidence = min(1.0, self._accumulated_energy / 3.0)
                logger.info(
                    "FallbackWakeWordDetector energy gate fired: chunk_energy=%.4f, avg_energy=%.4f, score=%.4f, threshold=%.4f",
                    chunk.energy,
                    self._accumulated_energy / 3.0,
                    confidence,
                    self.threshold,
                )
                self.reset()
                return WakeWordResult(
                    detected=True,
                    wake_word=self.wake_word,
                    confidence=confidence,
                    audio_offset_ms=chunk.duration_ms,
                    detector_type=self.detector_type,
                )
        else:
            self._frame_count = max(0, self._frame_count - 1)

        return WakeWordResult(
            detected=False,
            wake_word=self.wake_word,
            confidence=0.0,
            detector_type=self.detector_type,
        )


class OpenWakeWordDetector(WakeWordDetector):
    """Neural acoustic wake-word engine backed by openWakeWord / ONNX."""

    def __init__(
        self,
        wake_word: str = "Denver",
        model_path: str | None = None,
        threshold: float = 0.5,
        cooldown_seconds: float = 1.0,
    ) -> None:
        self.wake_word = wake_word
        self.model_path = model_path
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self.fallback = FallbackWakeWordDetector(
            wake_word=wake_word,
            threshold=threshold,
            cooldown_seconds=cooldown_seconds,
        )
        self._model: Any = None
        self._init_engine()

    @property
    def name(self) -> str:
        return "openwakeword" if self._model else "openwakeword_fallback"

    @property
    def detector_type(self) -> str:
        return "trained" if self._model else "acoustic_fallback"

    @property
    def is_available(self) -> bool:
        return self._model is not None

    def _init_engine(self) -> None:
        if not self.model_path:
            return
        try:
            import openwakeword
            from openwakeword.model import Model
            self._model = Model(wakeword_models=[self.model_path], inference_framework="onnx")
            logger.info("openWakeWord model initialized from %s", self.model_path)
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("openWakeWord model not loaded: %s. Using acoustic fallback.", exc)
            self._model = None

    def reset(self) -> None:
        if self._model:
            try:
                self._model.reset()
            except Exception:  # pylint: disable=broad-except
                pass
        self.fallback.reset()

    def process_chunk(self, chunk: AudioChunk) -> WakeWordResult:
        if not self._model:
            return self.fallback.process_chunk(chunk)

        # If trained model is active, pass 16-bit PCM array to openWakeWord
        try:
            import numpy as np
            samples = np.frombuffer(chunk.data, dtype=np.int16)
            prediction = self._model.predict(samples)
            confidence = float(max(prediction.values()) if prediction else 0.0)
            if confidence >= self.threshold:
                self.reset()
                return WakeWordResult(
                    detected=True,
                    wake_word=self.wake_word,
                    confidence=confidence,
                    detector_type=self.detector_type,
                )
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("openWakeWord inference error: %s", exc)

        return WakeWordResult(detected=False, wake_word=self.wake_word, confidence=0.0, detector_type=self.detector_type)
