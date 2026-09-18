"""Vision Engine and Multimodal Screen Intelligence for Denver AI Assistant."""

from __future__ import annotations

import base64
import io
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from denver.automation.models import AutomationResult
from denver.automation.screenshot import ScreenshotController
from denver.logging.logger import get_logger
from denver.providers.models import ProviderRequest, ProviderResponse
from denver.providers.router import ProviderRouter

logger = get_logger("automation.vision")

try:
    from PIL import Image, ImageGrab
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


@dataclass
class VisionAnalysisResult:
    """Outcome of a multimodal visual screen analysis."""

    success: bool
    text: str
    screenshot_path: Path | None = None
    width: int = 0
    height: int = 0
    provider_used: str = ""
    model_used: str = ""
    latency_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "text": self.text,
            "screenshot_path": str(self.screenshot_path) if self.screenshot_path else None,
            "width": self.width,
            "height": self.height,
            "provider_used": self.provider_used,
            "model_used": self.model_used,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


class VisionEngine:
    """Orchestrates screen capture, image optimization, base64 encoding, and multimodal AI analysis."""

    def __init__(
        self,
        screenshot_controller: ScreenshotController | None = None,
        output_dir: Path | str = "data/screenshots",
    ) -> None:
        self.screenshot_controller = screenshot_controller or ScreenshotController(output_dir=output_dir)
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def capture_screen_base64(
        self,
        max_dimension: int = 1920,
        quality: int = 85,
    ) -> tuple[Path | None, str, int, int]:
        """Capture the current screen, optionally downscale to bounded resolution, and return base64 string."""
        if not _PIL_AVAILABLE:
            raise RuntimeError("Pillow (PIL) is not installed; screen capture unavailable.")

        try:
            img = ImageGrab.grab()
        except Exception as exc:
            logger.warning("ImageGrab.grab() failed (%s); creating diagnostic frame.", exc)
            img = Image.new("RGB", (1280, 720), color=(24, 24, 27))

        orig_w, orig_h = img.size

        # Downscale if image exceeds max dimension to ensure fast network transfer
        if max(orig_w, orig_h) > max_dimension:
            scale = max_dimension / max(orig_w, orig_h)
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        else:
            new_w, new_h = orig_w, orig_h

        # Save to sandbox screenshot folder
        stamp = time.strftime("%Y%m%d_%H%M%S")
        target_path = self.output_dir / f"vision_{stamp}.png"
        img.save(target_path, "PNG")

        # Convert to compressed JPEG/PNG base64 for prompt injection
        buf = io.BytesIO()
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=quality)
        b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")

        return target_path, b64_str, new_w, new_h

    async def analyze_screen(
        self,
        prompt: str,
        provider_router: ProviderRouter | None = None,
        image_base64: str | None = None,
        screenshot_path: Path | None = None,
        focus_mode: str = "general",
    ) -> VisionAnalysisResult:
        """Perform visual question answering and analysis on the active desktop screen."""
        start = time.perf_counter()
        width = 0
        height = 0

        # Step 1: Capture screen if not already provided
        if not image_base64:
            try:
                screenshot_path, image_base64, width, height = self.capture_screen_base64()
            except Exception as exc:
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                logger.error("Failed to capture screen for vision analysis: %s", exc)
                return VisionAnalysisResult(
                    success=False,
                    text="Failed to capture screen image.",
                    latency_ms=elapsed_ms,
                    error=str(exc),
                )

        # Step 2: Build Multimodal Request with focus mode instructions
        mode_instructions = {
            "error_diagnosis": (
                "You are Denver Desktop Vision in ERROR DIAGNOSIS mode. Specifically inspect IDE terminals, "
                "browser consoles, stack traces, compiler output, or error dialogs visible on screen. "
                "Extract: 1) The exact error message and line number, 2) The root cause, 3) The concrete solution/fix."
            ),
            "ocr_reading": (
                "You are Denver Desktop Vision in OCR & TEXT EXTRACTION mode. Read and transcribe all relevant "
                "text, headers, labels, and data visible on screen accurately."
            ),
            "code_review": (
                "You are Denver Desktop Vision in CODE INSPECTION mode. Inspect code visible on screen for syntax issues, "
                "logical bugs, typing mismatches, and suggest clean refactorings."
            ),
            "summary": (
                "You are Denver Desktop Vision in SUMMARY mode. Provide a 1-2 sentence executive overview "
                "of what application is active and what the user is working on."
            ),
        }

        system_instruction = mode_instructions.get(
            focus_mode.lower(),
            (
                "You are Denver Desktop Vision. You have been provided with a real-time screenshot "
                "of the user's active desktop screen. Analyze the visual elements, code, terminal output, "
                "active application, and UI components with high accuracy. "
                "Give direct, concise, and actionable answers. If an error or code issue is present, "
                "point it out specifically and provide the exact fix."
            ),
        )

        provider_req = ProviderRequest(
            messages=[{"role": "user", "content": prompt}],
            images=[image_base64],
            system_prompt=system_instruction,
            temperature=0.2 if focus_mode in {"error_diagnosis", "ocr_reading"} else 0.3,
            max_tokens=1024,
        )

        # Step 3: Dispatch to Multimodal Provider Router
        if provider_router is None:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            return VisionAnalysisResult(
                success=False,
                text="AI Provider Router is not available.",
                screenshot_path=screenshot_path,
                width=width,
                height=height,
                latency_ms=elapsed_ms,
                error="ProviderRouterMissing",
            )

        try:
            ai_res: ProviderResponse = await provider_router.generate(provider_req)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

            if ai_res.success:
                return VisionAnalysisResult(
                    success=True,
                    text=ai_res.text,
                    screenshot_path=screenshot_path,
                    width=width,
                    height=height,
                    provider_used=ai_res.provider_name,
                    model_used=ai_res.model_name,
                    latency_ms=elapsed_ms,
                )
            else:
                return VisionAnalysisResult(
                    success=False,
                    text=ai_res.error or "Vision analysis failed.",
                    screenshot_path=screenshot_path,
                    width=width,
                    height=height,
                    provider_used=ai_res.provider_name,
                    model_used=ai_res.model_name,
                    latency_ms=elapsed_ms,
                    error=ai_res.error,
                )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error("Vision multimodal generation failed: %s", exc)
            return VisionAnalysisResult(
                success=False,
                text=f"Vision analysis error: {exc}",
                screenshot_path=screenshot_path,
                width=width,
                height=height,
                latency_ms=elapsed_ms,
                error=str(exc),
            )
