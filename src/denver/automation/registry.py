"""Allowlisted Application & Site Catalogs for Denver Desktop Automation."""

from __future__ import annotations

from typing import Mapping
from denver.automation.models import ApplicationTarget, BrowserTarget


class AutomationRegistry:
    """Registry of trusted, allowlisted desktop applications and known web sites."""

    def __init__(self) -> None:
        self._applications: dict[str, ApplicationTarget] = {}
        self._known_sites: dict[str, str] = {}
        self._register_default_applications()
        self._register_default_sites()

    def _register_default_applications(self) -> None:
        defaults = [
            ApplicationTarget(
                app_id="notepad",
                display_name="Notepad",
                executable="notepad.exe",
                aliases=("editor", "text editor", "notes"),
                process_names=("notepad.exe",),
                description="Standard Windows text editor",
            ),
            ApplicationTarget(
                app_id="calculator",
                display_name="Calculator",
                executable="calc.exe",
                aliases=("calc", "calculator app"),
                process_names=("CalculatorApp.exe", "calc.exe"),
                description="Windows desktop calculator",
            ),
            ApplicationTarget(
                app_id="explorer",
                display_name="File Explorer",
                executable="explorer.exe",
                aliases=("file explorer", "files", "my computer", "folders"),
                process_names=("explorer.exe",),
                description="Windows file and folder navigation",
            ),
            ApplicationTarget(
                app_id="task_manager",
                display_name="Task Manager",
                executable="taskmgr.exe",
                aliases=("task manager", "taskmgr", "taskman", "process manager"),
                process_names=("Taskmgr.exe",),
                description="Windows system task and performance monitor",
            ),
            ApplicationTarget(
                app_id="settings",
                display_name="Windows Settings",
                executable="ms-settings:",
                aliases=("windows settings", "pc settings", "system settings"),
                is_uri_scheme=True,
                description="Windows modern settings dashboard",
            ),
            ApplicationTarget(
                app_id="cmd",
                display_name="Command Prompt",
                executable="cmd.exe",
                aliases=("command prompt", "terminal", "console"),
                process_names=("cmd.exe",),
                description="Windows command line interface",
            ),
            ApplicationTarget(
                app_id="browser",
                display_name="Web Browser",
                executable="default_browser",
                aliases=("web browser", "internet", "chrome", "google chrome", "edge", "firefox"),
                description="Default operating system web browser",
            ),
            ApplicationTarget(
                app_id="paint",
                display_name="Paint",
                executable="mspaint.exe",
                aliases=("mspaint", "draw", "drawing"),
                process_names=("mspaint.exe", "PaintApp.exe"),
                description="Windows drawing and image editor",
            ),
            ApplicationTarget(
                app_id="snipping_tool",
                display_name="Snipping Tool",
                executable="snippingtool.exe",
                aliases=("snip", "snipper", "screen capture tool"),
                process_names=("SnippingTool.exe", "ScreenClippingHost.exe"),
                description="Windows screen clipping utility",
            ),
            ApplicationTarget(
                app_id="whatsapp",
                display_name="WhatsApp",
                executable="whatsapp:",
                aliases=(
                    "whatsapp", "whatapp", "whatsap", "watshap", "watsapp",
                    "wapp", "whats app", "wa", "whatsapp desktop", "whatsapp messenger"
                ),
                process_names=("WhatsApp.exe", "WhatsApp.Root.exe"),
                is_uri_scheme=True,
                description="WhatsApp Desktop messaging client",
            ),
            ApplicationTarget(
                app_id="spotify",
                display_name="Spotify",
                executable="spotify:",
                aliases=("spotify", "spotfy", "spodify", "music", "spotify music", "spotify player"),
                process_names=("Spotify.exe",),
                is_uri_scheme=True,
                description="Spotify desktop music player",
            ),
            ApplicationTarget(
                app_id="vscode",
                display_name="Visual Studio Code",
                executable="code",
                aliases=("vscode", "vs code", "code", "visual studio code"),
                process_names=("Code.exe",),
                description="Visual Studio Code development editor",
            ),
            ApplicationTarget(
                app_id="discord",
                display_name="Discord",
                executable="discord:",
                aliases=("discord", "discord app"),
                process_names=("Discord.exe",),
                is_uri_scheme=True,
                description="Discord voice and chat client",
            ),
            ApplicationTarget(
                app_id="telegram",
                display_name="Telegram",
                executable="tg:",
                aliases=("telegram", "tg", "telegram messenger"),
                process_names=("Telegram.exe",),
                is_uri_scheme=True,
                description="Telegram desktop messaging client",
            ),
            ApplicationTarget(
                app_id="terminal",
                display_name="Windows Terminal",
                executable="wt.exe",
                aliases=("terminal", "windows terminal", "wt", "powershell terminal"),
                process_names=("WindowsTerminal.exe", "wt.exe"),
                description="Windows tabbed command terminal",
            ),
        ]
        for app in defaults:
            self.register_application(app)

    def _register_default_sites(self) -> None:
        sites = {
            "google": "https://www.google.com",
            "youtube": "https://www.youtube.com",
            "github": "https://www.github.com",
            "gmail": "https://mail.google.com",
            "reddit": "https://www.reddit.com",
            "wikipedia": "https://www.wikipedia.org",
            "bing": "https://www.bing.com",
            "duckduckgo": "https://duckduckgo.com",
            "stackoverflow": "https://stackoverflow.com",
            "whatsapp": "https://web.whatsapp.com",
            "whatsapp web": "https://web.whatsapp.com",
            "spotify": "https://open.spotify.com",
            "discord": "https://discord.com/app",
            "chatgpt": "https://chatgpt.com",
            "claude": "https://claude.ai",
        }
        self._known_sites.update(sites)

    def register_application(self, app: ApplicationTarget, allow_override: bool = False) -> None:
        """Add an allowlisted application target."""
        key = app.app_id.lower()
        if not allow_override and key in self._applications:
            raise ValueError(f"Application '{app.app_id}' is already registered.")
        self._applications[key] = app

    def get_application(self, query: str) -> ApplicationTarget | None:
        """Alias for find_application."""
        return self.find_application(query)

    def find_application(self, query: str) -> ApplicationTarget | None:
        """Look up an application by ID or registered alias. Rejects arbitrary filepaths."""
        import re
        q = query.strip().lower()
        cleaned = re.sub(r"^(?:the|my|a|an)\s+", "", q).strip()
        cleaned = re.sub(r"\s+(?:app|application|program)$", "", cleaned).strip()

        for test_q in (q, cleaned):
            if not test_q:
                continue
            if test_q in self._applications:
                return self._applications[test_q]

            for app in self._applications.values():
                if app.matches(test_q):
                    return app
        return None

    def list_applications(self) -> list[ApplicationTarget]:
        """Return all allowlisted applications."""
        return list(self._applications.values())

    def get_known_site(self, site_name: str) -> BrowserTarget | None:
        """Look up known site and return BrowserTarget model."""
        url = self._known_sites.get(site_name.strip().lower())
        if not url:
            for k, u in self._known_sites.items():
                if site_name.strip().lower() == k.lower():
                    return BrowserTarget(url=u, site_name=k, is_allowlisted=True)
            return None
        return BrowserTarget(url=url, site_name=site_name, is_allowlisted=True)

    def register_known_site(self, site: BrowserTarget) -> None:
        """Register a known site target."""
        key = site.site_name.strip().lower() or site.url
        self._known_sites[key] = site.url
        for alias in site.aliases:
            self._known_sites[alias.strip().lower()] = site.url

    def resolve_known_site(self, site_name: str) -> str | None:
        """Resolve common shorthand names to validated canonical URLs."""
        return self._known_sites.get(site_name.strip().lower())

    def list_known_sites(self) -> Mapping[str, str]:
        """Return copy of all registered known web destinations."""
        return dict(self._known_sites)
