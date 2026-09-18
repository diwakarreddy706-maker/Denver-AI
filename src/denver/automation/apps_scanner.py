"""Windows Application & Shortcuts Scanner for Denver AI Assistant."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from denver.logging.logger import get_logger

logger = get_logger("apps_scanner")

DEFAULT_APPS_PATH = Path("data/apps.json")


@dataclass
class AppShortcut:
    """Represents a discovered application, web shortcut, or folder."""

    name: str
    aliases: list[str] = field(default_factory=list)
    type: str = "executable"  # executable, url, folder, uwp
    path: str = ""
    url: str = ""
    category: str = "general"  # development, media, productivity, web, system, games
    launch_args: list[str] = field(default_factory=list)

    def matches(self, query: str) -> bool:
        """Check if search query matches name or any alias."""
        q = query.strip().lower()
        if not q:
            return False

        if q == self.name.lower() or q in self.name.lower():
            return True

        for alias in self.aliases:
            a = alias.strip().lower()
            if q == a or q in a or a in q:
                return True

        return False

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppShortcut:
        """Create from JSON dictionary."""
        return cls(
            name=str(data.get("name", "")).strip(),
            aliases=[str(a).strip().lower() for a in data.get("aliases", []) if a],
            type=str(data.get("type", "executable")),
            path=str(data.get("path", "")).strip(),
            url=str(data.get("url", "")).strip(),
            category=str(data.get("category", "general")),
            launch_args=[str(arg) for arg in data.get("launch_args", [])],
        )


class WindowsAppScanner:
    """Discovers installed Windows applications, Start Menu items, folders, and web tools."""

    def __init__(self, output_file: Path | str = DEFAULT_APPS_PATH) -> None:
        self.output_file = Path(output_file)

    def scan_all(self) -> list[AppShortcut]:
        """Scan all Windows Start Menu shortcuts, system tools, folders, and curated web apps."""
        apps_map: dict[str, AppShortcut] = {}

        # 1. Add Essential Web Shortcuts
        for web_app in self._get_curated_web_shortcuts():
            apps_map[web_app.name.lower()] = web_app

        # 2. Add Common User Folders
        for folder_app in self._get_common_folders():
            apps_map[folder_app.name.lower()] = folder_app

        # 3. Add Built-in Windows System Tools
        for sys_app in self._get_builtin_system_tools():
            apps_map[sys_app.name.lower()] = sys_app

        # 4. Scan Start Menu Shortcuts (.lnk files) via PowerShell
        start_menu_apps = self._scan_start_menu_powershell()
        for app in start_menu_apps:
            key = app.name.lower()
            if key not in apps_map:
                apps_map[key] = app

        result = list(apps_map.values())
        self.save_apps(result)
        logger.info("Discovered %d total applications and shortcuts.", len(result))
        return result

    def save_apps(self, apps: list[AppShortcut]) -> bool:
        """Save apps to data/apps.json atomically."""
        try:
            from denver.utils.atomic_write import atomic_write_json
            atomic_write_json(self.output_file, [a.to_dict() for a in apps])
            logger.info("Saved %d applications to %s", len(apps), self.output_file)
            return True
        except Exception as exc:
            logger.error("Failed to save apps to %s: %s", self.output_file, exc)
            return False

    def load_apps(self) -> list[AppShortcut]:
        """Load apps from data/apps.json, scanning if missing."""
        if not self.output_file.exists():
            return self.scan_all()

        try:
            with open(self.output_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [AppShortcut.from_dict(item) for item in data if isinstance(item, dict)]
        except Exception as exc:
            logger.warning("Failed to parse %s: %s; re-scanning...", self.output_file, exc)

        return self.scan_all()

    def _scan_start_menu_powershell(self) -> list[AppShortcut]:
        """Query Windows Start Menu shortcuts using PowerShell."""
        ps_script = """
$shortcuts = @()
$paths = @(
    "$env:ProgramData\\Microsoft\\Windows\\Start Menu\\Programs",
    "$env:AppData\\Microsoft\\Windows\\Start Menu\\Programs"
)
$wscript = New-Object -ComObject WScript.Shell

foreach ($p in $paths) {
    if (Test-Path $p) {
        Get-ChildItem -Path $p -Filter *.lnk -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                $target = $wscript.CreateShortcut($_.FullName).TargetPath
                if ($target -and ($target.EndsWith(".exe") -or (Test-Path $target))) {
                    $name = $_.BaseName
                    $shortcuts += [PSCustomObject]@{
                        Name = $name
                        Target = $target
                    }
                }
            } catch {}
        }
    }
}
$shortcuts | ConvertTo-Json -Compress
"""
        discovered: list[AppShortcut] = []
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                raw = json.loads(proc.stdout.strip())
                items = raw if isinstance(raw, list) else [raw]
                for item in items:
                    name = str(item.get("Name", "")).strip()
                    target = str(item.get("Target", "")).strip()
                    if not name or not target:
                        continue

                    # Filter out uninstallation links, help links, updates
                    lower_name = name.lower()
                    if any(bad in lower_name for bad in ("uninstall", "help", "readme", "documentation", "update")):
                        continue

                    # Generate smart aliases
                    aliases = [lower_name]
                    clean_name = re.sub(r"[^a-zA-Z0-9\s]", "", lower_name).strip()
                    if clean_name != lower_name:
                        aliases.append(clean_name)
                    # Add individual words if multi-word
                    parts = clean_name.split()
                    if len(parts) > 1:
                        aliases.append("".join(parts))

                    discovered.append(
                        AppShortcut(
                            name=name,
                            aliases=list(set(aliases)),
                            type="executable",
                            path=target,
                            category="productivity",
                        )
                    )
        except Exception as exc:
            logger.warning("PowerShell Start Menu scan encountered error: %s", exc)

        return discovered

    def _get_builtin_system_tools(self) -> list[AppShortcut]:
        """Standard Windows system executables and utilities."""
        return [
            AppShortcut(
                name="Calculator",
                aliases=["calculator", "calc", "math"],
                type="executable",
                path="calc.exe",
                category="system",
            ),
            AppShortcut(
                name="Notepad",
                aliases=["notepad", "text editor", "notes"],
                type="executable",
                path="notepad.exe",
                category="productivity",
            ),
            AppShortcut(
                name="Task Manager",
                aliases=["task manager", "taskmgr", "activity monitor"],
                type="executable",
                path="taskmgr.exe",
                category="system",
            ),
            AppShortcut(
                name="Command Prompt",
                aliases=["cmd", "command prompt", "terminal", "console"],
                type="executable",
                path="cmd.exe",
                category="development",
            ),
            AppShortcut(
                name="PowerShell",
                aliases=["powershell", "ps", "terminal"],
                type="executable",
                path="powershell.exe",
                category="development",
            ),
            AppShortcut(
                name="File Explorer",
                aliases=["file explorer", "explorer", "files", "my computer"],
                type="executable",
                path="explorer.exe",
                category="system",
            ),
            AppShortcut(
                name="Snipping Tool",
                aliases=["snipping tool", "screenshot tool", "snip"],
                type="executable",
                path="snippingtool.exe",
                category="system",
            ),
            AppShortcut(
                name="Settings",
                aliases=["windows settings", "settings", "control panel"],
                type="executable",
                path="ms-settings:",
                category="system",
            ),
        ]

    def _get_common_folders(self) -> list[AppShortcut]:
        """User directory locations."""
        user_home = Path.home()
        return [
            AppShortcut(
                name="Desktop Folder",
                aliases=["desktop", "desktop folder", "my desktop"],
                type="folder",
                path=str(user_home / "Desktop"),
                category="folders",
            ),
            AppShortcut(
                name="Downloads Folder",
                aliases=["downloads", "download folder", "my downloads"],
                type="folder",
                path=str(user_home / "Downloads"),
                category="folders",
            ),
            AppShortcut(
                name="Documents Folder",
                aliases=["documents", "doc folder", "my documents"],
                type="folder",
                path=str(user_home / "Documents"),
                category="folders",
            ),
            AppShortcut(
                name="AI Project Workspace",
                aliases=["ai project", "ai folder", "my project", "workspace", "codebase"],
                type="folder",
                path=str(Path.cwd()),
                category="folders",
            ),
        ]

    def _get_curated_web_shortcuts(self) -> list[AppShortcut]:
        """Top web services and cloud apps."""
        return [
            AppShortcut(
                name="YouTube",
                aliases=["youtube", "yt", "videos"],
                type="url",
                url="https://www.youtube.com",
                category="entertainment",
            ),
            AppShortcut(
                name="GitHub",
                aliases=["github", "git", "repos", "repositories"],
                type="url",
                url="https://github.com",
                category="development",
            ),
            AppShortcut(
                name="ChatGPT",
                aliases=["chatgpt", "openai", "gpt"],
                type="url",
                url="https://chat.openai.com",
                category="web",
            ),
            AppShortcut(
                name="Google",
                aliases=["google", "search engine", "google search"],
                type="url",
                url="https://www.google.com",
                category="web",
            ),
            AppShortcut(
                name="Canva",
                aliases=["canva", "graphic design", "design tool"],
                type="url",
                url="https://www.canva.com",
                category="productivity",
            ),
            AppShortcut(
                name="Gmail",
                aliases=["gmail", "google mail", "my email", "emails"],
                type="url",
                url="https://mail.google.com",
                category="productivity",
            ),
            AppShortcut(
                name="LinkedIn",
                aliases=["linkedin", "jobs", "network"],
                type="url",
                url="https://www.linkedin.com",
                category="productivity",
            ),
            AppShortcut(
                name="Google Maps",
                aliases=["maps", "google maps", "directions", "navigation"],
                type="url",
                url="https://maps.google.com",
                category="web",
            ),
        ]
