"""Unit tests for Denver Live Current Location Service, Dual-Layer Cache, and Command Integration."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from denver.automation.location import LocationResult, LocationService
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.config.settings import DenverSettings
from denver.memory.database import DenverDatabase
from denver.memory.memory_service import MemoryService
from denver.memory.models import CachedLocation


@pytest.fixture
def mock_settings(tmp_path):
    return DenverSettings(
        database_path=tmp_path / "test_location.sqlite3",
        location_cache_ttl_seconds=600,
        location_timeout_seconds=2.0,
        ai_enabled=False,
    )


@pytest.fixture
async def memory_service(mock_settings):
    db = DenverDatabase(db_path=mock_settings.database_path)
    mem = MemoryService(db=db)
    yield mem
    await db.close()


@pytest.mark.asyncio
async def test_primary_provider_ipapi_success(mock_settings, memory_service):
    """Test successful current location detection using primary provider ipapi.co."""
    service = LocationService(settings=mock_settings, memory_service=memory_service)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "latitude": 51.5074,
        "longitude": -0.1278,
        "city": "London",
        "region": "England",
        "country_name": "United Kingdom",
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await service.detect_current_location(force_refresh=True)

        assert res.success is True
        assert res.city == "London"
        assert res.latitude == 51.5074
        assert res.longitude == -0.1278
        assert res.source == "ipapi.co"
        assert "London" in res.spoken_description

        # Verify persisted to SQLite cache
        cached_db = await memory_service.get_cached_location()
        assert cached_db is not None
        assert cached_db.city == "London"
        assert cached_db.latitude == 51.5074


@pytest.mark.asyncio
async def test_primary_429_rate_limit_falls_back_to_secondary(mock_settings, memory_service):
    """Test that HTTP 429 on primary skips directly to secondary fallback provider ip-api.com."""
    service = LocationService(settings=mock_settings, memory_service=memory_service)

    # First call: 429 on ipapi.co
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429

    # Second call: 200 on ip-api.com
    mock_resp_secondary = MagicMock()
    mock_resp_secondary.status_code = 200
    mock_resp_secondary.json.return_value = {
        "status": "success",
        "lat": 12.9716,
        "lon": 77.5946,
        "city": "Bengaluru",
        "regionName": "Karnataka",
        "country": "India",
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [mock_resp_429, mock_resp_secondary]
        res = await service.detect_current_location(force_refresh=True)

        assert res.success is True
        assert res.city == "Bengaluru"
        assert res.source == "ip-api.com"
        assert res.latitude == 12.9716
        assert res.longitude == 77.5946


@pytest.mark.asyncio
async def test_all_providers_failed_with_stale_cache_fallback(mock_settings, memory_service):
    """Test that when all live providers fail, stale SQLite cache is used with explicit notice."""
    # Pre-populate SQLite cache with timestamp from 30 mins ago
    old_time = datetime.now(timezone.utc) - timedelta(minutes=30)
    await memory_service.save_cached_location(
        latitude=40.7128,
        longitude=-74.0060,
        city="New York",
        region="New York",
        country="United States",
        formatted_address="New York, New York, United States",
    )

    service = LocationService(settings=mock_settings, memory_service=memory_service)

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("Network unreachable")
        res = await service.detect_current_location(force_refresh=True)

        assert res.success is True
        assert res.is_stale is True
        assert res.city == "New York"
        assert "last known location" in res.spoken_description.lower()


@pytest.mark.asyncio
async def test_all_providers_failed_without_cache(mock_settings, memory_service):
    """Test that complete failure without cache yields clear failure message."""
    service = LocationService(settings=mock_settings, memory_service=memory_service)

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("No network")
        res = await service.detect_current_location(force_refresh=True)

        assert res.success is False
        assert "Could not detect" in res.spoken_description


@pytest.mark.asyncio
async def test_sqlite_cache_persists_across_instances(mock_settings, memory_service):
    """Test that a new LocationService instance (simulating new CLI process) hits SQLite cache within TTL."""
    # 1. First instance detects and saves
    s1 = LocationService(settings=mock_settings, memory_service=memory_service)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "latitude": 48.8566,
        "longitude": 2.3522,
        "city": "Paris",
        "region": "Ile-de-France",
        "country_name": "France",
    }
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res1 = await s1.detect_current_location(force_refresh=True)
        assert res1.city == "Paris"

    # 2. Second separate instance (e.g. new CLI command process)
    s2 = LocationService(settings=mock_settings, memory_service=memory_service)
    # Ensure network is NOT called
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get_s2:
        res2 = await s2.detect_current_location(force_refresh=False)
        mock_get_s2.assert_not_called()
        assert res2.success is True
        assert res2.city == "Paris"
        assert res2.source == "sqlite_cache"


def test_intent_router_location_triggers():
    """Verify IntentRouter captures current location queries and save-current-location variations."""
    router = IntentRouter()

    # 1. Current location queries
    for phrase in ["where am i", "what is my current location", "show my location", "current location"]:
        intent = router.route(phrase)
        assert intent.action_name == "get_current_location", f"Failed for '{phrase}'"

    # 2. Save current location queries
    intent_save1 = router.route("save my current location as home")
    assert intent_save1.action_name == "save_current_location"
    assert intent_save1.params.get("label") == "home"

    intent_save2 = router.route("save where I am as office")
    assert intent_save2.action_name == "save_current_location"
    assert intent_save2.params.get("label") == "office"

    intent_save3 = router.route("remember current location as work confirm")
    assert intent_save3.action_name == "save_current_location"
    assert intent_save3.params.get("label") == "work"
    assert intent_save3.params.get("confirmed") is True


@pytest.mark.asyncio
async def test_command_service_current_location_and_confirmation_flow(mock_settings, memory_service):
    """Verify CommandEngineService end-to-end current location queries and confirmation flow."""
    cmd_service = CommandEngineService(
        memory_service=memory_service,
        settings=mock_settings,
    )

    mock_loc = LocationResult(
        success=True,
        latitude=51.5074,
        longitude=-0.1278,
        city="London",
        region="England",
        country="United Kingdom",
        formatted_address="London, England, United Kingdom",
        source="ipapi.co",
    )

    with patch.object(cmd_service.location_service, "detect_current_location", new_callable=AsyncMock) as mock_det:
        mock_det.return_value = mock_loc

        # 1. Query current location
        res_loc = await cmd_service.process_command("where am I")
        assert res_loc.success is True
        assert "London" in res_loc.message

        # 2. Save current location without confirmation -> requests confirmation
        res_save = await cmd_service.process_command("save my current location as home")
        assert res_save.success is True
        assert "confirm" in res_save.message.lower()
        assert res_save.data.get("requires_confirmation") is True

        # Verify not yet written
        saved_before = await memory_service.get_saved_location("home")
        assert saved_before is None

        # 3. Confirm the action
        res_confirm = await cmd_service.process_command("confirm")
        assert res_confirm.success is True
        assert "Confirmed" in res_confirm.message
        assert "Home" in res_confirm.message

        # Verify now persisted in saved_locations
        saved_after = await memory_service.get_saved_location("home")
        assert saved_after is not None
        assert "London" in saved_after.raw_address
        assert saved_after.latitude == 51.5074
