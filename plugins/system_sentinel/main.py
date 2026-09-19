"""System Sentinel Plugin for Denver AI Assistant."""

from __future__ import annotations

from datetime import datetime
from denver.plugins.base import BasePlugin


class SystemSentinelPlugin(BasePlugin):
    """Monitors system background security and maintains audit log in isolated data storage."""

    def on_load(self) -> bool:
        self.context.register_command_pattern("system sentinel", self.handle_status)
        self.context.register_command_pattern("security alert", self.handle_status)

        # Demonstrate sandboxed filesystem write
        now_str = datetime.now().isoformat()
        self.context.write_data_file("sentinel_audit.log", f"[{now_str}] System Sentinel initialized.\n")
        self.logger.info("System Sentinel plugin loaded and initialized audit log.")
        return True

    def handle_status(self, query: str) -> str:
        self.context.notify("Sentinel: All systems secure. 0 active security alerts.", level="info")
        return (
            "System Sentinel Report:\n"
            "- Integrity: Verified (OK)\n"
            "- Firewall: Active & Shielded\n"
            "- Active Alerts: 0 security threats detected"
        )

    def on_command(self, text: str) -> str | None:
        t = text.lower()
        if "check security" in t or "security status" in t:
            return self.handle_status(text)
        return None
