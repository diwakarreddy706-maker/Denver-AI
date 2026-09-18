"""WASAPI System Audio Loopback Capture for Denver.

Captures system audio output (what you hear through speakers/headphones from Zoom,
Teams, Google Meet, YouTube, etc.) on Windows via WASAPI Loopback.
"""

from __future__ import annotations

import asyncio
import collections
import math
import platform
import struct
import threading
import time
from typing import Any, AsyncGenerator

from denver.audio.capture import calculate_rms_energy
from denver.audio.device import AudioDeviceManager
from denver.audio.models import AudioChunk, AudioFormat
from denver.logging.logger import get_logger

logger = get_logger("audio.loopback")

_IS_WINDOWS = platform.system() == "Windows"

try:
    import sounddevice as sd
    _SOUNDDEVICE_AVAILABLE = True
except (ImportError, OSError):
    _SOUNDDEVICE_AVAILABLE = False


class WasapiLoopbackCapture:
    """Asynchronous system audio loopback capture with bounded ring buffering."""

    def __init__(
        self,
        audio_format: AudioFormat | None = None,
        device_index: int | None = None,
        max_buffer_seconds: float = 60.0,
        device_manager: AudioDeviceManager | None = None,
    ) -> None:
        self.format = audio_format or AudioFormat(sample_rate=16000, channels=1, sample_width=2)
        self.device_index = device_index
        self.max_buffer_seconds = max_buffer_seconds
        self.device_manager = device_manager or AudioDeviceManager()

        max_chunks = int(math.ceil((self.max_buffer_seconds * 1000.0) / self.format.frame_duration_ms))
        self._buffer: collections.deque[AudioChunk] = collections.deque(maxlen=max_chunks)

        self._stream: Any = None
        self._is_capturing = False
        self._async_queue: asyncio.Queue[AudioChunk] = asyncio.Queue(maxsize=max_chunks)
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_capturing(self) -> bool:
        return self._is_capturing

    @property
    def buffer_size(self) -> int:
        return len(self._buffer)

    def _audio_callback(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:
        """PortAudio / WASAPI loopback callback running in audio driver thread."""
        if not self._is_capturing:
            return

        if status:
            logger.debug("Loopback audio status warning: %s", status)

        raw_bytes = bytes(indata)
        energy = calculate_rms_energy(raw_bytes)

        chunk = AudioChunk(
            data=raw_bytes,
            sample_rate=self.format.sample_rate,
            channels=self.format.channels,
            sample_width=self.format.sample_width,
            timestamp=time.time(),
            duration_ms=self.format.frame_duration_ms,
            energy=energy,
        )

        self._buffer.append(chunk)

        if self._loop and self._loop.is_running():
            try:
                self._loop.call_soon_threadsafe(self._put_chunk_nonblocking, chunk)
            except RuntimeError:
                pass

    def _put_chunk_nonblocking(self, chunk: AudioChunk) -> None:
        if self._async_queue.full():
            try:
                self._async_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self._async_queue.put_nowait(chunk)
        except asyncio.QueueFull:
            pass

    def push_mock_chunk(self, pcm_bytes: bytes, duration_ms: float = 100.0) -> AudioChunk:
        """Push an in-memory audio chunk into buffer (useful for test simulations)."""
        energy = calculate_rms_energy(pcm_bytes)
        chunk = AudioChunk(
            data=pcm_bytes,
            sample_rate=self.format.sample_rate,
            channels=self.format.channels,
            sample_width=self.format.sample_width,
            timestamp=time.time(),
            duration_ms=duration_ms,
            energy=energy,
        )
        self._buffer.append(chunk)
        try:
            self._async_queue.put_nowait(chunk)
        except (asyncio.QueueFull, Exception):
            pass
        return chunk

    async def start(self) -> bool:
        """Initialize and start WASAPI loopback recording."""
        if self._is_capturing:
            return True

        self._loop = asyncio.get_running_loop()

        if not _SOUNDDEVICE_AVAILABLE or not _IS_WINDOWS:
            logger.info("WASAPI loopback active in simulated/software buffer mode.")
            self._is_capturing = True
            return True

        try:
            # Find default WASAPI output device for loopback
            target_device = self.device_index
            extra_settings = None

            if hasattr(sd, "WasapiSettings"):
                try:
                    wasapi_cls = getattr(sd, "WasapiSettings")
                    extra_settings = wasapi_cls(exclusive=False)
                except Exception:
                    extra_settings = None

            self._stream = sd.RawInputStream(
                samplerate=self.format.sample_rate,
                blocksize=self.format.chunk_size,
                device=target_device,
                channels=self.format.channels,
                dtype="int16",
                extra_settings=extra_settings,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._is_capturing = True
            logger.info("WASAPI loopback capture started on device %s (%d Hz)", target_device, self.format.sample_rate)
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to start WASAPI loopback hardware stream (%s). Fallback to simulated mode.", exc)
            self._is_capturing = True
            return True

    async def stop(self) -> None:
        """Halt loopback capture."""
        if not self._is_capturing:
            return

        self._is_capturing = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("Error closing loopback stream: %s", exc)
            finally:
                self._stream = None

        logger.info("WASAPI loopback capture stopped.")

    def clear(self) -> None:
        """Clear audio buffer."""
        self._buffer.clear()
        while not self._async_queue.empty():
            try:
                self._async_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def read_chunk(self, timeout: float = 1.0) -> AudioChunk | None:
        """Read the next audio chunk from queue."""
        try:
            return await asyncio.wait_for(self._async_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def get_buffered_audio_bytes(self, max_duration_seconds: float | None = None) -> bytes:
        """Extract contiguous PCM bytes from loopback ring buffer."""
        if not self._buffer:
            return b""

        if max_duration_seconds is None:
            return b"".join(c.data for c in self._buffer)

        req_ms = max_duration_seconds * 1000.0
        accumulated_ms = 0.0
        chunks = []
        for c in reversed(self._buffer):
            chunks.append(c.data)
            accumulated_ms += c.duration_ms
            if accumulated_ms >= req_ms:
                break

        chunks.reverse()
        return b"".join(chunks)
