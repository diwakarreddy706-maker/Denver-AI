"""Unit tests for TTS Phrase Caching and CachedTTSProvider."""

from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from denver.audio.fake import FakeTTSProvider
from denver.audio.models import TTSRequest, TTSResult
from denver.audio.tts_cache import CachedTTSProvider, TTSPhraseCache


class TestTTSPhraseCache(unittest.IsolatedAsyncioTestCase):
    """Test suite for TTS phrase caching, disk persistence, and instant lookup."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name) / "tts_cache"
        self.cache = TTSPhraseCache(max_entries=10, cache_dir=self.cache_dir, enable_disk_cache=True)
        self.fake_tts = FakeTTSProvider()
        self.cached_tts = CachedTTSProvider(inner_provider=self.fake_tts, cache=self.cache)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_tts_cache_hit_and_miss_lifecycle(self) -> None:
        req = TTSRequest(text="Standing by.")

        # 1. First call -> Cache MISS -> Invokes fake_tts
        res1 = await self.cached_tts.synthesize(req)
        self.assertTrue(res1.success)
        self.assertEqual(self.cache.misses, 1)
        self.assertEqual(self.cache.hits, 0)
        self.assertEqual(self.cache.size, 1)

        # 2. Second call -> Cache HIT -> Returns cached copy with sub-millisecond latency
        res2 = await self.cached_tts.synthesize(req)
        self.assertTrue(res2.success)
        self.assertEqual(self.cache.hits, 1)
        self.assertEqual(self.cache.hit_rate, 0.5)
        self.assertIn("cached", res2.provider)

    async def test_disk_cache_persistence_across_instances(self) -> None:
        req = TTSRequest(text="All systems operational.")

        # Write to cache with instance 1
        res1 = await self.cached_tts.synthesize(req)
        self.assertTrue(res1.success)

        # Create fresh instance pointing to same disk directory (empty memory cache)
        cache2 = TTSPhraseCache(max_entries=10, cache_dir=self.cache_dir, enable_disk_cache=True)
        cached_tts2 = CachedTTSProvider(inner_provider=FakeTTSProvider(), cache=cache2)

        # Should load from disk cache
        res2 = await cached_tts2.synthesize(req)
        self.assertTrue(res2.success)
        self.assertEqual(cache2.hits, 1)
        self.assertEqual(cache2.misses, 0)

    async def test_cache_eviction_when_full(self) -> None:
        small_cache = TTSPhraseCache(max_entries=2, cache_dir=None, enable_disk_cache=False)
        tts = CachedTTSProvider(inner_provider=FakeTTSProvider(), cache=small_cache)

        await tts.synthesize(TTSRequest(text="Phrase 1"))
        await tts.synthesize(TTSRequest(text="Phrase 2"))
        self.assertEqual(small_cache.size, 2)

        # Adding 3rd phrase should evict oldest and maintain max_entries limit
        await tts.synthesize(TTSRequest(text="Phrase 3"))
        self.assertEqual(small_cache.size, 2)


if __name__ == "__main__":
    unittest.main()
