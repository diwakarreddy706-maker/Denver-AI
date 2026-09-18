"""Fastest-Route Navigation & Directions Engine for Denver AI Assistant.

Integrates OSRM (Open Source Routing Machine), Google Maps Directions, and hands-free
browser map visualization.
"""

from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from typing import Any

from denver.automation.weather import WeatherService
from denver.config.settings import DenverSettings, get_settings
from denver.logging.logger import get_logger

logger = get_logger("automation.navigation")


def format_duration(seconds: float) -> str:
    """Format duration in seconds into clean human-readable text."""
    if seconds < 60:
        return f"{int(seconds)} sec"
    total_minutes = int(round(seconds / 60.0))
    if total_minutes < 60:
        return f"{total_minutes} min"
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if minutes == 0:
        return f"{hours} hr"
    return f"{hours} hr {minutes} min"


def format_distance(meters: float) -> str:
    """Format distance in meters into km or meters."""
    if meters < 1000:
        return f"{int(meters)} m"
    km = round(meters / 1000.0, 1)
    if km.is_integer():
        return f"{int(km)} km"
    return f"{km} km"


def build_google_maps_url(origin: str, destination: str, mode: str = "driving") -> str:
    """Generate direct Google Maps navigation URL for desktop browsers."""
    mode_map = {
        "driving": "driving",
        "car": "driving",
        "walking": "walking",
        "walk": "walking",
        "cycling": "bicycling",
        "bike": "bicycling",
        "transit": "transit",
        "bus": "transit",
        "train": "transit",
    }
    travel_mode = mode_map.get(mode.lower().strip(), "driving")
    orig_encoded = urllib.parse.quote(origin.strip())
    dest_encoded = urllib.parse.quote(destination.strip())
    return f"https://www.google.com/maps/dir/?api=1&origin={orig_encoded}&destination={dest_encoded}&travelmode={travel_mode}"


@dataclass
class RouteResult:
    """Structured routing and navigation result."""

    origin: str
    destination: str
    mode: str = "driving"
    duration_seconds: float | None = None
    distance_meters: float | None = None
    formatted_duration: str = ""
    formatted_distance: str = ""
    spoken_summary: str = ""
    maps_url: str = ""
    source: str = "osrm"
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "mode": self.mode,
            "duration_seconds": self.duration_seconds,
            "distance_meters": self.distance_meters,
            "formatted_duration": self.formatted_duration,
            "formatted_distance": self.formatted_distance,
            "spoken_summary": self.spoken_summary,
            "maps_url": self.maps_url,
            "source": self.source,
        }


class NavigationService:
    """Fastest-route calculation and navigation engine."""

    def __init__(
        self,
        settings: DenverSettings | None = None,
        weather_service: WeatherService | None = None,
        location_service: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.weather_service = weather_service or WeatherService(settings=self.settings)
        self.location_service = location_service
        self._last_route: dict[str, Any] | None = None

    def _http_get_json(self, url: str, timeout: float | None = None) -> dict[str, Any]:
        """Perform synchronous HTTP GET request returning parsed JSON."""
        tout = timeout or self.settings.osrm_timeout_seconds
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

    async def calculate_route(
        self,
        origin: str,
        destination: str,
        mode: str = "driving",
        open_in_browser: bool | None = None,
    ) -> RouteResult:
        """Calculate travel duration and distance between origin and destination."""
        clean_origin = origin.strip() if origin else "here"
        clean_dest = destination.strip()
        clean_mode = mode.lower().strip() or "driving"

        # Resolve 'here' / 'current location' using LocationService
        if clean_origin.lower() in {"", "here", "current", "current location", "my location", "current place"}:
            if self.location_service:
                loc_res = await self.location_service.detect_current_location()
                if loc_res.success:
                    clean_origin = loc_res.formatted_address or loc_res.city or f"{loc_res.latitude},{loc_res.longitude}"

        should_open = open_in_browser if open_in_browser is not None else self.settings.route_open_in_browser
        maps_url = build_google_maps_url(clean_origin, clean_dest, clean_mode)

        # Store recent query for conversational mode-switching follow-ups
        self._last_route = {
            "origin": clean_origin,
            "destination": clean_dest,
            "mode": clean_mode,
        }

        # 1. Handle Public Transit (OSRM does not support transit schedules)
        if clean_mode in ("transit", "bus", "train", "metro", "subway"):
            spoken = (
                f"Public transit schedules from {clean_origin} to {clean_dest} require live transit feeds. "
                f"Opening the Google Maps transit route on your screen."
            )
            if should_open:
                await self.open_route_in_browser(clean_origin, clean_dest, clean_mode)
            return RouteResult(
                origin=clean_origin,
                destination=clean_dest,
                mode=clean_mode,
                spoken_summary=spoken,
                maps_url=maps_url,
                source="transit_redirect",
            )

        # 2. Check Optional Google Maps Directions API if configured
        if self.settings.google_maps_enabled and self.settings.google_maps_api_key:
            try:
                gmaps_res = await self._query_google_maps(clean_origin, clean_dest, clean_mode, maps_url)
                if gmaps_res:
                    if should_open:
                        await self.open_route_in_browser(clean_origin, clean_dest, clean_mode)
                    return gmaps_res
            except Exception as exc:
                logger.warning("Google Maps Directions query failed, falling back to OSRM: %s", exc)

        # 3. Primary Path: OSRM Routing Backend
        osrm_base = self.settings.osrm_base_url.rstrip("/") if self.settings.osrm_base_url else ""
        if not osrm_base:
            # Fallback to direct maps view when no dedicated OSRM server is configured
            spoken = f"Directions from {clean_origin} to {clean_dest} ({clean_mode}). Opening the interactive map."
            if should_open:
                await self.open_route_in_browser(clean_origin, clean_dest, clean_mode)
            return RouteResult(
                origin=clean_origin,
                destination=clean_dest,
                mode=clean_mode,
                spoken_summary=spoken,
                maps_url=maps_url,
                source="browser_only",
            )

        # Geocode origin and destination using shared geocoder
        orig_geo, dest_geo = await asyncio.gather(
            self.weather_service.geocode(clean_origin),
            self.weather_service.geocode(clean_dest),
            return_exceptions=True,
        )

        if not orig_geo or isinstance(orig_geo, Exception) or not dest_geo or isinstance(dest_geo, Exception):
            spoken = f"Could not precisely resolve coordinates for {clean_origin} or {clean_dest}. Opening Google Maps route."
            if should_open:
                await self.open_route_in_browser(clean_origin, clean_dest, clean_mode)
            return RouteResult(
                origin=clean_origin,
                destination=clean_dest,
                mode=clean_mode,
                spoken_summary=spoken,
                maps_url=maps_url,
                source="geocoding_fallback",
            )

        profile_map = {
            "driving": "driving",
            "car": "driving",
            "walking": "walking",
            "walk": "walking",
            "cycling": "bike",
            "bike": "bike",
            "bicycle": "bike",
        }
        profile = profile_map.get(clean_mode, "driving")
        route_url = f"{osrm_base}/route/v1/{profile}/{orig_geo.longitude},{orig_geo.latitude};{dest_geo.longitude},{dest_geo.latitude}?overview=false"

        try:
            data = await asyncio.to_thread(self._http_get_json, route_url)
            routes = data.get("routes", [])
            if not routes:
                spoken = f"No direct route found between {clean_origin} and {clean_dest}. Opening Google Maps."
                if should_open:
                    await self.open_route_in_browser(clean_origin, clean_dest, clean_mode)
                return RouteResult(
                    origin=clean_origin,
                    destination=clean_dest,
                    mode=clean_mode,
                    spoken_summary=spoken,
                    maps_url=maps_url,
                    source="osrm_no_route",
                )

            top_route = routes[0]
            duration_sec = float(top_route.get("duration", 0.0))
            distance_m = float(top_route.get("distance", 0.0))

            f_dur = format_duration(duration_sec)
            f_dist = format_distance(distance_m)

            mode_phrase = "drive" if profile == "driving" else ("walk" if profile == "walking" else "bike ride")
            spoken = (
                f"The fastest route from {clean_origin} to {clean_dest} is about {f_dist}, "
                f"taking approximately {f_dur} by {mode_phrase} (based on typical travel time, no live traffic data)."
            )

            if should_open:
                await self.open_route_in_browser(clean_origin, clean_dest, clean_mode)

            return RouteResult(
                origin=clean_origin,
                destination=clean_dest,
                mode=clean_mode,
                duration_seconds=duration_sec,
                distance_meters=distance_m,
                formatted_duration=f_dur,
                formatted_distance=f_dist,
                spoken_summary=spoken,
                maps_url=maps_url,
                source="osrm",
                raw_payload=data,
            )

        except Exception as exc:
            logger.warning("OSRM route calculation error: %s", exc)
            spoken = f"Directions from {clean_origin} to {clean_dest}. Opening Google Maps navigation."
            if should_open:
                await self.open_route_in_browser(clean_origin, clean_dest, clean_mode)
            return RouteResult(
                origin=clean_origin,
                destination=clean_dest,
                mode=clean_mode,
                spoken_summary=spoken,
                maps_url=maps_url,
                source="osrm_error",
            )

    async def _query_google_maps(self, origin: str, dest: str, mode: str, maps_url: str) -> RouteResult | None:
        """Query Google Maps Directions REST API."""
        api_key = self.settings.google_maps_api_key
        url = (
            f"https://maps.googleapis.com/maps/api/directions/json"
            f"?origin={urllib.parse.quote(origin)}&destination={urllib.parse.quote(dest)}"
            f"&mode={mode}&key={api_key}"
        )
        data = await asyncio.to_thread(self._http_get_json, url)
        routes = data.get("routes", [])
        if not routes:
            return None

        legs = routes[0].get("legs", [])
        if not legs:
            return None

        leg = legs[0]
        duration_sec = float(leg.get("duration", {}).get("value", 0))
        distance_m = float(leg.get("distance", {}).get("value", 0))
        f_dur = leg.get("duration", {}).get("text", format_duration(duration_sec))
        f_dist = leg.get("distance", {}).get("text", format_distance(distance_m))

        spoken = f"The fastest route from {origin} to {dest} is {f_dist}, taking about {f_dur} via Google Maps."
        return RouteResult(
            origin=origin,
            destination=dest,
            mode=mode,
            duration_seconds=duration_sec,
            distance_meters=distance_m,
            formatted_duration=f_dur,
            formatted_distance=f_dist,
            spoken_summary=spoken,
            maps_url=maps_url,
            source="google_maps",
            raw_payload=data,
        )

    async def open_route_in_browser(self, origin: str, destination: str, mode: str = "driving") -> bool:
        """Open the visual Google Maps directions page in default desktop browser."""
        url = build_google_maps_url(origin, destination, mode)
        try:
            await asyncio.to_thread(webbrowser.open, url)
            return True
        except Exception as exc:
            logger.warning("Could not launch browser navigation URL: %s", exc)
            return False

    async def switch_last_route_mode(self, new_mode: str) -> RouteResult:
        """Re-run the last requested route query with a new travel mode."""
        if not self._last_route:
            return RouteResult(
                origin="",
                destination="",
                mode=new_mode,
                spoken_summary="No previous route request found to change travel mode.",
                source="error",
            )
        return await self.calculate_route(
            origin=self._last_route["origin"],
            destination=self._last_route["destination"],
            mode=new_mode,
        )
