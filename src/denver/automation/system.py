"""System Telemetry and Workstation Control for Denver."""

from __future__ import annotations

import os
import platform
import socket
import time
from typing import Any

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

from denver.automation.models import AutomationResult, AutomationRisk
from denver.automation.windows import WindowsNativeAPI
from denver.logging.logger import get_logger

logger = get_logger("automation.system")


class SystemController:
    """Provides non-destructive system telemetry and privileged session locking."""

    def __init__(self, native_api: WindowsNativeAPI | None = None) -> None:
        self.api = native_api or WindowsNativeAPI()
        self._boot_time = psutil.boot_time() if _PSUTIL_AVAILABLE else time.time()

    def get_system_summary(self) -> AutomationResult:
        """Collect comprehensive system performance and hardware summary."""
        data: dict[str, Any] = {
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "hostname": socket.gethostname(),
            "python_version": platform.python_version(),
        }

        if _PSUTIL_AVAILABLE:
            try:
                # CPU
                data["cpu_percent"] = psutil.cpu_percent(interval=None)
                data["cpu_cores"] = psutil.cpu_count(logical=True)

                # RAM
                vm = psutil.virtual_memory()
                data["ram_percent"] = vm.percent
                data["ram_used_gb"] = round(vm.used / (1024**3), 2)
                data["ram_total_gb"] = round(vm.total / (1024**3), 2)

                # Disk
                disk = psutil.disk_usage("/")
                data["disk_percent"] = disk.percent
                data["disk_free_gb"] = round(disk.free / (1024**3), 2)
                data["disk_total_gb"] = round(disk.total / (1024**3), 2)

                # Battery
                if hasattr(psutil, "sensors_battery"):
                    batt = psutil.sensors_battery()
                    if batt:
                        data["battery_percent"] = batt.percent
                        data["power_plugged"] = batt.power_plugged

                # Uptime
                uptime_sec = max(0, time.time() - self._boot_time)
                data["uptime_hours"] = round(uptime_sec / 3600.0, 1)

            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("Error gathering partial system telemetry: %s", exc)

        cpu_str = f"{data.get('cpu_percent', 0)}%"
        ram_str = f"{data.get('ram_percent', 0)}%"
        msg = f"System: CPU {cpu_str}, RAM {ram_str} on {data['os']} {data['os_release']} ({data['hostname']})."

        return AutomationResult(
            success=True,
            action="get_system_summary",
            message=msg,
            data=data,
            risk_level=AutomationRisk.LOW,
        )

    def lock_workstation(self) -> AutomationResult:
        """Lock the current Windows workstation session (High Risk)."""
        ok = self.api.lock_workstation()
        if ok:
            logger.info("Workstation locked successfully.")
            return AutomationResult(
                success=True,
                action="lock_workstation",
                message="Workstation locked successfully.",
                risk_level=AutomationRisk.HIGH,
            )

        return AutomationResult(
            success=False,
            action="lock_workstation",
            message="Failed to lock workstation.",
            risk_level=AutomationRisk.HIGH,
            error="LockWorkstationFailed",
        )
