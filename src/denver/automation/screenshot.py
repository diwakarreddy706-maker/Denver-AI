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
    from PIL import Image, ImageGrab
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


def _grab_win32_gdi() -> Any:
    """Capture Windows desktop screen using native Win32 GDI BitBlt via ctypes."""
    import ctypes

    u32 = ctypes.windll.user32
    g32 = ctypes.windll.gdi32

    try:
        u32.SetProcessDPIAware()
    except Exception:
        pass

    w = u32.GetSystemMetrics(0)  # SM_CXSCREEN
    h = u32.GetSystemMetrics(1)  # SM_CYSCREEN
    if w <= 0 or h <= 0:
        raise RuntimeError("Invalid display metrics from user32.GetSystemMetrics")

    hdc_screen = u32.GetDC(0)
    hdc_mem = g32.CreateCompatibleDC(hdc_screen)
    hbm = g32.CreateCompatibleBitmap(hdc_screen, w, h)
    g32.SelectObject(hdc_mem, hbm)

    # 0x00CC0020 = SRCCOPY, 0x40000000 = CAPTUREBLT (captures layered/semi-transparent windows)
    g32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, 0, 0, 0x00CC0020 | 0x40000000)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.c_uint32),
            ("biWidth", ctypes.c_int32),
            ("biHeight", ctypes.c_int32),
            ("biPlanes", ctypes.c_uint16),
            ("biBitCount", ctypes.c_uint16),
            ("biCompression", ctypes.c_uint32),
            ("biSizeImage", ctypes.c_uint32),
            ("biXPelsPerMeter", ctypes.c_int32),
            ("biYPelsPerMeter", ctypes.c_int32),
            ("biClrUsed", ctypes.c_uint32),
            ("biClrImportant", ctypes.c_uint32),
        ]

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h  # top-down DIB
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0

    buf = ctypes.create_string_buffer(w * h * 4)
    g32.GetDIBits(hdc_mem, hbm, 0, h, buf, ctypes.byref(bmi), 0)

    # Clean up GDI handles
    g32.DeleteObject(hbm)
    g32.DeleteDC(hdc_mem)
    u32.ReleaseDC(0, hdc_screen)

    return Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")


def grab_desktop_image() -> Any:
    """Capture desktop display with automatic Win32 GDI fallback."""
    if not _PIL_AVAILABLE:
        raise RuntimeError("Pillow (PIL) is not installed; screen capture unavailable.")

    try:
        return ImageGrab.grab()
    except Exception as exc:
        if os.name == "nt":
            logger.debug("ImageGrab.grab() failed (%s); attempting Win32 GDI BitBlt fallback.", exc)
            return _grab_win32_gdi()
        raise


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
            img = grab_desktop_image()
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
