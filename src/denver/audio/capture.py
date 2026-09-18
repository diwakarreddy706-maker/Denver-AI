"""Asynchronous microphone audio capture with bounded ring buffering."""

from __future__ import annotations

import asyncio
import collections
import math
import struct
import threading
import time
from typing import Any, AsyncGenerator

from denver.audio.device import AudioDeviceManager
from denver.audio.models import AudioChunk, AudioFormat
from denver.logging.logger import get_logger

logger = get_logger("audio.capture")

try:
    import sounddevice as sd
    _SOUNDDEVICE_AVAILABLE = True
except (ImportError, OSError):
    _SOUNDDEVICE_AVAILABLE = False


def calculate_rms_energy(pcm_data: bytes) -> float:
    """Compute Root Mean Square (RMS) energy normalized between 0.0 and 1.0."""
    if not pcm_data or len(pcm_data) < 2:
        return 0.0

    count = len(pcm_data) // 2
    format_str = f"<{count}h"
    try:
        samples = struct.unpack(format_str, pcm_data[:count * 2])
        sum_sq = sum(float(s * s) for s in samples)
        rms = math.sqrt(sum_sq / count)
        # Normalize 16-bit signed integer range (0 to 32768)
        return min(1.0, rms / 32768.0)
    except struct.error:
        return 0.0


class AudioCapture:
    """Asynchronous microphone streaming capture with bounded memory ring buffer."""

    def __init__(
        self,
        audio_format: AudioFormat | None = None,
        device_index: int | None = None,
        max_buffer_seconds: float = 10.0,
        device_manager: AudioDeviceManager | None = None,
    ) -> None:
        self.format = audio_format or AudioFormat()
        self.device_index = device_index
        self.max_buffer_seconds = max_buffer_seconds
        self.device_manager = device_manager or AudioDeviceManager()

        # Maximum chunks in ring buffer to guarantee memory bound
        max_chunks = int(math.ceil((self.max_buffer_seconds * 1000.0) / self.format.frame_duration_ms))
        self._buffer: collections.deque[AudioChunk] = collections.deque(maxlen=max_chunks)

        self._stream: Any = None
        self._is_capturing = False
        self._thread: threading.Thread | None = None
        self._async_queue: asyncio.Queue[AudioChunk] = asyncio.Queue(maxsize=max_chunks)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._noise_floor = 0.01

    @property
    def is_capturing(self) -> bool:
        return self._is_capturing

    @property
    def buffer_size(self) -> int:
        return len(self._buffer)

    @property
    def noise_floor(self) -> float:
        return self._noise_floor

    def _enqueue_chunk(self, chunk: AudioChunk) -> None:
        """Internal helper to enqueue a chunk into the buffer and async queue."""
        self._buffer.append(chunk)
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._safe_put, chunk)
        else:
            try:
                self._async_queue.put_nowait(chunk)
            except (asyncio.QueueFull, Exception):
                pass

    def _audio_callback(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:
        """PortAudio callback running in audio driver thread."""
        if not self._is_capturing:
            return

        if status:
            logger.debug("Audio capture status warning: %s", status)

        # Raw bytes from numpy buffer
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

        # Dispatch to async queue safely
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

    async def start(self) -> bool:
        """Start capturing audio from the input device asynchronously."""
        if self._is_capturing:
            return True

        self._loop = asyncio.get_running_loop()
        dev = self.device_manager.get_device_by_name_or_index(self.device_index, is_input=True)
        if not dev:
            logger.warning("No audio input device found.")
            return False

        if not _SOUNDDEVICE_AVAILABLE:
            logger.warning("sounddevice is not available. Audio capture running in simulated/passive mode.")
            self._is_capturing = True
            return True

        try:
            self._stream = sd.RawInputStream(
                samplerate=self.format.sample_rate,
                blocksize=self.format.chunk_size,
                device=dev.index,
                channels=self.format.channels,
                dtype="int16",
                callback=self._audio_callback,
            )
            self._stream.start()
            self._is_capturing = True
            logger.info("Microphone capture started on '%s' (%d Hz)", dev.name, self.format.sample_rate)
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to open audio input stream: %s", exc)
            self._is_capturing = False
            return False

    async def stop(self) -> None:
        """Halt microphone capture and release hardware resources."""
        if not self._is_capturing:
            return

        self._is_capturing = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("Error closing audio stream: %s", exc)
            finally:
                self._stream = None

        logger.info("Microphone capture stopped.")

    def clear(self) -> None:
        """Flush in-memory buffers to prevent stale audio carryover."""
        self._buffer.clear()
        while not self._async_queue.empty():
            try:
                self._async_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def read_chunk(self, timeout: float = 1.0) -> AudioChunk | None:
        """Read the next temporal audio chunk from the streaming queue."""
        try:
            return await asyncio.wait_for(self._async_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def stream_chunks(self) -> AsyncGenerator[AudioChunk, None]:
        """Yield real-time stream of audio chunks until capture is stopped."""
        while self._is_capturing:
            chunk = await self.read_chunk(timeout=0.2)
            if chunk is not None:
                yield chunk

    def get_buffered_audio_bytes(self, max_duration_seconds: float | None = None) -> bytes:
        """Extract contiguous PCM bytes from the in-memory ring buffer."""
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

    async def calibrate_noise_floor(self, duration_seconds: float = 0.5) -> float:
        """Measure background ambient noise floor to establish dynamic energy baseline."""
        if not self._is_capturing:
            return self._noise_floor

        samples = []
        start = time.time()
        while time.time() - start < duration_seconds:
            chunk = await self.read_chunk(timeout=0.1)
            if chunk:
                samples.append(chunk.energy)

        if samples:
            self._noise_floor = sum(samples) / len(samples)
            logger.debug("Calibrated noise floor baseline: %.4f", self._noise_floor)

        return self._noise_floor
