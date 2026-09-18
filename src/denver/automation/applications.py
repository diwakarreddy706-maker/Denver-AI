"""Allowlisted Application Launcher and Closer for Denver."""

from __future__ import annotations

import os
import subprocess
import webbrowser
from typing import Any

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

from denver.automation.errors import ApplicationLaunchError, ApplicationNotFoundError
from denver.automation.models import ApplicationTarget, AutomationResult, AutomationRisk
from denver.automation.registry import AutomationRegistry
from denver.logging.logger import get_logger

logger = get_logger("automation.applications")


class ApplicationController:
    """Safe, allowlisted application manager preventing arbitrary executable execution."""

    def __init__(self, registry: AutomationRegistry | None = None) -> None:
        self.registry = registry or AutomationRegistry()

    @staticmethod
    def _resolve_executable(executable: str) -> str:
        """Resolve executable path handling Windows PATH, .cmd wrappers, and standard install locations."""
        import shutil
        if not executable:
            return executable

        # 1. Direct which lookup
        which_path = shutil.which(executable)
        if which_path and os.path.exists(which_path):
            return which_path

        # 2. If path already exists directly or expanded
        expanded = os.path.expandvars(executable)
        if os.path.exists(expanded):
            return expanded

        # 3. Known standard Windows program locations
        common_locations = {
            "code": [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
                os.path.expandvars(r"%ProgramFiles%\Microsoft VS Code\Code.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft VS Code\Code.exe"),
            ],
            "chrome": [
                os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ],
            "brave": [
                os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            ],
            "msedge": [
                os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            ],
        }
        stem = os.path.splitext(os.path.basename(executable))[0].lower()
        for candidate in common_locations.get(stem, []):
            if os.path.exists(candidate):
                return candidate

        return executable

    def launch(self, app_query: str) -> AutomationResult:
        """Launch an allowlisted application by identifier, registered alias, or apps.json discovery."""
        # 1. Primary Check: Static AutomationRegistry
        app = self.registry.find_application(app_query)
        if app:
            try:
                if app.app_id == "browser":
                    webbrowser.open("https://www.google.com")
                    logger.info("Launched default browser.")
                    return AutomationResult(
                        success=True,
                        action="open_application",
                        target=app.display_name,
                        message=f"Opened {app.display_name}.",
                        data={"app_id": app.app_id, "executable": app.executable},
                        risk_level=AutomationRisk.LOW,
                    )

                if app.is_uri_scheme:
                    try:
                        os.startfile(app.executable)
                        logger.info("Launched URI application: %s", app.executable)
                        return AutomationResult(
                            success=True,
                            action="open_application",
                            target=app.display_name,
                            message=f"Opened {app.display_name}.",
                            data={"app_id": app.app_id, "scheme": app.executable},
                            risk_level=AutomationRisk.LOW,
                        )
                    except Exception as uri_err:
                        web_fallbacks = {
                            "whatsapp": "https://web.whatsapp.com",
                            "spotify": "https://open.spotify.com",
                            "discord": "https://discord.com/app",
                            "telegram": "https://web.telegram.org",
                        }
                        if app.app_id in web_fallbacks:
                            webbrowser.open(web_fallbacks[app.app_id])
                            logger.info("Launched %s web fallback.", app.display_name)
                            return AutomationResult(
                                success=True,
                                action="open_application",
                                target=app.display_name,
                                message=f"Opened {app.display_name} (Web).",
                                data={"app_id": app.app_id, "url": web_fallbacks[app.app_id]},
                                risk_level=AutomationRisk.LOW,
                            )
                        raise uri_err

                # Standard executable launch with resolution & fallbacks
                resolved_exe = self._resolve_executable(app.executable)
                args = [resolved_exe] + list(app.launch_args)
                is_batch = resolved_exe.lower().endswith((".cmd", ".bat"))
                try:
                    proc = subprocess.Popen(args, shell=is_batch)
                    pid = getattr(proc, "pid", None)
                except Exception:
                    os.startfile(resolved_exe)
                    pid = None

                logger.info("Launched allowlisted application '%s' (PID: %s)", app.display_name, pid)

                return AutomationResult(
                    success=True,
                    action="open_application",
                    target=app.display_name,
                    message=f"Opened {app.display_name}.",
                    data={"app_id": app.app_id, "pid": pid, "executable": resolved_exe},
                    risk_level=AutomationRisk.LOW,
                )
            except Exception as exc:
                logger.error("Failed to launch application '%s': %s", app.display_name, exc)
                return AutomationResult(
                    success=False,
                    action="open_application",
                    target=app.display_name,
                    message=f"Could not open {app.display_name}: {exc}",
                    risk_level=AutomationRisk.LOW,
                    error=str(exc),
                )

        # 2. Secondary Fallback: data/apps.json discovered shortcuts (Apps, Websites, Folders)
        try:
            from denver.automation.apps_scanner import WindowsAppScanner
            scanner = WindowsAppScanner()
            for item in scanner.load_apps():
                if item.matches(app_query):
                    logger.info("Found '%s' in discovered apps catalog (%s).", app_query, item.name)
                    if item.type == "url" and item.url:
                        webbrowser.open(item.url)
                        return AutomationResult(
                            success=True,
                            action="open_application",
                            target=item.name,
                            message=f"Opened {item.name} in browser.",
                            data={"name": item.name, "url": item.url, "type": "url"},
                            risk_level=AutomationRisk.LOW,
                        )
                    elif item.type == "folder" and item.path:
                        os.startfile(item.path)
                        return AutomationResult(
                            success=True,
                            action="open_application",
                            target=item.name,
                            message=f"Opened folder {item.name}.",
                            data={"name": item.name, "path": item.path, "type": "folder"},
                            risk_level=AutomationRisk.LOW,
                        )
                    elif item.path:
                        try:
                            os.startfile(item.path)
                        except Exception:
                            subprocess.Popen([item.path] + list(item.launch_args), shell=False)
                        return AutomationResult(
                            success=True,
                            action="open_application",
                            target=item.name,
                            message=f"Opened {item.name}.",
                            data={"name": item.name, "path": item.path, "type": item.type},
                            risk_level=AutomationRisk.LOW,
                        )
        except Exception as scan_err:
            logger.debug("Apps catalog check failed: %s", scan_err)

        logger.warning("Application launch rejected: '%s' is not in allowlist.", app_query)
        return AutomationResult(
            success=False,
            action="open_application",
            target=app_query,
            message=f"Application '{app_query}' is not in the allowlisted registry.",
            risk_level=AutomationRisk.LOW,
            error="ApplicationNotAllowlisted",
        )

    def close(self, app_query: str) -> AutomationResult:
        """Terminate running processes matching an allowlisted application."""
        app = self.registry.find_application(app_query)
        if not app:
            logger.warning("Application close rejected: '%s' is not in allowlist.", app_query)
            return AutomationResult(
                success=False,
                action="close_application",
                target=app_query,
                message=f"Application '{app_query}' is not in the allowlisted registry.",
                risk_level=AutomationRisk.MEDIUM,
                error="ApplicationNotAllowlisted",
            )

        if not _PSUTIL_AVAILABLE:
            return AutomationResult(
                success=False,
                action="close_application",
                target=app.display_name,
                message=f"Process termination requires psutil, which is unavailable.",
                risk_level=AutomationRisk.MEDIUM,
                error="PsutilUnavailable",
            )

        if not app.process_names:
            return AutomationResult(
                success=False,
                action="close_application",
                target=app.display_name,
                message=f"No process name defined for closing {app.display_name}.",
                risk_level=AutomationRisk.MEDIUM,
                error="NoProcessNameDefined",
            )

        target_processes = {p.lower() for p in app.process_names}
        terminated_count = 0

        try:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    pname = (proc.info["name"] or "").lower()
                    if pname in target_processes:
                        proc.terminate()
                        terminated_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if terminated_count > 0:
                logger.info("Closed %s instance(s) of '%s'", terminated_count, app.display_name)
                return AutomationResult(
                    success=True,
                    action="close_application",
                    target=app.display_name,
                    message=f"Closed {app.display_name}.",
                    data={"app_id": app.app_id, "terminated_instances": terminated_count},
                    risk_level=AutomationRisk.MEDIUM,
                )

            return AutomationResult(
                success=True,
                action="close_application",
                target=app.display_name,
                message=f"{app.display_name} was not currently running.",
                data={"app_id": app.app_id, "terminated_instances": 0},
                risk_level=AutomationRisk.MEDIUM,
            )

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to close application '%s': %s", app.display_name, exc)
            return AutomationResult(
                success=False,
                action="close_application",
                target=app.display_name,
                message=f"Failed to close {app.display_name}: {exc}",
                risk_level=AutomationRisk.MEDIUM,
                error=str(exc),
            )

    def send_whatsapp_message(self, message: str, phone: str = "", contact_name: str = "") -> AutomationResult:
        """Launch WhatsApp with drafted message or open contact chat and send."""
        from denver.automation.whatsapp import WhatsAppDispatcher
        dispatcher = WhatsAppDispatcher()
        return dispatcher.dispatch_message(message=message, phone=phone, contact_name=contact_name)

