"""Live Current Location Detection Service for Denver AI Assistant.

Supports privacy-preserving IP geolocation with an explicit ordered provider chain:
1. Primary: ipapi.co (HTTPS)
2. Secondary Fallback: ip-api.com (HTTP - non-commercial, 45 req/min rate limit)
Backed by both fast in-memory process caching and persistent SQLite cache across CLI invocations.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

from denver.config.settings import DenverSettings, get_settings
from denver.logging.logger import get_logger
from denver.memory.memory_service import MemoryService
from denver.memory.models import CachedLocation

logger = get_logger("automation.location")


@dataclass
class LocationResult:
    """Represents the output of a current location detection attempt."""

    success: bool
    latitude: float | None = None
    longitude: float | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    formatted_address: str | None = None
    source: str = "network"  # 'ipapi.co', 'ip-api.com', 'sqlite_cache', 'memory_cache', 'stale_cache'
    is_stale: bool = False
    age_seconds: float = 0.0
    error: str | None = None

    @property
    def spoken_description(self) -> str:
        """Produce a clean human-readable spoken summary of the detected location."""
        if not self.success:
            return "Could not detect your current location."
        parts = [p for p in [self.city, self.region, self.country] if p]
        loc_str = ", ".join(parts) if parts else (self.formatted_address or "Unknown Location")
        if self.is_stale:
            mins_ago = max(1, int(self.age_seconds // 60))
            return f"Using your last known location ({loc_str}) from {mins_ago} minutes ago."
        return loc_str

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "city": self.city,
            "region": self.region,
            "country": self.country,
            "formatted_address": self.formatted_address,
            "source": self.source,
            "is_stale": self.is_stale,
            "age_seconds": round(self.age_seconds, 1),
            "spoken_description": self.spoken_description,
            "error": self.error,
        }


class LocationService:
    """Service to resolve real-time device/network geolocation and manage dual-layer caching."""

    def __init__(
        self,
        settings: DenverSettings | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.memory = memory_service
        self._mem_cache: LocationResult | None = None
        self._mem_cached_at: float = 0.0

    async def detect_current_location(self, force_refresh: bool = False) -> LocationResult:
        """Detect device's current location via IP geolocation with persistent cache lookup."""
        cache_ttl = getattr(self.settings, "location_cache_ttl_seconds", 600)
        timeout_s = getattr(self.settings, "location_timeout_seconds", 5.0)
        now_ts = time.time()

        # 1. Check in-memory cache (fast-path for long-running voice/GUI process)
        if not force_refresh and self._mem_cache and self._mem_cache.success:
            age = now_ts - self._mem_cached_at
            if age < cache_ttl:
                logger.debug("Returning in-memory cached location (age: %.1fs)", age)
                return LocationResult(
                    success=True,
                    latitude=self._mem_cache.latitude,
                    longitude=self._mem_cache.longitude,
                    city=self._mem_cache.city,
                    region=self._mem_cache.region,
                    country=self._mem_cache.country,
                    formatted_address=self._mem_cache.formatted_address,
                    source="memory_cache",
                    is_stale=False,
                    age_seconds=age,
                )

        # 2. Check persistent SQLite cache (fast-path across CLI single-shot processes)
        if not force_refresh and self.memory:
            try:
                cached_db = await self.memory.get_cached_location()
                if cached_db:
                    det_at = cached_db.detected_at
                    if det_at.tzinfo is None:
                        det_at = det_at.replace(tzinfo=timezone.utc)
                    db_age = (datetime.now(timezone.utc) - det_at).total_seconds()
                    if db_age < cache_ttl:
                        logger.debug("Returning SQLite-cached location (age: %.1fs)", db_age)
                        res = LocationResult(
                            success=True,
                            latitude=cached_db.latitude,
                            longitude=cached_db.longitude,
                            city=cached_db.city,
                            region=cached_db.region,
                            country=cached_db.country,
                            formatted_address=cached_db.formatted_address,
                            source="sqlite_cache",
                            is_stale=False,
                            age_seconds=db_age,
                        )
                        self._mem_cache = res
                        self._mem_cached_at = now_ts - db_age
                        return res
            except Exception as exc:
                logger.warning("Failed to query SQLite location cache: %s", exc)

        if not _HTTPX_AVAILABLE:
            logger.error("httpx is not installed; cannot perform outbound geolocation request.")
            return await self._fallback_or_fail("httpx_missing")

        # 3. Primary Provider: ipapi.co (HTTPS)
        primary_res = await self._query_ipapi_co(timeout_s)
        if primary_res and primary_res.success:
            await self._persist_cache(primary_res)
            return primary_res

        # 4. Secondary Fallback Provider: ip-api.com (HTTP plaintext)
        # Note: ip-api.com free tier is strictly unencrypted HTTP and rate limited to 45 req/min.
        logger.info("Primary location provider failed or rate-limited; attempting secondary fallback (ip-api.com)...")
        fallback_res = await self._query_ip_api_com(timeout_s)
        if fallback_res and fallback_res.success:
            await self._persist_cache(fallback_res)
            return fallback_res

        # 5. Both providers failed: check if a stale cache entry is available
        logger.warning("All live geolocation providers failed. Checking for stale cache fallback...")
        return await self._fallback_or_fail("all_providers_failed")

    async def _query_ipapi_co(self, timeout: float) -> LocationResult | None:
        """Query primary HTTPS provider: ipapi.co."""
        url = "https://ipapi.co/json/"
        headers = {"User-Agent": "Denver-Assistant/1.0"}
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 429:
                    logger.warning("ipapi.co returned HTTP 429 (Rate Limited). Skipping to fallback.")
                    return None
                if resp.status_code != 200:
                    logger.warning("ipapi.co returned HTTP %d: %s", resp.status_code, resp.text[:100])
                    return None
                data = resp.json()
                if data.get("error"):
                    logger.warning("ipapi.co error in response: %s", data.get("reason", "unknown"))
                    return None

                lat = float(data["latitude"])
                lon = float(data["longitude"])
                city = data.get("city") or ""
                region = data.get("region") or ""
                country = data.get("country_name") or data.get("country") or ""
                parts = [p for p in [city, region, country] if p]
                formatted = ", ".join(parts) if parts else f"{lat:.4f}, {lon:.4f}"

                return LocationResult(
                    success=True,
                    latitude=lat,
                    longitude=lon,
                    city=city or None,
                    region=region or None,
                    country=country or None,
                    formatted_address=formatted,
                    source="ipapi.co",
                    is_stale=False,
                    age_seconds=0.0,
                )
        except httpx.TimeoutException:
            logger.warning("ipapi.co query timed out after %.1fs.", timeout)
            return None
        except Exception as exc:
            logger.warning("ipapi.co query failed: %s", exc)
            return None

    async def _query_ip_api_com(self, timeout: float) -> LocationResult | None:
        """Query secondary fallback HTTP provider: ip-api.com.
        
        Note: The free tier of ip-api.com is plain HTTP without TLS encryption, capped at
        45 requests per minute. It is used strictly when ipapi.co fails or hits rate limits.
        """
        url = "http://ip-api.com/json/"
        headers = {"User-Agent": "Denver-Assistant/1.0"}
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 429:
                    logger.warning("ip-api.com returned HTTP 429 (Rate Limited).")
                    return None
                if resp.status_code != 200:
                    logger.warning("ip-api.com returned HTTP %d: %s", resp.status_code, resp.text[:100])
                    return None
                data = resp.json()
                if data.get("status") == "fail":
                    logger.warning("ip-api.com reported failure: %s", data.get("message", "unknown"))
                    return None

                lat = float(data["lat"])
                lon = float(data["lon"])
                city = data.get("city") or ""
                region = data.get("regionName") or data.get("region") or ""
                country = data.get("country") or ""
                parts = [p for p in [city, region, country] if p]
                formatted = ", ".join(parts) if parts else f"{lat:.4f}, {lon:.4f}"

                return LocationResult(
                    success=True,
                    latitude=lat,
                    longitude=lon,
                    city=city or None,
                    region=region or None,
                    country=country or None,
                    formatted_address=formatted,
                    source="ip-api.com",
                    is_stale=False,
                    age_seconds=0.0,
                )
        except httpx.TimeoutException:
            logger.warning("ip-api.com query timed out after %.1fs.", timeout)
            return None
        except Exception as exc:
            logger.warning("ip-api.com query failed: %s", exc)
            return None

    async def _persist_cache(self, res: LocationResult) -> None:
        """Update both memory cache and SQLite persistent cache."""
        self._mem_cache = res
        self._mem_cached_at = time.time()
        if self.memory and res.latitude is not None and res.longitude is not None:
            try:
                await self.memory.save_cached_location(
                    latitude=res.latitude,
                    longitude=res.longitude,
                    city=res.city,
                    region=res.region,
                    country=res.country,
                    formatted_address=res.formatted_address,
                )
                logger.debug("Persisted live location to SQLite cache (%s)", res.formatted_address)
            except Exception as exc:
                logger.warning("Failed to persist location cache to SQLite: %s", exc)

    async def _fallback_or_fail(self, reason: str) -> LocationResult:
        """Handle offline/failed scenario: check for stale SQLite cache before returning failure."""
        if self.memory:
            try:
                cached_db = await self.memory.get_cached_location()
                if cached_db:
                    det_at = cached_db.detected_at
                    if det_at.tzinfo is None:
                        det_at = det_at.replace(tzinfo=timezone.utc)
                    db_age = (datetime.now(timezone.utc) - det_at).total_seconds()
                    logger.info("Using stale location from SQLite cache (age: %.1fs)", db_age)
                    return LocationResult(
                        success=True,
                        latitude=cached_db.latitude,
                        longitude=cached_db.longitude,
                        city=cached_db.city,
                        region=cached_db.region,
                        country=cached_db.country,
                        formatted_address=cached_db.formatted_address,
                        source="stale_cache",
                        is_stale=True,
                        age_seconds=db_age,
                    )
            except Exception as exc:
                logger.warning("Failed to query stale SQLite location cache: %s", exc)

        return LocationResult(
            success=False,
            error=reason,
        )
