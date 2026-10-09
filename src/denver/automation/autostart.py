"""Windows Autostart Manager for Denver AI Assistant.

Writes a lightweight, silent .vbs launcher directly to the Windows Startup folder
so Denver boots in the background at user logon without a command prompt window.
Writes files strictly through native Python file I/O to avoid LOLBin execution blocks.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from denver.logging.logger import get_logger

logger = get_logger("automation.autostart")

STARTUP_FILENAME = "Denver_Startup.vbs"


def get_project_root() -> Path:
    """Detect root directory of the Denver repository or executable location."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.resolve()
    # In source checkout: src/denver/automation/autostart.py -> parent x3 is project root
    return Path(__file__).resolve().parent.parent.parent.parent


def get_startup_directory() -> Path:
    """Return the Windows user Startup directory."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    # Fallback to standard user home path
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def get_autostart_path() -> Path:
    """Return the full destination path of the startup .vbs launcher."""
    return get_startup_directory() / STARTUP_FILENAME


def is_autostart_enabled() -> bool:
    """Check if Denver startup script exists in the Windows Startup folder."""
    return get_autostart_path().is_file()


def generate_vbs_content(project_dir: Path | None = None, headless: bool = True) -> str:
    """Generate VBScript content setting CurrentDirectory and launching Denver silently."""
    proj = (project_dir or get_project_root()).resolve()

    if getattr(sys, "frozen", False):
        exe_path = Path(sys.executable).resolve()
        flag = " --headless" if headless else ""
        run_cmd = f'"{exe_path}"{flag}'
    else:
        # Prefer pythonw.exe to prevent any console window allocation
        python_exe = Path(sys.executable).resolve()
        pythonw = python_exe.with_name("pythonw.exe")
        py_binary = pythonw if pythonw.is_file() else python_exe
        flag = " --headless" if headless else ""
        run_cmd = f'"{py_binary}" main.py{flag}'

    # Escape quotes for VBScript
    vbs_run_cmd = run_cmd.replace('"', '""')
    vbs_proj_dir = str(proj).replace('"', '""')

    return (
        "' Denver AI Assistant Windows Startup Launcher\n"
        "' Generated automatically. Do not edit directly.\n"
        "Set WshShell = CreateObject(\"WScript.Shell\")\n"
        f"WshShell.CurrentDirectory = \"{vbs_proj_dir}\"\n"
        f"WshShell.Run \"{vbs_run_cmd}\", 0, False\n"
        "Set WshShell = Nothing\n"
    )


def enable_autostart(project_dir: Path | None = None, headless: bool = True) -> Path:
    """Write the Denver autostart .vbs launcher directly to the Windows Startup folder.

    Never executes wscript/cscript or shell commands.
    """
    startup_dir = get_startup_directory()
    startup_dir.mkdir(parents=True, exist_ok=True)
    target_path = get_autostart_path()

    vbs_code = generate_vbs_content(project_dir=project_dir, headless=headless)
    target_path.write_text(vbs_code, encoding="utf-8")
    logger.info("Denver autostart launcher created at %s", target_path)
    return target_path


def disable_autostart() -> bool:
    """Remove Denver startup launcher from the Windows Startup folder."""
    target_path = get_autostart_path()
    if target_path.exists():
        try:
            target_path.unlink()
            logger.info("Denver autostart launcher removed from %s", target_path)
            return True
        except OSError as exc:
            logger.warning("Failed to remove autostart launcher %s: %s", target_path, exc)
            return False
    return False


def get_autostart_info() -> dict[str, Any]:
    """Inspect current autostart configuration."""
    target_path = get_autostart_path()
    enabled = target_path.is_file()
    content = ""
    if enabled:
        try:
            content = target_path.read_text(encoding="utf-8")
        except Exception:
            pass
    return {
        "enabled": enabled,
        "path": str(target_path),
        "project_root": str(get_project_root()),
        "content": content,
    }
