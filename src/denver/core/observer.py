"""Desktop Observer Engine for Denver Pillar 2: Continuous Desktop & Window Awareness."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Any

from denver.automation.models import WindowInfo
from denver.automation.windows import WindowsNativeAPI
from denver.logging.logger import get_logger
from denver.runtime.event_bus import DenverEventBus, get_event_bus
from denver.runtime.events import ActiveWindowChanged

logger = get_logger("core.observer")


@unique
class WorkspaceCategory(str, Enum):
    """Categorical classification of user workspace tasks."""

    DEVELOPMENT = "DEVELOPMENT"
    BROWSER = "BROWSER"
    TERMINAL = "TERMINAL"
    COMMUNICATION = "COMMUNICATION"
    MEDIA = "MEDIA"
    DOCUMENT = "DOCUMENT"
    SYSTEM = "SYSTEM"
    GENERAL = "GENERAL"


@dataclass(frozen=True)
class DesktopWindowContext:
    """Rich metadata describing the currently active desktop window and workspace."""

    hwnd: int = 0
    title: str = ""
    process_name: str = ""
    category: str = "GENERAL"
    active_file: str | None = None
    project_name: str | None = None
    dwell_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "hwnd": self.hwnd,
            "title": self.title,
            "process_name": self.process_name,
            "category": self.category,
            "active_file": self.active_file,
            "project_name": self.project_name,
            "dwell_seconds": round(self.dwell_seconds, 2),
        }


def _format_dwell(seconds: float) -> str:
    """Format dwell duration in seconds to human-readable string."""
    secs = int(seconds)
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    rem_secs = secs % 60
    if mins < 60:
        return f"{mins}m {rem_secs}s"
    hrs = mins // 60
    rem_mins = mins % 60
    return f"{hrs}h {rem_mins}m"


class DesktopObserverEngine:
    """Continuously observes the desktop foreground state, active application, and workspace context."""

    def __init__(
        self,
        native_api: Any | None = None,
        window_manager: Any | None = None,
        event_bus: DenverEventBus | None = None,
    ) -> None:
        self.native_api = native_api or WindowsNativeAPI()
        self.window_manager = window_manager
        self.event_bus = event_bus

        # Dwell and transition state tracking
        self._last_hwnd: int = 0
        self._last_title: str = ""
        self._last_process: str = ""
        self._last_category: str = "GENERAL"
        self._focus_start_time: float = time.time()

        # Known process classifications
        self._dev_processes = {
            "code.exe", "vscodium.exe", "pycharm64.exe", "idea64.exe",
            "clion64.exe", "devenv.exe", "sublime_text.exe", "atom.exe",
            "nvim.exe", "vim.exe", "cursor.exe",
        }
        self._browser_processes = {
            "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
            "opera.exe", "vivaldi.exe", "arc.exe",
        }
        self._terminal_processes = {
            "windowsterminal.exe", "cmd.exe", "powershell.exe",
            "pwsh.exe", "mintty.exe", "conhost.exe", "alacritty.exe",
            "warp.exe",
        }
        self._comm_processes = {
            "slack.exe", "discord.exe", "teams.exe", "ms-teams.exe",
            "whatsapp.exe", "telegram.exe", "signal.exe", "zoom.exe",
        }
        self._media_processes = {
            "spotify.exe", "vlc.exe", "wmplayer.exe", "foobar2000.exe",
        }
        self._doc_processes = {
            "winword.exe", "excel.exe", "powerpnt.exe", "notepad.exe",
            "acrobat.exe",
        }
        self._system_processes = {
            "explorer.exe", "taskmgr.exe", "systemsettings.exe",
        }

        # Regex patterns for extracting context from window titles
        # VS Code / Cursor: "● file.py - Project - Visual Studio Code" or "Project - Visual Studio Code"
        self._vscode_file_re = re.compile(
            r"^(?:●\s*)?([^\s\\/]+(?:\.[a-zA-Z0-9_\-]+)?)\s+-\s+(.+?)\s+-\s+(?:Visual Studio Code|VSCodium|Cursor)$",
            re.IGNORECASE,
        )
        self._vscode_proj_re = re.compile(
            r"^(?:●\s*)?(.+?)\s+-\s+(?:Visual Studio Code|VSCodium|Cursor)$",
            re.IGNORECASE,
        )
        # JetBrains: "[Project] - .../file.py [Project]" or "file.py – Project – PyCharm"
        self._jetbrains_re = re.compile(
            r"(?:\[(.+?)\]\s+-\s+)?(.+?\.[a-zA-Z0-9_\-]+)",
            re.IGNORECASE,
        )
        # Browser title cleanup: "Tab Title - Google Chrome"
        self._browser_tab_re = re.compile(
            r"^(.+?)\s+-\s+(?:Google Chrome|Microsoft Edge|Mozilla Firefox|Brave|Opera|Vivaldi)$",
            re.IGNORECASE,
        )

    def classify_window(self, title: str, process_name: str) -> tuple[str, str | None, str | None]:
        """Classify window into category, extracting active file and project if detectable.

        Returns:
            (category, active_file, project_name)
        """
        proc_lower = process_name.lower().strip()
        title_clean = title.strip()

        # 1. Development (VS Code, Cursor, JetBrains, Visual Studio)
        if proc_lower in self._dev_processes or "visual studio code" in title_clean.lower():
            m_file = self._vscode_file_re.match(title_clean)
            if m_file:
                return WorkspaceCategory.DEVELOPMENT.value, m_file.group(1).strip(), m_file.group(2).strip()
            m_proj = self._vscode_proj_re.match(title_clean)
            if m_proj:
                return WorkspaceCategory.DEVELOPMENT.value, None, m_proj.group(1).strip()
            return WorkspaceCategory.DEVELOPMENT.value, None, None

        # 2. Browser
        if proc_lower in self._browser_processes:
            m_tab = self._browser_tab_re.match(title_clean)
            tab_name = m_tab.group(1).strip() if m_tab else title_clean
            return WorkspaceCategory.BROWSER.value, None, tab_name

        # 3. Terminal
        if proc_lower in self._terminal_processes or "powershell" in title_clean.lower() or "cmd.exe" in title_clean.lower():
            return WorkspaceCategory.TERMINAL.value, None, None

        # 4. Communication
        if proc_lower in self._comm_processes:
            return WorkspaceCategory.COMMUNICATION.value, None, None

        # 5. Media
        if proc_lower in self._media_processes:
            return WorkspaceCategory.MEDIA.value, None, None

        # 6. Document / Office
        if proc_lower in self._doc_processes:
            return WorkspaceCategory.DOCUMENT.value, None, None

        # 7. System
        if proc_lower in self._system_processes:
            return WorkspaceCategory.SYSTEM.value, None, None

        return WorkspaceCategory.GENERAL.value, None, None

    def _fetch_raw_window(self) -> WindowInfo | None:
        """Fetch the raw foreground window via native_api or window_manager."""
        if self.native_api and hasattr(self.native_api, "get_foreground_window"):
            win = self.native_api.get_foreground_window()
            if win:
                return win
        if self.window_manager and hasattr(self.window_manager, "get_active_window"):
            return self.window_manager.get_active_window()
        return None

    def get_active_window(self) -> DesktopWindowContext | None:
        """Retrieve and track the currently active desktop window with dwell duration."""
        raw_win = self._fetch_raw_window()
        if not raw_win or not raw_win.title:
            return None

        now = time.time()
        category, active_file, project = self.classify_window(raw_win.title, raw_win.process_name)

        # Detect focus switch
        if raw_win.handle != self._last_hwnd or raw_win.title != self._last_title:
            if self._last_hwnd != 0 and self.event_bus:
                evt = ActiveWindowChanged(
                    old_app=self._last_process,
                    new_app=raw_win.process_name or raw_win.title,
                    window_title=raw_win.title,
                    category=category,
                )
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.event_bus.publish(evt))
                except RuntimeError:
                    try:
                        asyncio.run(self.event_bus.publish(evt))
                    except Exception:
                        pass

            self._last_hwnd = raw_win.handle
            self._last_title = raw_win.title
            self._last_process = raw_win.process_name
            self._last_category = category
            self._focus_start_time = now

        dwell = now - self._focus_start_time

        return DesktopWindowContext(
            hwnd=raw_win.handle,
            title=raw_win.title,
            process_name=raw_win.process_name,
            category=category,
            active_file=active_file,
            project_name=project,
            dwell_seconds=dwell,
        )

    # Alias for API compatibility
    observe_active_window = get_active_window

    def get_active_workspace_summary(self) -> str:
        """Format a zero-latency markdown context block for LLM prompt injection."""
        ctx = self.get_active_window()
        if not ctx or not ctx.title:
            return ""

        app_name = ctx.process_name or "Application"
        base_app = app_name.split(".")[0].capitalize() if "." in app_name else app_name

        meta_parts = []
        if ctx.active_file:
            meta_parts.append(f"File: {ctx.active_file}")
        if ctx.project_name:
            label = "Project" if ctx.category == WorkspaceCategory.DEVELOPMENT.value else "Tab"
            meta_parts.append(f"{label}: {ctx.project_name}")
        meta_str = f" ({', '.join(meta_parts)})" if meta_parts else ""


        dwell_str = _format_dwell(ctx.dwell_seconds)

        return (
            "[ACTIVE WORKSPACE CONTEXT]\n"
            f"- Focused Application: {base_app} ({app_name})\n"
            f"- Window Title: \"{ctx.title}\"\n"
            f"- Workspace Category: {ctx.category}{meta_str}\n"
            f"- Focus Dwell Duration: {dwell_str}"
        )

    def format_active_window_speech(self, ctx: DesktopWindowContext | None = None) -> str:
        """Format a natural speech response for voice queries regarding active window."""
        if ctx is None:
            ctx = self.get_active_window()

        if not ctx or not ctx.title:
            return "No application window is currently active on your desktop."

        app_name = ctx.process_name or "active window"
        base_app = app_name.split(".")[0].capitalize() if "." in app_name else app_name

        if ctx.category == WorkspaceCategory.DEVELOPMENT.value:
            if ctx.active_file and ctx.project_name:
                return f"You're in Visual Studio Code working on {ctx.active_file} in the {ctx.project_name} project."
            if ctx.project_name:
                return f"You're in Visual Studio Code in the {ctx.project_name} workspace."
            return f"You have {base_app} open for development."

        if ctx.category == WorkspaceCategory.BROWSER.value:
            tab = ctx.project_name or ctx.title
            return f"You're currently browsing {tab} in {base_app}."

        if ctx.category == WorkspaceCategory.TERMINAL.value:
            return f"You have the terminal focused with {ctx.title}."

        if ctx.category == WorkspaceCategory.MEDIA.value:
            return f"You're listening to or watching {base_app}."

        if ctx.category == WorkspaceCategory.COMMUNICATION.value:
            return f"You're currently in your communication app, {base_app}."

        return f"You are currently focused on {base_app} with window title '{ctx.title}'."
