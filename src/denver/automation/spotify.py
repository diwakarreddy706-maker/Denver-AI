"""Denver AI Assistant — Spotify Voice Controller & Media Key Automation Subsystem."""

from __future__ import annotations

import os
import time
import urllib.parse
import webbrowser
from typing import Any

from denver.automation.models import AutomationResult, AutomationRisk
from denver.logging.logger import get_logger

logger = get_logger("automation.spotify")

# Windows Virtual Key Codes for Media Controls
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3


class SpotifyController:
    """Controls Spotify desktop/web playback via native Windows virtual media keys and URI protocols."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def _is_mock_env(is_mock: bool = False) -> bool:
        """Determine whether automation should run in safe simulated mock mode."""
        return (
            is_mock
            or os.environ.get("DENVER_MOCK_AUTOMATION", "").lower() in ("true", "1", "yes")
            or "PYTEST_CURRENT_TEST" in os.environ
        )

    def _send_media_key(self, vk_code: int) -> None:
        """Send native Windows virtual media key press and release event."""
        import ctypes

        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)

    def play_pause(self, is_mock: bool = False) -> AutomationResult:
        """Toggle Spotify or active system media playback (Play / Pause)."""
        if self._is_mock_env(is_mock):
            logger.info("[MOCK] Triggered Spotify Play/Pause toggle.")
            return AutomationResult(
                success=True,
                action="spotify_play_pause",
                target="Spotify",
                message="Toggled Spotify playback (Play/Pause).",
                data={"vk_code": hex(VK_MEDIA_PLAY_PAUSE), "mock": True},
                risk_level=AutomationRisk.LOW,
            )

        try:
            self._send_media_key(VK_MEDIA_PLAY_PAUSE)
            logger.info("Sent VK_MEDIA_PLAY_PAUSE to active media player.")
            return AutomationResult(
                success=True,
                action="spotify_play_pause",
                target="Spotify",
                message="Toggled Spotify playback (Play/Pause).",
                data={"vk_code": hex(VK_MEDIA_PLAY_PAUSE)},
                risk_level=AutomationRisk.LOW,
            )
        except Exception as exc:
            logger.error("Failed to send media key VK_MEDIA_PLAY_PAUSE: %s", exc)
            return AutomationResult(
                success=False,
                action="spotify_play_pause",
                target="Spotify",
                message=f"Could not toggle Spotify playback: {exc}",
                error=str(exc),
                risk_level=AutomationRisk.LOW,
            )

    def next_track(self, is_mock: bool = False) -> AutomationResult:
        """Skip to the next song/track."""
        if self._is_mock_env(is_mock):
            logger.info("[MOCK] Skipped to next track.")
            return AutomationResult(
                success=True,
                action="spotify_next_track",
                target="Spotify",
                message="Skipped to next track on Spotify.",
                data={"vk_code": hex(VK_MEDIA_NEXT_TRACK), "mock": True},
                risk_level=AutomationRisk.LOW,
            )

        try:
            self._send_media_key(VK_MEDIA_NEXT_TRACK)
            logger.info("Sent VK_MEDIA_NEXT_TRACK.")
            return AutomationResult(
                success=True,
                action="spotify_next_track",
                target="Spotify",
                message="Skipped to next track on Spotify.",
                data={"vk_code": hex(VK_MEDIA_NEXT_TRACK)},
                risk_level=AutomationRisk.LOW,
            )
        except Exception as exc:
            logger.error("Failed to send VK_MEDIA_NEXT_TRACK: %s", exc)
            return AutomationResult(
                success=False,
                action="spotify_next_track",
                target="Spotify",
                message=f"Could not skip track: {exc}",
                error=str(exc),
                risk_level=AutomationRisk.LOW,
            )

    def previous_track(self, is_mock: bool = False) -> AutomationResult:
        """Return to the previous song/track."""
        if self._is_mock_env(is_mock):
            logger.info("[MOCK] Returned to previous track.")
            return AutomationResult(
                success=True,
                action="spotify_previous_track",
                target="Spotify",
                message="Returned to previous track on Spotify.",
                data={"vk_code": hex(VK_MEDIA_PREV_TRACK), "mock": True},
                risk_level=AutomationRisk.LOW,
            )

        try:
            self._send_media_key(VK_MEDIA_PREV_TRACK)
            logger.info("Sent VK_MEDIA_PREV_TRACK.")
            return AutomationResult(
                success=True,
                action="spotify_previous_track",
                target="Spotify",
                message="Returned to previous track on Spotify.",
                data={"vk_code": hex(VK_MEDIA_PREV_TRACK)},
                risk_level=AutomationRisk.LOW,
            )
        except Exception as exc:
            logger.error("Failed to send VK_MEDIA_PREV_TRACK: %s", exc)
            return AutomationResult(
                success=False,
                action="spotify_previous_track",
                target="Spotify",
                message=f"Could not return to previous track: {exc}",
                error=str(exc),
                risk_level=AutomationRisk.LOW,
            )

    def play_query(self, query: str, is_mock: bool = False) -> AutomationResult:
        """Search and play a song, artist, album, or playlist on Spotify."""
        clean_q = query.strip()
        encoded = urllib.parse.quote(clean_q)
        uri = f"spotify:search:{encoded}"
        web_url = f"https://open.spotify.com/search/{encoded}"

        if self._is_mock_env(is_mock):
            logger.info("[MOCK] Searching Spotify for: '%s'", clean_q)
            return AutomationResult(
                success=True,
                action="spotify_play_query",
                target=f"Spotify ({clean_q})",
                message=f"Searching and playing '{clean_q}' on Spotify.",
                data={"query": clean_q, "uri": uri, "web_url": web_url, "mock": True},
                risk_level=AutomationRisk.LOW,
            )

        try:
            os.startfile(uri)  # pylint: disable=no-member
            logger.info("Launched Spotify search URI: %s", uri)
            return AutomationResult(
                success=True,
                action="spotify_play_query",
                target=f"Spotify ({clean_q})",
                message=f"Playing '{clean_q}' on Spotify.",
                data={"query": clean_q, "uri": uri, "web_url": web_url},
                risk_level=AutomationRisk.LOW,
            )
        except Exception as exc:
            logger.warning("Failed to open Spotify URI (%s); launching Web player.", exc)
            webbrowser.open(web_url)
            return AutomationResult(
                success=True,
                action="spotify_play_query",
                target=f"Spotify ({clean_q}) (Web)",
                message=f"Opened Spotify Web search for '{clean_q}'.",
                data={"query": clean_q, "url": web_url},
                risk_level=AutomationRisk.LOW,
            )
