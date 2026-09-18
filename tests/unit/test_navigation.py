"""Unit tests for Denver Fastest-Route Navigation Subsystem."""

import pytest
from unittest.mock import AsyncMock, patch

from denver.automation.navigation import (
    NavigationService,
    RouteResult,
    build_google_maps_url,
    format_distance,
    format_duration,
)
from denver.automation.weather import GeocodeResult
from denver.commands.router import IntentRouter
from denver.config.settings import DenverSettings


def test_duration_and_distance_formatting() -> None:
    assert format_duration(45) == "45 sec"
    assert format_duration(300) == "5 min"
    assert format_duration(3600) == "1 hr"
    assert format_duration(11700) == "3 hr 15 min"

    assert format_distance(450) == "450 m"
    assert format_distance(1000) == "1 km"
    assert format_distance(145200) == "145.2 km"


def test_google_maps_url_generation() -> None:
    url = build_google_maps_url("Bangalore", "Mysore", mode="driving")
    assert "origin=Bangalore" in url
    assert "destination=Mysore" in url
    assert "travelmode=driving" in url

    url_walk = build_google_maps_url("Times Square", "Central Park", mode="walking")
    assert "travelmode=walking" in url_walk


@pytest.mark.asyncio
async def test_navigation_transit_handling() -> None:
    settings = DenverSettings(route_open_in_browser=False)
    service = NavigationService(settings=settings)

    res = await service.calculate_route("Boston", "New York", mode="transit")
    assert res.source == "transit_redirect"
    assert "Public transit schedules" in res.spoken_summary
    assert "travelmode=transit" in res.maps_url


@pytest.mark.asyncio
async def test_navigation_osrm_route_calculation() -> None:
    settings = DenverSettings(
        osrm_base_url="http://osrm.local",
        route_open_in_browser=False,
    )
    service = NavigationService(settings=settings)

    orig_geo = GeocodeResult(name="Bangalore", latitude=12.97, longitude=77.59)
    dest_geo = GeocodeResult(name="Mysore", latitude=12.30, longitude=76.65)

    osrm_response = {
        "routes": [
            {
                "duration": 11700.0,  # 3 hr 15 min
                "distance": 145000.0,  # 145 km
            }
        ]
    }

    with patch.object(service.weather_service, "geocode", side_effect=[orig_geo, dest_geo]):
        with patch.object(service, "_http_get_json", return_value=osrm_response):
            res = await service.calculate_route("Bangalore", "Mysore", mode="driving")
            assert res.source == "osrm"
            assert res.formatted_duration == "3 hr 15 min"
            assert res.formatted_distance == "145 km"
            assert "typical travel time, no live traffic data" in res.spoken_summary


@pytest.mark.asyncio
async def test_navigation_mode_switching() -> None:
    settings = DenverSettings(route_open_in_browser=False)
    service = NavigationService(settings=settings)

    # Prime last route
    service._last_route = {
        "origin": "Empire State Building",
        "destination": "Madison Square Garden",
        "mode": "driving",
    }

    with patch.object(service, "calculate_route", new=AsyncMock(return_value=RouteResult(
        origin="Empire State Building",
        destination="Madison Square Garden",
        mode="walking",
        spoken_summary="Fastest walking route is 10 min.",
        source="test",
    ))) as mock_calc:
        res = await service.switch_last_route_mode("walking")
        assert res.mode == "walking"
        mock_calc.assert_called_once_with(
            origin="Empire State Building",
            destination="Madison Square Garden",
            mode="walking",
        )


def test_intent_router_navigation_triggers() -> None:
    router = IntentRouter()

    # Directions from A to B
    i1 = router.route("how do I get from Bangalore to Mysore")
    assert i1.action_name == "get_directions"
    assert i1.params["origin"].lower() == "bangalore"
    assert i1.params["destination"].lower() == "mysore"
    assert i1.params["mode"] == "driving"

    # Directions by walking
    i2 = router.route("fastest route from Central Park to Times Square by walking")
    assert i2.action_name == "get_directions"
    assert i2.params["mode"] == "walking"

    # Single navigate to
    i3 = router.route("navigate to the airport")
    assert i3.action_name == "navigate_to"
    assert "airport" in i3.params["destination"].lower()

    # Mode switch
    i4 = router.route("switch to walking directions")
    assert i4.action_name == "switch_directions_mode"
    assert i4.params["mode"] == "walking"

    i5 = router.route("actually driving")
    assert i5.action_name == "switch_directions_mode"
    assert i5.params["mode"] == "driving"
