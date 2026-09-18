"""Safe Screenshot Capture for Denver Desktop Automation."""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from denver.automation.errors import PathTraversalError, ScreenshotError
from denver.automation.models import AutomationResult, AutomationRisk, ScreenshotResult
from denver.logging.logger import get_logger

logger = get_logger("automation.screenshot")

try:
    from PIL import ImageGrab
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


class ScreenshotController:
    """Captures and saves screen captures strictly within an approved sandbox directory."""

    def __init__(self, output_dir: Path | str = "data/screenshots", screenshot_dir: Path | str | None = None) -> None:
        chosen_dir = screenshot_dir if screenshot_dir is not None else output_dir
        self.output_dir = Path(chosen_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _generate_safe_filepath(self, custom_name: str | None = None) -> Path:
        """Generate a validated absolute path guaranteed to reside inside output_dir."""
        if custom_name:
            if ".." in custom_name or custom_name.startswith("/") or custom_name.startswith("\\") or (len(custom_name) > 1 and custom_name[1] == ":"):
                raw_path = Path(custom_name)
                if raw_path.is_absolute():
                    target_path = raw_path.resolve()
                else:
                    target_path = (self.output_dir / custom_name).resolve()
            else:
                clean_name = custom_name.strip()
                if not clean_name.lower().endswith(".png"):
                    clean_name = f"{clean_name}.png"
                target_path = (self.output_dir / clean_name).resolve()
        else:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_path = (self.output_dir / f"screenshot_{stamp}.png").resolve()

        # Enforce boundary containment
        try:
            target_path.relative_to(self.output_dir)
        except ValueError as exc:
            raise PathTraversalError(f"Target path '{target_path}' escapes screenshot directory '{self.output_dir}'") from exc

        return target_path

    def capture(self, custom_name: str | None = None) -> AutomationResult:
        """Capture the primary display and write exclusively to the approved screenshot folder."""
        try:
            target_file = self._generate_safe_filepath(custom_name)
        except PathTraversalError as exc:
            logger.warning("Screenshot path traversal blocked: %s", exc)
            return AutomationResult(
                success=False,
                action="take_screenshot",
                message=f"Path traversal blocked: {exc}",
                risk_level=AutomationRisk.MEDIUM,
                error="PathTraversalError",
            )

        if not _PIL_AVAILABLE:
            return AutomationResult(
                success=False,
                action="take_screenshot",
                message="Screenshot capture requires Pillow (PIL), which is unavailable.",
                risk_level=AutomationRisk.MEDIUM,
                error="PillowUnavailable",
            )

        try:
            img = ImageGrab.grab()
            img.save(target_file, "PNG")

            file_size = target_file.stat().st_size
            width, height = img.size

            res = ScreenshotResult(
                file_path=target_file,
                file_size_bytes=file_size,
                width=width,
                height=height,
                timestamp=time.time(),
                format="PNG",
            )

            logger.info("Captured screenshot saved to '%s' (%dx%d, %d bytes)", target_file, width, height, file_size)

            return AutomationResult(
                success=True,
                action="take_screenshot",
                target=str(target_file),
                message=f"Screenshot captured successfully: {target_file.name}",
                data=res.to_dict(),
                risk_level=AutomationRisk.MEDIUM,
            )

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Screenshot capture failed: %s", exc)
            return AutomationResult(
                success=False,
                action="take_screenshot",
                message=f"Failed to capture screenshot: {exc}",
                risk_level=AutomationRisk.MEDIUM,
                error=str(exc),
            )
