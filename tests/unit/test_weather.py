"""Unit tests for Denver Live Weather Subsystem."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from denver.automation.weather import (
    GeocodeResult,
    WeatherReport,
    WeatherService,
    get_wmo_description,
)
from denver.automation.web_agent import WebSearchResult
from denver.commands.router import IntentRouter
from denver.config.settings import DenverSettings


def test_wmo_code_descriptions() -> None:
    assert get_wmo_description(0) == "Clear sky"
    assert get_wmo_description(1) == "Mainly clear"
    assert get_wmo_description(61) == "Slight rain"
    assert get_wmo_description(95) == "Thunderstorm"
    assert get_wmo_description(None) == "Fair"
    assert get_wmo_description(9999) == "Partly cloudy"


@pytest.mark.asyncio
async def test_weather_geocoding_disambiguation() -> None:
    mock_geo_data = {
        "results": [
            {"name": "Springfield", "latitude": 39.78, "longitude": -89.65, "country": "United States", "population": 114000},
            {"name": "Springfield", "latitude": 44.04, "longitude": -123.01, "country": "United States", "population": 60000},
            {"name": "Springfield", "latitude": 52.00, "longitude": 0.50, "country": "United Kingdom", "population": None},
        ]
    }

    settings = DenverSettings()
    service = WeatherService(settings=settings)

    with patch.object(service, "_http_get_json", return_value=mock_geo_data):
        # 1. Without country hint -> highest population chosen (Springfield, IL)
        res1 = await service.geocode("Springfield")
        assert res1 is not None
        assert res1.latitude == 39.78
        assert res1.population == 114000

        # 2. With UK country hint -> UK chosen even with missing population
        res2 = await service.geocode("Springfield", country_hint="United Kingdom")
        assert res2 is not None
        assert res2.country == "United Kingdom"
        assert res2.population == 0


@pytest.mark.asyncio
async def test_weather_get_current_weather() -> None:
    settings = DenverSettings()
    service = WeatherService(settings=settings)

    geo_return = GeocodeResult(name="Paris", latitude=48.85, longitude=2.35, country="France")
    forecast_return = {
        "current": {
            "temperature_2m": 22.4,
            "relative_humidity_2m": 55,
            "wind_speed_10m": 12.0,
            "precipitation": 0.0,
            "weather_code": 1,
        },
        "daily": {
            "precipitation_probability_max": [10],
        },
    }

    with patch.object(service, "geocode", new=AsyncMock(return_value=geo_return)):
        with patch.object(service, "_http_get_json", return_value=forecast_return):
            report = await service.get_current_weather("Paris")
            assert report.city == "Paris, France"
            assert report.temp_c == 22.4
            assert report.condition == "Mainly clear"
            assert report.humidity_pct == 55
            assert report.source == "open-meteo"
            assert "22°C" in report.to_spoken_summary()


@pytest.mark.asyncio
async def test_weather_get_forecast() -> None:
    settings = DenverSettings()
    service = WeatherService(settings=settings)

    geo_return = GeocodeResult(name="Tokyo", latitude=35.68, longitude=139.76, country="Japan")
    forecast_return = {
        "current": {"temperature_2m": 18.0, "weather_code": 2},
        "daily": {
            "weather_code": [2, 61],
            "precipitation_probability_max": [20, 80],
            "temperature_2m_max": [20.0, 16.5],
        },
    }

    with patch.object(service, "geocode", new=AsyncMock(return_value=geo_return)):
        with patch.object(service, "_http_get_json", return_value=forecast_return):
            report = await service.get_forecast("Tokyo", days=1)
            assert report.city == "Tokyo, Japan"
            assert report.is_forecast is True
            assert report.precip_probability_pct == 80
            assert "Chance of rain is 80%" in report.to_spoken_summary()


@pytest.mark.asyncio
async def test_weather_web_agent_fallback() -> None:
    settings = DenverSettings(weather_fallback_to_web_agent=True)
    fake_web_agent = MagicMock()
    mock_results = [
        WebSearchResult(
            title="London Weather Forecast",
            snippet="Current temperature is 19°C with cloudy skies and light breeze.",
            url="https://weather.test/london",
        )
    ]
    fake_web_agent.search_web = AsyncMock(return_value=mock_results)
    fake_web_agent.search = AsyncMock(return_value=mock_results)

    service = WeatherService(settings=settings, web_agent=fake_web_agent)

    # Simulate geocoding failure
    with patch.object(service, "geocode", new=AsyncMock(return_value=None)):
        report = await service.get_current_weather("London")
        assert report.source == "web_agent_fallback"
        assert report.temp_c == 19.0
        assert "Cloudy" in report.condition


def test_intent_router_weather_triggers() -> None:
    router = IntentRouter()

    # Current weather
    i1 = router.route("what's the weather in London")
    assert i1.action_name == "get_weather"
    assert i1.params["city"].lower() == "london"

    i2 = router.route("how's the weather today in Bangalore")
    assert i2.action_name == "get_weather"
    assert i2.params["city"].lower() == "bangalore"

    i3 = router.route("what is it like outside")
    assert i3.action_name == "get_weather"
    assert i3.params["city"] == ""

    # Forecast
    i4 = router.route("will it rain tomorrow in Delhi")
    assert i4.action_name == "get_weather_forecast"
    assert i4.params["city"].lower() == "delhi"

    i5 = router.route("weather forecast for Tokyo")
    assert i5.action_name == "get_weather_forecast"
    assert i5.params["city"].lower() == "tokyo"
