"""Unit tests for Denver Pipeline Latency Telemetry."""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock

from denver.runtime.telemetry import PipelineLatencyMetrics, PipelineLatencyTracker, StageSpan


class TestPipelineLatencyTelemetry(unittest.TestCase):
    """Test suite for stage spans, tracker metrics, formatting, and event publication."""

    def test_stage_span_timing(self) -> None:
        span = StageSpan(name="stt")
        time.sleep(0.01)  # 10ms
        duration = span.finish()
        self.assertGreaterEqual(duration, 8.0)
        self.assertEqual(span.finish(), duration)  # Idempotent finish

    def test_pipeline_latency_tracker_workflow(self) -> None:
        event_bus = MagicMock()
        tracker = PipelineLatencyTracker(utterance="what is the time", event_bus=event_bus)

        tracker.start_stage("stt")
        time.sleep(0.005)
        tracker.end_stage("stt")

        tracker.start_stage("intent_routing")
        time.sleep(0.002)
        tracker.end_stage("intent_routing")

        tracker.start_stage("action_execution")
        time.sleep(0.002)
        tracker.end_stage("action_execution")

        tracker.start_stage("tts_synthesis")
        time.sleep(0.005)
        tracker.end_stage("tts_synthesis")

        metrics = tracker.finalize(intent="get_time")

        self.assertGreater(metrics.stt_ms, 0)
        self.assertGreater(metrics.intent_routing_ms, 0)
        self.assertGreater(metrics.action_execution_ms, 0)
        self.assertGreater(metrics.tts_synthesis_ms, 0)
        self.assertGreater(metrics.total_ms, 0)
        self.assertEqual(metrics.intent, "get_time")
        self.assertEqual(metrics.utterance, "what is the time")

        log_str = metrics.format_log()
        self.assertIn("[LATENCY]", log_str)
        self.assertIn("STT:", log_str)
        self.assertIn("Route:", log_str)
        self.assertIn("Exec:", log_str)
        self.assertIn("TTS:", log_str)

        # Confirm event was published to event bus
        event_bus.publish.assert_called_once()
        call_args = event_bus.publish.call_args[0]
        self.assertEqual(call_args[0], "pipeline.latency")
        self.assertEqual(call_args[1]["intent"], "get_time")


if __name__ == "__main__":
    unittest.main()
