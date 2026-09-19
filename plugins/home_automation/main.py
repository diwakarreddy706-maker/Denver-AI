"""Smart Home & IoT Automation Plugin for Denver AI Assistant."""

from __future__ import annotations

import re
from denver.plugins.base import BasePlugin


class HomeAutomationPlugin(BasePlugin):
    """Controls smart lights, scene presets, and IoT appliances."""

    def on_load(self) -> bool:
        self.context.register_command_pattern("dim.*lights", self.handle_dim_lights)
        self.context.register_command_pattern("turn on.*lights", self.handle_turn_on)
        self.context.register_command_pattern("turn off.*lights", self.handle_turn_off)
        self.logger.info("Home Automation plugin loaded successfully.")
        return True

    def handle_dim_lights(self, query: str) -> str:
        self.context.notify("Smart Home: Living room lights dimmed to 30%", level="info")
        return "I've dimmed the living room lights to 30% for a relaxing ambient vibe."

    def handle_turn_on(self, query: str) -> str:
        target = "desk" if "desk" in query.lower() else "room"
        self.context.notify(f"Smart Home: {target.title()} lights turned ON", level="info")
        return f"Turned on the {target} lights."

    def handle_turn_off(self, query: str) -> str:
        self.context.notify("Smart Home: All lights turned OFF", level="info")
        return "All lights have been powered off."

    def on_command(self, text: str) -> str | None:
        t = text.lower()
        if "dim living room lights" in t:
            return self.handle_dim_lights(text)
        elif "turn on desk lights" in t or "turn on lights" in t:
            return self.handle_turn_on(text)
        elif "turn off lights" in t:
            return self.handle_turn_off(text)
        return None
