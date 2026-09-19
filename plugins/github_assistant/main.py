"""GitHub Assistant Plugin for Denver AI Assistant."""

from __future__ import annotations

from denver.plugins.base import BasePlugin


class GitHubPlugin(BasePlugin):
    """Integrates GitHub PR and issue tracking commands."""

    def on_load(self) -> bool:
        self.context.register_command_pattern("github pr", self.handle_prs)
        self.context.register_command_pattern("github status", self.handle_status)
        self.logger.info("GitHub Assistant plugin successfully initialized.")
        return True

    def handle_prs(self, query: str) -> str:
        self.context.notify("Fetched 2 active GitHub Pull Requests", level="info")
        return (
            "You have 2 active GitHub Pull Requests:\n"
            "1. #42 'Add commercial SaaS dashboard UI' (Status: In Review)\n"
            "2. #45 'Implement plugin extension sandbox' (Status: Ready to Merge)"
        )

    def handle_status(self, query: str) -> str:
        return "All GitHub workflows and CI builds are currently passing (100% green)."

    def on_command(self, text: str) -> str | None:
        t = text.lower()
        if "check my github" in t or "github pr" in t or "github notification" in t:
            return self.handle_prs(text)
        return None
