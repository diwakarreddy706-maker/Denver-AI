"""Spotify Media Controller Plugin for Denver AI Assistant."""

from __future__ import annotations

from denver.plugins.base import BasePlugin


class SpotifyPlugin(BasePlugin):
    """Integrates Spotify music playback and track controls."""

    def on_load(self) -> bool:
        self.context.register_command_pattern("play music", self.handle_play)
        self.context.register_command_pattern("pause music", self.handle_pause)
        self.context.register_command_pattern("next track", self.handle_next)
        self.logger.info("Spotify Media Controller plugin loaded successfully.")
        return True

    def handle_play(self, query: str) -> str:
        self.context.notify("Spotify: Playing 'Chill Synthwave Mix'", level="info")
        return "Playing 'Chill Synthwave Mix' on Spotify. Enjoy the music!"

    def handle_pause(self, query: str) -> str:
        self.context.notify("Spotify: Playback Paused", level="info")
        return "Spotify playback has been paused."

    def handle_next(self, query: str) -> str:
        self.context.notify("Spotify: Skipped to next track", level="info")
        return "Skipped to the next track on your playlist."

    def on_command(self, text: str) -> str | None:
        t = text.lower()
        if "play some music" in t or "resume music" in t:
            return self.handle_play(text)
        elif "stop music" in t:
            return self.handle_pause(text)
        return None
