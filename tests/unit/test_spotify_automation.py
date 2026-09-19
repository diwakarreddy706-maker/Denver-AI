"""Unit tests for Spotify Voice Controller & Media Key Automation subsystem."""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import MagicMock, patch

from denver.automation.spotify import (
    SpotifyController,
    VK_MEDIA_NEXT_TRACK,
    VK_MEDIA_PLAY_PAUSE,
    VK_MEDIA_PREV_TRACK,
)
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.memory.memory_service import MemoryService
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.events import SpotifyPlaybackChanged


class TestSpotifyRouter(unittest.TestCase):
    """Test suite for IntentRouter Spotify & media voice phrase matching."""

    def setUp(self) -> None:
        self.router = IntentRouter()

    def test_play_music(self) -> None:
        intent = self.router.route("play music")
        self.assertEqual(intent.intent_name, "spotify_play_pause")

    def test_play_spotify(self) -> None:
        intent = self.router.route("play spotify")
        self.assertEqual(intent.intent_name, "spotify_play_pause")

    def test_pause_music(self) -> None:
        intent = self.router.route("pause music")
        self.assertEqual(intent.intent_name, "spotify_play_pause")

    def test_resume_music(self) -> None:
        intent = self.router.route("resume music")
        self.assertEqual(intent.intent_name, "spotify_play_pause")

    def test_next_song(self) -> None:
        intent = self.router.route("next song")
        self.assertEqual(intent.intent_name, "spotify_next_track")

    def test_skip_track(self) -> None:
        intent = self.router.route("skip track")
        self.assertEqual(intent.intent_name, "spotify_next_track")

    def test_previous_song(self) -> None:
        intent = self.router.route("previous song")
        self.assertEqual(intent.intent_name, "spotify_previous_track")

    def test_prev_track(self) -> None:
        intent = self.router.route("prev track")
        self.assertEqual(intent.intent_name, "spotify_previous_track")

    def test_play_song_on_spotify(self) -> None:
        intent = self.router.route("play Starboy on spotify")
        self.assertEqual(intent.intent_name, "spotify_play_query")
        self.assertEqual(intent.params.get("query"), "Starboy")

    def test_search_spotify_for(self) -> None:
        intent = self.router.route("search spotify for Daft Punk")
        self.assertEqual(intent.intent_name, "spotify_play_query")
        self.assertEqual(intent.params.get("query"), "Daft Punk")


class TestSpotifyController(unittest.TestCase):
    """Test suite for SpotifyController media key execution and URI formatting."""

    def setUp(self) -> None:
        self.controller = SpotifyController()

    def test_play_pause_mock(self) -> None:
        res = self.controller.play_pause(is_mock=True)
        self.assertTrue(res.success)
        self.assertEqual(res.action, "spotify_play_pause")
        self.assertTrue(res.data.get("mock"))

    def test_next_track_mock(self) -> None:
        res = self.controller.next_track(is_mock=True)
        self.assertTrue(res.success)
        self.assertEqual(res.action, "spotify_next_track")
        self.assertTrue(res.data.get("mock"))

    def test_previous_track_mock(self) -> None:
        res = self.controller.previous_track(is_mock=True)
        self.assertTrue(res.success)
        self.assertEqual(res.action, "spotify_previous_track")
        self.assertTrue(res.data.get("mock"))

    def test_play_query_mock(self) -> None:
        res = self.controller.play_query("Interstellar Soundtrack", is_mock=True)
        self.assertTrue(res.success)
        self.assertEqual(res.action, "spotify_play_query")
        self.assertIn("spotify:search:Interstellar%20Soundtrack", res.data.get("uri", ""))


class TestSpotifyServiceIntegration(unittest.IsolatedAsyncioTestCase):
    """Test suite for CommandEngineService action execution and event bus telemetry."""

    async def asyncSetUp(self) -> None:
        os.environ["DENVER_MOCK_AUTOMATION"] = "true"
        self.event_bus = DenverEventBus()
        self.memory_service = MagicMock(spec=MemoryService)

        self.service = CommandEngineService(
            memory_service=self.memory_service,
            event_bus=self.event_bus,
        )

    async def asyncTearDown(self) -> None:
        os.environ.pop("DENVER_MOCK_AUTOMATION", None)
        await self.event_bus.shutdown()

    async def test_spotify_play_pause_command(self) -> None:
        events: list[SpotifyPlaybackChanged] = []

        async def on_event(ev: SpotifyPlaybackChanged) -> None:
            events.append(ev)

        self.event_bus.subscribe(SpotifyPlaybackChanged, on_event)

        res = await self.service.process_command("Denver, play music")
        self.assertTrue(res.success)
        self.assertEqual(res.action_name, "spotify_play_pause")
        await asyncio.sleep(0.05)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].action, "play_pause")

    async def test_spotify_next_track_command(self) -> None:
        events: list[SpotifyPlaybackChanged] = []

        async def on_event(ev: SpotifyPlaybackChanged) -> None:
            events.append(ev)

        self.event_bus.subscribe(SpotifyPlaybackChanged, on_event)

        res = await self.service.process_command("Denver, next song")
        self.assertTrue(res.success)
        self.assertEqual(res.action_name, "spotify_next_track")
        await asyncio.sleep(0.05)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].action, "next_track")

    async def test_spotify_play_query_command(self) -> None:
        events: list[SpotifyPlaybackChanged] = []

        async def on_event(ev: SpotifyPlaybackChanged) -> None:
            events.append(ev)

        self.event_bus.subscribe(SpotifyPlaybackChanged, on_event)

        res = await self.service.process_command("Denver, play Starboy on spotify")
        self.assertTrue(res.success)
        self.assertEqual(res.action_name, "spotify_play_query")
        await asyncio.sleep(0.05)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].action, "play_query")
        self.assertEqual(events[0].query.lower(), "starboy")


if __name__ == "__main__":
    unittest.main()
