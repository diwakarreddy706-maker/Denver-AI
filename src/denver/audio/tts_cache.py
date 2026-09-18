"""Fast TTS Phrase Caching for Denver Voice Engine."""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from denver.audio.models import TTSRequest, TTSResult
from denver.audio.tts import TextToSpeechProvider
from denver.logging.logger import get_logger

logger = get_logger("audio.tts_cache")

COMMON_SYSTEM_PHRASES: tuple[str, ...] = (
    "Standing by.",
    "Command completed.",
    "All systems operational.",
    "I am listening.",
    "Diagnostic complete.",
    "Yes, sir?",
    "How can I help you?",
    "Stopping all tasks.",
    "Microphone muted.",
    "Microphone active.",
)


@dataclass
class CacheEntry:
    result: TTSResult
    cached_at: float = field(default_factory=time.time)
    hit_count: int = 0


class TTSPhraseCache:
    """In-memory and disk cache for synthesized audio phrases."""

    def __init__(
        self,
        max_entries: int = 256,
        cache_dir: str | Path | None = "data/cache/tts",
        enable_disk_cache: bool = True,
    ) -> None:
        self.max_entries = max_entries
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.enable_disk_cache = enable_disk_cache and self.cache_dir is not None
        self._memory_cache: dict[str, CacheEntry] = {}
        self.hits: int = 0
        self.misses: int = 0

        if self.enable_disk_cache and self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_key(request: TTSRequest) -> str:
        """Create a deterministic SHA-256 hash for a TTSRequest."""
        norm_text = request.text.strip().lower()
        key_raw = f"{norm_text}|{request.voice}|{request.rate}|{request.volume}|{request.pitch}"
        return hashlib.sha256(key_raw.encode("utf-8")).hexdigest()[:16]

    def get(self, request: TTSRequest) -> TTSResult | None:
        """Lookup cached TTSResult in memory or disk."""
        key = self.compute_key(request)

        # 1. Check memory cache
        if key in self._memory_cache:
            entry = self._memory_cache[key]
            entry.hit_count += 1
            self.hits += 1
            res = entry.result
            return TTSResult(
                success=res.success,
                audio_data=res.audio_data,
                format=res.format,
                sample_rate=res.sample_rate,
                duration_seconds=res.duration_seconds,
                latency_ms=0.5,
                provider=f"{res.provider}_cached",
                error=res.error,
            )

        # 2. Check disk cache
        if self.enable_disk_cache and self.cache_dir:
            meta_file = self.cache_dir / f"{key}.meta"
            audio_file = self.cache_dir / f"{key}.audio"
            if meta_file.exists() and audio_file.exists():
                try:
                    import json
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    audio_data = audio_file.read_bytes()
                    res = TTSResult(
                        success=True,
                        audio_data=audio_data,
                        format=meta.get("format", "mp3"),
                        sample_rate=meta.get("sample_rate", 24000),
                        duration_seconds=meta.get("duration_seconds", 0.0),
                        latency_ms=1.0,
                        provider=f"{meta.get('provider', 'tts')}_cached",
                    )
                    self._put_memory(key, res)
                    self.hits += 1
                    return res
                except Exception as exc:
                    logger.debug("Failed reading disk cache for key %s: %s", key, exc)

        self.misses += 1
        return None

    def put(self, request: TTSRequest, result: TTSResult) -> None:
        """Store synthesized TTSResult into memory and disk cache."""
        if not result.success or not result.audio_data:
            return

        key = self.compute_key(request)
        self._put_memory(key, result)

        if self.enable_disk_cache and self.cache_dir:
            try:
                import json
                meta_file = self.cache_dir / f"{key}.meta"
                audio_file = self.cache_dir / f"{key}.audio"
                meta_file.write_text(
                    json.dumps({
                        "text": request.text,
                        "voice": request.voice,
                        "format": result.format,
                        "sample_rate": result.sample_rate,
                        "duration_seconds": result.duration_seconds,
                        "provider": result.provider,
                    }),
                    encoding="utf-8",
                )
                audio_file.write_bytes(result.audio_data)
            except Exception as exc:
                logger.debug("Failed saving disk cache for key %s: %s", key, exc)

    def _put_memory(self, key: str, result: TTSResult) -> None:
        if len(self._memory_cache) >= self.max_entries:
            # Evict oldest
            oldest_key = min(self._memory_cache.keys(), key=lambda k: self._memory_cache[k].cached_at)
            del self._memory_cache[oldest_key]
        self._memory_cache[key] = CacheEntry(result=result)

    def clear(self) -> None:
        """Clear all in-memory and disk cache entries."""
        self._memory_cache.clear()
        self.hits = 0
        self.misses = 0
        if self.enable_disk_cache and self.cache_dir and self.cache_dir.exists():
            for f in self.cache_dir.glob("*"):
                try:
                    f.unlink()
                except Exception:
                    pass

    @property
    def size(self) -> int:
        return len(self._memory_cache)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 3) if total > 0 else 0.0


class CachedTTSProvider(TextToSpeechProvider):
    """Decorator provider that transparently wraps any TTS provider with fast caching."""

    def __init__(
        self,
        inner_provider: TextToSpeechProvider,
        cache: TTSPhraseCache | None = None,
    ) -> None:
        self.inner = inner_provider
        self.cache = cache or TTSPhraseCache()

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def is_available(self) -> bool:
        return self.inner.is_available

    def get_health_status(self) -> dict[str, Any]:
        health = self.inner.get_health_status()
        health["cache_entries"] = self.cache.size
        health["cache_hits"] = self.cache.hits
        health["cache_hit_rate"] = self.cache.hit_rate
        return health

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        cached = self.cache.get(request)
        if cached is not None:
            logger.debug("TTS Cache HIT for: '%s' (0ms latency)", request.text[:30])
            return cached

        logger.debug("TTS Cache MISS for: '%s' -> invoking %s", request.text[:30], self.inner.name)
        result = await self.inner.synthesize(request)
        if result.success:
            self.cache.put(request, result)
        return result

    async def shutdown(self) -> None:
        await self.inner.shutdown()
