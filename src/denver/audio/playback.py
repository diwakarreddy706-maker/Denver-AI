"""Asynchronous speaker audio playback with barge-in interruption support."""

from __future__ import annotations

import asyncio
import io
import numpy as np
import threading
import time
from typing import Any

from denver.audio.device import AudioDeviceManager
from denver.audio.models import TTSResult
from denver.logging.logger import get_logger

logger = get_logger("audio.playback")

try:
    import sounddevice as sd
    _SOUNDDEVICE_AVAILABLE = True
except (ImportError, OSError):
    _SOUNDDEVICE_AVAILABLE = False

try:
    import winsound
    _WINSOUND_AVAILABLE = True
except ImportError:
    _WINSOUND_AVAILABLE = False


class AudioPlayback:
    """Manages asynchronous audio playback to speakers with instant barge-in interruption."""

    def __init__(
        self,
        device_index: int | None = None,
        device_manager: AudioDeviceManager | None = None,
    ) -> None:
        self.device_index = device_index
        self.device_manager = device_manager or AudioDeviceManager()
        self._is_playing = False
        self._playback_lock = asyncio.Lock()
        self._stop_event = threading.Event()
        self._current_task: asyncio.Task[Any] | None = None

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    async def play_listening_chime(self) -> None:
        """Play a subtle, pleasant 70ms synthetic chime when wake-word is detected."""
        if not _SOUNDDEVICE_AVAILABLE:
            return
        def _chime():
            try:
                fs = 24000
                t = np.linspace(0, 0.07, int(fs * 0.07), endpoint=False)
                tone = 0.08 * np.sin(2 * np.pi * 880 * t) + 0.06 * np.sin(2 * np.pi * 1320 * t)
                env = np.exp(-t * 25)
                audio = (tone * env).astype(np.float32)
                sd.play(audio, fs)
            except Exception:
                pass
        asyncio.create_task(asyncio.to_thread(_chime))

    async def play_bytes(self, audio_data: bytes, format: str = "wav", sample_rate: int = 24000) -> bool:
        """Play synthesized audio bytes asynchronously to output speakers."""
        if not audio_data:
            return False

        async with self._playback_lock:
            self._is_playing = True
            self._stop_event.clear()

            dev = self.device_manager.get_device_by_name_or_index(self.device_index, is_input=False)
            logger.info("Starting audio playback (Format: %s, Size: %d bytes)...", format, len(audio_data))

            try:
                # 1. Sounddevice playback for WAV and MP3
                if _SOUNDDEVICE_AVAILABLE:
                    def _play_sd():
                        try:
                            import soundfile as sf
                            data, fs = sf.read(io.BytesIO(audio_data), dtype="float32")
                            sd.play(data, fs, device=dev.index if dev else None)
                            while sd.get_stream() and sd.get_stream().active:
                                if self._stop_event.is_set():
                                    sd.stop()
                                    break
                                time.sleep(0.05)
                        except Exception as e:
                            logger.debug("Soundfile decode failed, attempting miniaudio fallback: %s", e)
                            try:
                                import miniaudio
                                decoded = miniaudio.decode(audio_data)
                                samples = np.frombuffer(decoded.samples, dtype=np.int16).astype(np.float32) / 32768.0
                                if decoded.nchannels > 1:
                                    samples = samples.reshape(-1, decoded.nchannels)
                                sd.play(samples, decoded.sample_rate, device=dev.index if dev else None)
                                while sd.get_stream() and sd.get_stream().active:
                                    if self._stop_event.is_set():
                                        sd.stop()
                                        break
                                    time.sleep(0.05)
                            except Exception as e2:
                                logger.debug("Miniaudio playback fallback failed: %s", e2)

                    await asyncio.to_thread(_play_sd)

                # 2. Winsound fallback for Windows WAV
                elif _WINSOUND_AVAILABLE and format == "wav":
                    def _play_winsound():
                        try:
                            winsound.PlaySound(audio_data, winsound.SND_MEMORY)
                        except Exception as e:
                            logger.debug("Winsound playback error: %s", e)

                    await asyncio.to_thread(_play_winsound)

                # 3. Simulated sleep fallback if audio engine unavailable
                else:
                    duration = min(3.0, max(0.1, len(audio_data) / 16000.0))
                    for _ in range(int(duration * 20)):
                        if self._stop_event.is_set():
                            logger.debug("Playback interrupted by barge-in event.")
                            break
                        await asyncio.sleep(0.05)

                return not self._stop_event.is_set()

            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Audio playback error: %s", exc)
                return False
            finally:
                self._is_playing = False

    async def stop(self) -> None:
        """Immediately halt active playback (barge-in interruption)."""
        if not self._is_playing:
            return

        logger.info("Halting active speaker playback (barge-in requested)...")
        self._stop_event.set()

        if _SOUNDDEVICE_AVAILABLE:
            try:
                sd.stop()
            except Exception:  # pylint: disable=broad-except
                pass

        if _WINSOUND_AVAILABLE:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:  # pylint: disable=broad-except
                pass

        self._is_playing = False
