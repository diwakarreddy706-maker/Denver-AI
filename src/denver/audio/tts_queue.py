"""Thread-safe and Async Priority TTS Queue with Barge-In and Interruption Support."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from denver.logging.logger import get_logger

logger = get_logger("audio.tts_queue")


class TTSPriority(str, Enum):
    HIGH = "HIGH"        # Direct voice response to user command (flushes lower priorities)
    NORMAL = "NORMAL"    # Routine notifications & scheduled briefings
    LOW = "LOW"          # Background telemetry alerts


@dataclass
class TTSQueueItem:
    text: str
    priority: TTSPriority = TTSPriority.NORMAL
    created_at: float = field(default_factory=time.time)


class DenverTTSQueue:
    """Non-blocking priority TTS Queue that sequences speech responses and handles user interruptions."""

    def __init__(
        self,
        playback_handler: Callable[[str], Coroutine[Any, Any, None]] | None = None,
        enabled: bool = True,
        max_size: int = 10,
    ) -> None:
        self.playback_handler = playback_handler
        self.enabled = enabled
        self.max_size = max_size
        self._high_queue: deque[str] = deque()
        self._normal_queue: deque[str] = deque()
        self._low_queue: deque[str] = deque()
        self._speaking = False
        self._interrupted = False
        self._lock = asyncio.Lock()
        self._current_task: asyncio.Task[Any] | None = None

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def pending_count(self) -> int:
        return len(self._high_queue) + len(self._normal_queue) + len(self._low_queue)

    def enqueue(self, text: str, priority: TTSPriority = TTSPriority.NORMAL) -> bool:
        """Enqueue a speech utterance into the appropriate priority queue."""
        clean = str(text).strip()
        if not self.enabled or not clean:
            return False

        if priority == TTSPriority.HIGH:
            # High priority flushes low priority queue to keep conversation snappy
            self._low_queue.clear()
            if len(self._high_queue) >= self.max_size:
                self._high_queue.popleft()
            self._high_queue.append(clean)
        elif priority == TTSPriority.NORMAL:
            if len(self._normal_queue) >= self.max_size:
                self._normal_queue.popleft()
            self._normal_queue.append(clean)
        else:
            if len(self._low_queue) >= self.max_size:
                self._low_queue.popleft()
            self._low_queue.append(clean)

        self._interrupted = False
        logger.debug("Enqueued TTS item [Priority=%s]: '%s' (Total pending: %d)", priority.value, clean[:40], self.pending_count())
        return True

    def clear(self) -> int:
        """Clear all pending utterances across all priority levels."""
        total = self.pending_count()
        self._high_queue.clear()
        self._normal_queue.clear()
        self._low_queue.clear()
        logger.debug("TTS queue cleared (%d items removed).", total)
        return total

    def interrupt(self) -> None:
        """Interrupt any ongoing playback and clear pending queues (e.g. on user barge-in)."""
        self._interrupted = True
        self.clear()
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
        self._speaking = False
        logger.info("TTS playback interrupted and queue cleared.")

    def pop_next(self) -> str | None:
        """Retrieve the highest priority next text to speak."""
        if self._high_queue:
            return self._high_queue.popleft()
        if self._normal_queue:
            return self._normal_queue.popleft()
        if self._low_queue:
            return self._low_queue.popleft()
        return None

    async def drain_next(self) -> bool:
        """Speak the next item in the queue asynchronously."""
        if not self.enabled or self._interrupted:
            return False

        text = self.pop_next()
        if not text:
            return False

        if not self.playback_handler:
            return True

        self._speaking = True
        try:
            res = self.playback_handler(text)
            if asyncio.iscoroutine(res):
                self._current_task = asyncio.create_task(res)
                await self._current_task
            return True
        except asyncio.CancelledError:
            logger.info("TTS drain cancelled due to interruption.")
            return False
        except Exception as exc:
            logger.error("TTS playback error in queue: %s", exc)
            return False
        finally:
            self._speaking = False
            self._current_task = None
