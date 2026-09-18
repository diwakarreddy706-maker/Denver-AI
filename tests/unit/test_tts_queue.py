"""Unit tests for Denver Priority TTS Audio Queue."""

from __future__ import annotations

import asyncio

import pytest

from denver.audio.tts_queue import DenverTTSQueue, TTSPriority


def test_tts_queue_enqueue_and_priority() -> None:
    queue = DenverTTSQueue(enabled=True)

    # Low priority
    queue.enqueue("Background update", priority=TTSPriority.LOW)
    # Normal priority
    queue.enqueue("Scheduled briefing", priority=TTSPriority.NORMAL)
    # High priority command response
    queue.enqueue("Command answered", priority=TTSPriority.HIGH)

    # High priority should pop first
    assert queue.pop_next() == "Command answered"
    # Normal priority should pop second
    assert queue.pop_next() == "Scheduled briefing"
    # Low priority was purged when high priority enqueued
    assert queue.pop_next() is None
    assert queue.pending_count() == 0


def test_tts_queue_disabled() -> None:
    queue = DenverTTSQueue(enabled=False)
    assert not queue.enqueue("Hello")
    assert queue.pending_count() == 0


def test_tts_queue_clear() -> None:
    queue = DenverTTSQueue(enabled=True)
    queue.enqueue("One", priority=TTSPriority.NORMAL)
    queue.enqueue("Two", priority=TTSPriority.NORMAL)
    assert queue.pending_count() == 2

    cleared = queue.clear()
    assert cleared == 2
    assert queue.pending_count() == 0


@pytest.mark.asyncio
async def test_tts_queue_drain_next() -> None:
    spoken = []

    async def fake_playback(text: str) -> None:
        spoken.append(text)

    queue = DenverTTSQueue(playback_handler=fake_playback, enabled=True)
    queue.enqueue("Hello world", priority=TTSPriority.HIGH)

    success = await queue.drain_next()
    assert success
    assert spoken == ["Hello world"]
    assert queue.pending_count() == 0


def test_tts_queue_interrupt() -> None:
    queue = DenverTTSQueue(enabled=True)
    queue.enqueue("Long announcement 1", priority=TTSPriority.NORMAL)
    queue.enqueue("Long announcement 2", priority=TTSPriority.NORMAL)

    queue.interrupt()
    assert queue.pending_count() == 0
    assert not queue.is_speaking
