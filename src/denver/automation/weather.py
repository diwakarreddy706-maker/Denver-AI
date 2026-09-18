"""Live Weather Service for Denver AI Assistant using Open-Meteo & WebAgent Fallback."""

from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from denver.automation.web_agent import WebAgent
from denver.config.settings import DenverSettings, get_settings
from denver.logging.logger import get_logger

logger = get_logger("automation.weather")

WMO_CODE_DESCRIPTIONS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    62: "Moderate rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def get_wmo_description(code: int | None) -> str:
    """Map numeric WMO weather code to a human-readable condition string."""
    if code is None:
        return "Fair"
    return WMO_CODE_DESCRIPTIONS.get(code, "Partly cloudy")


@dataclass
class GeocodeResult:
    """Geocoded geographic coordinates for a named location."""

    name: str
    latitude: float
    longitude: float
    country: str = ""
    admin1: str = ""
    population: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "country": self.country,
            "admin1": self.admin1,
            "population": self.population,
        }


@dataclass
class WeatherReport:
    """Structured weather report and spoken summary."""

    city: str
    temp_c: float | None = None
    condition: str = "Unknown"
    humidity_pct: int | None = None
    wind_kph: float | None = None
    precip_mm: float | None = None
    precip_probability_pct: int | None = None
    is_forecast: bool = False
    source: str = "open-meteo"
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_spoken_summary(self) -> str:
        """Build a natural, human-friendly one-line summary for voice TTS."""
        if self.is_forecast:
            summary = f"Weather forecast for {self.city}: {self.condition}."
            if self.temp_c is not None:
                summary += f" Temperature around {round(self.temp_c)}°C."
            if self.precip_probability_pct is not None:
                summary += f" Chance of rain is {self.precip_probability_pct}%."
            return summary

        parts = [f"In {self.city}, it's currently {self.condition}"]
        if self.temp_c is not None:
            parts.append(f"at {round(self.temp_c)}°C")
        details = []
        if self.humidity_pct is not None:
            details.append(f"humidity is {self.humidity_pct}%")
        if self.wind_kph is not None and self.wind_kph > 0:
            details.append(f"wind speed is {round(self.wind_kph)} km/h")
        if self.precip_probability_pct is not None and self.precip_probability_pct > 0:
            details.append(f"{self.precip_probability_pct}% chance of precipitation")

        if details:
            return f"{' '.join(parts)}, with {', '.join(details)}."
        return f"{' '.join(parts)}."

    def to_dict(self) -> dict[str, Any]:
        return {
            "city": self.city,
            "temp_c": self.temp_c,
            "condition": self.condition,
            "humidity_pct": self.humidity_pct,
            "wind_kph": self.wind_kph,
            "precip_mm": self.precip_mm,
            "precip_probability_pct": self.precip_probability_pct,
            "is_forecast": self.is_forecast,
            "source": self.source,
            "spoken_summary": self.to_spoken_summary(),
        }


class WeatherService:
    """Live weather forecasting and geocoding engine."""

    def __init__(
        self,
        settings: DenverSettings | None = None,
        web_agent: WebAgent | None = None,
        location_service: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.web_agent = web_agent or WebAgent()
        self.location_service = location_service

    def _http_get_json(self, url: str, timeout: float | None = None) -> dict[str, Any]:
        """Perform synchronous HTTP GET request returning parsed JSON."""
        tout = timeout or self.settings.weather_timeout_seconds
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Denver-Assistant/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=tout) as resp:
            data = resp.read()
            return json.loads(data.decode("utf-8"))

    async def geocode(self, city_name: str, country_hint: str | None = None) -> GeocodeResult | None:
        """Geocode a city or place name into geographic latitude/longitude."""
        clean_name = city_name.strip()
        if not clean_name:
            return None

        # Check for current location aliases
        if clean_name.lower() in {"here", "current", "current location", "my location", "current place"}:
            if self.location_service:
                loc_res = await self.location_service.detect_current_location()
                if loc_res.success and loc_res.latitude is not None and loc_res.longitude is not None:
                    return GeocodeResult(
                        name=loc_res.city or loc_res.formatted_address or "Current Location",
                        latitude=loc_res.latitude,
                        longitude=loc_res.longitude,
                        country=loc_res.country or "",
                        admin1=loc_res.region or "",
                        population=0,
                    )

        query_url = f"{self.settings.weather_geocode_url}?name={urllib.parse.quote(clean_name)}&count=5"
        try:
            data = await asyncio.to_thread(self._http_get_json, query_url)
            results = data.get("results")
            if not results:
                logger.debug("Geocoding returned no results for '%s'", city_name)
                return None

            # Disambiguation:
            # 1. Exact country match if country hint provided
            # 2. Population ranking (safely default missing population to 0)
            # 3. Top result
            def _rank_key(item: dict[str, Any]) -> tuple[int, int]:
                country_match = 0
                if country_hint and str(item.get("country", "")).lower() == country_hint.strip().lower():
                    country_match = 1
                pop = item.get("population") or 0
                return (country_match, pop)

            best = max(results, key=_rank_key)
            return GeocodeResult(
                name=best.get("name", clean_name),
                latitude=float(best["latitude"]),
                longitude=float(best["longitude"]),
                country=best.get("country", ""),
                admin1=best.get("admin1", ""),
                population=best.get("population") or 0,
            )
        except Exception as exc:
            logger.warning("Geocoding failed for '%s': %s", city_name, exc)
            return None

    async def get_current_weather(self, city_name: str, country_hint: str | None = None) -> WeatherReport:
        """Fetch current real-time weather conditions for the specified city."""
        clean_name = city_name.strip() if city_name else "here"
        loc = await self.geocode(clean_name, country_hint=country_hint)
        if not loc:
            if self.settings.weather_fallback_to_web_agent:
                logger.warning("Geocoding failed for '%s'; falling back to WebAgent search.", clean_name)
                return await self._fallback_web_search(clean_name, is_forecast=False)
            return WeatherReport(
                city=clean_name,
                condition="Location not found",
                source="error",
            )

        forecast_url = (
            f"{self.settings.weather_forecast_url}"
            f"?latitude={loc.latitude}&longitude={loc.longitude}"
            f"&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code"
            f"&daily=precipitation_probability_max&timezone=auto"
        )

        try:
            data = await asyncio.to_thread(self._http_get_json, forecast_url)
            current = data.get("current", {})
            daily = data.get("daily", {})

            wmo_code = current.get("weather_code")
            condition = get_wmo_description(wmo_code)

            precip_prob = None
            daily_probs = daily.get("precipitation_probability_max", [])
            if daily_probs and isinstance(daily_probs, list):
                precip_prob = int(daily_probs[0]) if daily_probs[0] is not None else None

            city_label = loc.name
            if loc.country:
                city_label = f"{loc.name}, {loc.country}"

            return WeatherReport(
                city=city_label,
                temp_c=float(current["temperature_2m"]) if "temperature_2m" in current else None,
                condition=condition,
                humidity_pct=int(current["relative_humidity_2m"]) if "relative_humidity_2m" in current else None,
                wind_kph=float(current["wind_speed_10m"]) if "wind_speed_10m" in current else None,
                precip_mm=float(current["precipitation"]) if "precipitation" in current else None,
                precip_probability_pct=precip_prob,
                is_forecast=False,
                source="open-meteo",
                raw_payload=data,
            )
        except Exception as exc:
            logger.warning("Open-Meteo weather fetch failed for '%s': %s", city_name, exc)
            if self.settings.weather_fallback_to_web_agent:
                logger.warning("Falling back to WebAgent search for '%s' weather.", city_name)
                return await self._fallback_web_search(city_name, is_forecast=False)
            return WeatherReport(
                city=city_name,
                condition="Weather service unavailable",
                source="error",
            )

    async def get_forecast(self, city_name: str, country_hint: str | None = None, days: int = 1) -> WeatherReport:
        """Fetch 24-hour / multi-day forecast for the specified city."""
        clean_name = city_name.strip() if city_name else "here"
        loc = await self.geocode(clean_name, country_hint=country_hint)
        if not loc:
            if self.settings.weather_fallback_to_web_agent:
                return await self._fallback_web_search(clean_name, is_forecast=True)
            return WeatherReport(
                city=clean_name,
                condition="Location not found",
                is_forecast=True,
                source="error",
            )

        forecast_url = (
            f"{self.settings.weather_forecast_url}"
            f"?latitude={loc.latitude}&longitude={loc.longitude}"
            f"&current=temperature_2m,weather_code"
            f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            f"&timezone=auto"
        )

        try:
            data = await asyncio.to_thread(self._http_get_json, forecast_url)
            daily = data.get("daily", {})

            daily_codes = daily.get("weather_code", [])
            daily_probs = daily.get("precipitation_probability_max", [])
            daily_max_temps = daily.get("temperature_2m_max", [])

            idx = min(1, len(daily_codes) - 1) if len(daily_codes) > 1 else 0
            wmo_code = daily_codes[idx] if daily_codes else None
            condition = get_wmo_description(wmo_code)
            precip_prob = int(daily_probs[idx]) if daily_probs and daily_probs[idx] is not None else None
            max_temp = float(daily_max_temps[idx]) if daily_max_temps and daily_max_temps[idx] is not None else None

            city_label = loc.name
            if loc.country:
                city_label = f"{loc.name}, {loc.country}"

            return WeatherReport(
                city=city_label,
                temp_c=max_temp,
                condition=condition,
                precip_probability_pct=precip_prob,
                is_forecast=True,
                source="open-meteo",
                raw_payload=data,
            )
        except Exception as exc:
            logger.warning("Open-Meteo forecast failed for '%s': %s", city_name, exc)
            if self.settings.weather_fallback_to_web_agent:
                return await self._fallback_web_search(city_name, is_forecast=True)
            return WeatherReport(
                city=city_name,
                condition="Forecast unavailable",
                is_forecast=True,
                source="error",
            )

    async def _fallback_web_search(self, city_name: str, is_forecast: bool = False) -> WeatherReport:
        """Fallback path using WebAgent to search DuckDuckGo / Google."""
        query = f"weather in {city_name}"
        if is_forecast:
            query = f"weather forecast for {city_name}"

        try:
            res = None
            if hasattr(self.web_agent, "search_web") and callable(self.web_agent.search_web):
                maybe_coro = self.web_agent.search_web(query, max_results=3)
                res = await maybe_coro if asyncio.iscoroutine(maybe_coro) or hasattr(maybe_coro, "__await__") else maybe_coro
            elif hasattr(self.web_agent, "search") and callable(self.web_agent.search):
                maybe_coro = self.web_agent.search(query, max_results=3)
                res = await maybe_coro if asyncio.iscoroutine(maybe_coro) or hasattr(maybe_coro, "__await__") else maybe_coro

            if isinstance(res, list):
                results = res
            elif hasattr(res, "data") and isinstance(res.data, dict):
                results = res.data.get("results", [])
            else:
                results = []

            if not results:
                return WeatherReport(
                    city=city_name,
                    condition="Weather information could not be retrieved",
                    is_forecast=is_forecast,
                    source="web_agent_fallback",
                )

            # Combine snippets to extract temperature and conditions
            combined_text = " ".join(
                f"{r.get('title', '') if isinstance(r, dict) else getattr(r, 'title', '')}. {r.get('snippet', '') if isinstance(r, dict) else getattr(r, 'snippet', '')}"
                for r in results
            )

            # Regex search for temperature like 24°C or 75°F
            temp_c = None
            temp_match = re.search(r"(-?\d+)\s*(?:°\s*C|deg(?:rees)?\s*C)", combined_text, re.IGNORECASE)
            if temp_match:
                temp_c = float(temp_match.group(1))
            else:
                f_match = re.search(r"(-?\d+)\s*(?:°\s*F|deg(?:rees)?\s*F)", combined_text, re.IGNORECASE)
                if f_match:
                    temp_f = float(f_match.group(1))
                    temp_c = round((temp_f - 32) * 5.0 / 9.0, 1)

            # Extract condition keywords
            condition = "Weather summary retrieved from web"
            if "rain" in combined_text.lower():
                condition = "Rainy conditions"
            elif "sunny" in combined_text.lower() or "clear" in combined_text.lower():
                condition = "Sunny / Clear"
            elif "cloudy" in combined_text.lower():
                condition = "Cloudy"
            elif "thunderstorm" in combined_text.lower() or "storm" in combined_text.lower():
                condition = "Stormy"

            snippets_payload = [
                r.to_dict() if hasattr(r, "to_dict") else (r if isinstance(r, dict) else str(r))
                for r in results
            ]

            return WeatherReport(
                city=city_name,
                temp_c=temp_c,
                condition=condition,
                is_forecast=is_forecast,
                source="web_agent_fallback",
                raw_payload={"snippets": snippets_payload},
            )
        except Exception as exc:
            logger.error("WebAgent weather search failed: %s", exc)
            return WeatherReport(
                city=city_name,
                condition="Weather lookup failed",
                is_forecast=is_forecast,
                source="error",
            )
