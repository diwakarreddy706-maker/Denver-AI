"""Per-Stage Voice & Command Pipeline Latency Telemetry for Denver AI Assistant."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from denver.logging.logger import get_logger

logger = get_logger("runtime.telemetry")


@dataclass
class StageSpan:
    """Represents a single timed stage in the execution pipeline."""
    name: str
    start_time: float = field(default_factory=time.perf_counter)
    end_time: float | None = None
    duration_ms: float = 0.0

    def finish(self) -> float:
        """Mark the end of this stage and compute duration in milliseconds."""
        if self.end_time is None:
            self.end_time = time.perf_counter()
            self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        return self.duration_ms


@dataclass
class PipelineLatencyMetrics:
    """Comprehensive latency breakdown across all pipeline stages."""
    stt_ms: float = 0.0
    intent_routing_ms: float = 0.0
    action_execution_ms: float = 0.0
    tts_synthesis_ms: float = 0.0
    total_ms: float = 0.0
    utterance: str = ""
    intent: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stt_ms": self.stt_ms,
            "intent_routing_ms": self.intent_routing_ms,
            "action_execution_ms": self.action_execution_ms,
            "tts_synthesis_ms": self.tts_synthesis_ms,
            "total_ms": self.total_ms,
            "utterance": self.utterance,
            "intent": self.intent,
        }

    def format_log(self) -> str:
        """Format a crisp single-line telemetry log."""
        return (
            f"[LATENCY] STT: {self.stt_ms:.1f}ms | "
            f"Route: {self.intent_routing_ms:.1f}ms | "
            f"Exec: {self.action_execution_ms:.1f}ms | "
            f"TTS: {self.tts_synthesis_ms:.1f}ms | "
            f"Total: {self.total_ms:.1f}ms"
        )


class PipelineLatencyTracker:
    """Tracks latency across multiple stages for a single interaction turn."""

    def __init__(self, utterance: str = "", event_bus: Any | None = None) -> None:
        self.utterance = utterance
        self.event_bus = event_bus
        self.start_time = time.perf_counter()
        self._spans: dict[str, StageSpan] = {}
        self._metrics: PipelineLatencyMetrics | None = None

    def start_stage(self, name: str) -> StageSpan:
        """Begin timing a named stage."""
        span = StageSpan(name=name)
        self._spans[name] = span
        return span

    def end_stage(self, name: str) -> float:
        """End timing for a named stage and return duration in ms."""
        span = self._spans.get(name)
        if span:
            return span.finish()
        return 0.0

    def finalize(self, intent: str = "") -> PipelineLatencyMetrics:
        """Complete all open stages, compute total pipeline latency, and log/emit telemetry."""
        for span in self._spans.values():
            if span.end_time is None:
                span.finish()

        total_ms = round((time.perf_counter() - self.start_time) * 1000, 2)
        metrics = PipelineLatencyMetrics(
            stt_ms=self._spans.get("stt", StageSpan("stt", duration_ms=0.0)).duration_ms,
            intent_routing_ms=self._spans.get("intent_routing", StageSpan("intent_routing", duration_ms=0.0)).duration_ms,
            action_execution_ms=self._spans.get("action_execution", StageSpan("action_execution", duration_ms=0.0)).duration_ms,
            tts_synthesis_ms=self._spans.get("tts_synthesis", StageSpan("tts_synthesis", duration_ms=0.0)).duration_ms,
            total_ms=total_ms,
            utterance=self.utterance,
            intent=intent,
        )
        self._metrics = metrics
        logger.info(metrics.format_log())

        if self.event_bus and hasattr(self.event_bus, "publish"):
            try:
                import asyncio
                # If event bus has async publish
                res = self.event_bus.publish("pipeline.latency", metrics.to_dict())
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception as exc:
                logger.debug("Failed publishing telemetry event: %s", exc)

        return metrics
