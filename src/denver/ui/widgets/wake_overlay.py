"""Denver Wake-Word HUD Overlay — Jarvis-Style Multi-Modal Cyber HUD.

Features:
1. Live Voice-Reactive Audio Waveform (Sound-Reactive Arc Reactor).
2. Live Ghost Subtitles (Real-time voice transcription & feedback pill).
3. Dynamic Adaptive Sizing (Compact Pill 380x56 <-> Expanded HUD 780x340).
4. Windows 11 Native Acrylic / Mica Frosted Glass Backing.
5. Action Receipt Micro-Cards & Visual Execution Badges.
6. Sci-Fi Audio Cues (Toggleable low-latency synthesizer).
7. Custom Arc Reactor Themes & Color Palettes (Jarvis, Cyberpunk, Matrix, Stealth, Crimson).

Thread-Safe Public API:
    notify_wake_overlay("LISTENING")
    notify_wake_overlay_subtitle("Turn on notepad and write hi")
    notify_wake_overlay_audio(0.75)
    notify_wake_overlay_receipt("🚀", "Notepad Launched", "PID 20420")
    notify_wake_overlay_theme("CYBERPUNK")
    notify_wake_overlay_mode("compact")
"""

from __future__ import annotations

import ctypes
import io
import json
import math
import re
import struct
import sys
import threading
import time
from typing import Any
import urllib.request
import wave

import psutil
from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QWidget

# --------------------------------------------------------------------------- #
# 1. Sci-Fi Audio Cues (In-Memory Synthesizer)
# --------------------------------------------------------------------------- #


class SciFiAudioPlayer:
    """Low-latency sci-fi audio cue synthesizer for assistant state changes."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled and sys.platform == "win32"
        self._cues: dict[str, bytes] = {}
        if self.enabled:
            try:
                self._cues["wake"] = self._synth([(587, 50), (880, 70)])      # D5 -> A5 rising
                self._cues["success"] = self._synth([(1046, 35), (1318, 55)])  # C6 -> E6 high confirmation
                self._cues["standby"] = self._synth([(880, 45), (440, 65)])    # A5 -> A4 descending sleep
            except Exception:
                self.enabled = False

    @staticmethod
    def _synth(tones: list[tuple[int, int]], sample_rate: int = 44100) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            for freq, dur_ms in tones:
                n_samples = int(sample_rate * dur_ms / 1000)
                for i in range(n_samples):
                    t = i / sample_rate
                    env = math.sin(math.pi * i / n_samples)
                    val = int(32767 * 0.22 * env * math.sin(2 * math.pi * freq * t))
                    w.writeframes(struct.pack("<h", val))
        return buf.getvalue()

    def play(self, cue_name: str) -> None:
        """Play synthesized audio cue in a daemon thread without blocking."""
        if not self.enabled or cue_name not in self._cues:
            return
        data = self._cues[cue_name]

        def _play_worker() -> None:
            try:
                import winsound
                winsound.PlaySound(data, winsound.SND_MEMORY)
            except Exception:
                pass

        threading.Thread(target=_play_worker, name=f"DenverAudioCue-{cue_name}", daemon=True).start()


_audio_cues = SciFiAudioPlayer(enabled=True)


# --------------------------------------------------------------------------- #
# 2. Windows 11 Native Acrylic & Mica Glass API
# --------------------------------------------------------------------------- #


def apply_windows_acrylic_glass(hwnd: int) -> bool:
    """Apply native Windows 11 Acrylic/Mica blurred translucent window backdrop."""
    if sys.platform != "win32":
        return False
    try:
        dwmapi = ctypes.windll.dwmapi
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        dark_mode = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33 -> DWMWCP_ROUND (2)
        corner_pref = ctypes.c_int(2)
        dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner_pref), ctypes.sizeof(corner_pref))
        # DWMWA_SYSTEMBACKDROP_TYPE = 38 -> DWMSBT_TRANSIENTWINDOW (Acrylic = 3) or Mica (2)
        backdrop = ctypes.c_int(3)
        res = dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop))
        return res == 0
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# 3. Themes & Color Palettes
# --------------------------------------------------------------------------- #

THEMES: dict[str, dict[str, Any]] = {
    "JARVIS": {
        "primary": QColor("#22d3ee"),     # Cyan
        "secondary": QColor("#fbbf24"),   # Gold
        "glow": QColor("#38bdf8"),        # Sky
        "accent": QColor("#a78bfa"),      # Purple
        "bg_top": QColor(9, 13, 22, 230),
        "bg_bottom": QColor(15, 23, 42, 230),
    },
    "CYBERPUNK": {
        "primary": QColor("#c084fc"),     # Neon Purple
        "secondary": QColor("#f43f5e"),   # Hot Pink
        "glow": QColor("#ec4899"),        # Neon Pink Glow
        "accent": QColor("#22d3ee"),      # Cyan
        "bg_top": QColor(18, 10, 30, 230),
        "bg_bottom": QColor(28, 14, 46, 230),
    },
    "MATRIX": {
        "primary": QColor("#10b981"),     # Emerald Terminal
        "secondary": QColor("#34d399"),   # Mint
        "glow": QColor("#059669"),        # Dark Emerald
        "accent": QColor("#6ee7b7"),      # Soft Green
        "bg_top": QColor(4, 18, 12, 230),
        "bg_bottom": QColor(8, 28, 18, 230),
    },
    "STEALTH": {
        "primary": QColor("#f8fafc"),     # Titanium White
        "secondary": QColor("#38bdf8"),   # Ice Blue
        "glow": QColor("#94a3b8"),        # Slate Glow
        "accent": QColor("#64748b"),      # Steel
        "bg_top": QColor(15, 23, 42, 230),
        "bg_bottom": QColor(30, 41, 59, 230),
    },
    "CRIMSON": {
        "primary": QColor("#ef4444"),     # Crimson Mark 42
        "secondary": QColor("#f59e0b"),   # Amber Gold
        "glow": QColor("#dc2626"),        # Red Glow
        "accent": QColor("#f87171"),      # Coral
        "bg_top": QColor(26, 10, 10, 230),
        "bg_bottom": QColor(40, 15, 15, 230),
    },
}

STATE_COLORS = {
    "LISTENING": QColor("#22d3ee"),
    "PROCESSING": QColor("#fbbf24"),
    "SPEAKING": QColor("#34d399"),
    "STANDBY": QColor("#64748b"),
}

TEXT_COLOR = QColor("#f1f5f9")
MUTED_COLOR = QColor("#64748b")
GREEN_COLOR = QColor("#34d399")
AMBER_COLOR = QColor("#fbbf24")
RED_COLOR = QColor("#f87171")


# --------------------------------------------------------------------------- #
# 4. Desktop Context & System Helpers
# --------------------------------------------------------------------------- #

_WMO = {
    0: "Clear sky", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 71: "Light snow", 73: "Snow",
    75: "Heavy snow", 80: "Rain showers", 81: "Rain showers", 82: "Heavy showers",
    95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
}

_IDE_PROCS = {"code.exe", "cursor.exe", "windsurf.exe", "code - insiders.exe"}


def _http_json(url: str, timeout: float = 4.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "DenverOverlay/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read().decode("utf-8"))


def fetch_weather() -> str:
    """Return e.g. '31°C · Partly cloudy · Chennai'."""
    try:
        import asyncio
        from denver.automation.location import LocationService
        from denver.automation.weather import WeatherService
        loc_svc = LocationService()
        coords = asyncio.run(loc_svc.detect_current_location())
        ws = WeatherService(location_service=loc_svc)
        city_hint = coords.city if coords and coords.city else ""
        report = asyncio.run(ws.get_current_weather(city_hint or "here"))
        if report and report.temp_c is not None:
            desc = report.condition or "Fair"
            txt = f"{round(report.temp_c)}°C · {desc}"
            city_out = report.city.split(",")[0].strip() if report.city else city_hint
            return f"{txt} · {city_out}" if city_out else txt
    except BaseException:
        pass

    try:
        loc = _http_json("https://ipapi.co/json/")
        lat, lon, city = loc["latitude"], loc["longitude"], loc.get("city", "")
        w = _http_json(
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code"
        )["current"]
        desc = _WMO.get(int(w["weather_code"]), "—")
        text = f"{round(w['temperature_2m'])}°C · {desc}"
        return f"{text} · {city}" if city else text
    except BaseException:
        return "Weather unavailable"


def foreground_project() -> str:
    """Describe what the user is working on right now."""
    try:
        from denver.core.observer import DesktopObserverEngine
        obs = DesktopObserverEngine()
        ctx = obs.observe_active_window()
        if ctx and ctx.title:
            if ctx.project_name and ctx.active_file:
                return f"{ctx.project_name}  ·  {ctx.active_file}"
            if ctx.project_name:
                return ctx.project_name
            app = (ctx.process_name or "").replace(".exe", "").title()
            short = re.sub(r"\s+", " ", ctx.title)[:38]
            return f"{app}  ·  {short}" if short else app
    except Exception:
        pass

    if sys.platform != "win32":
        return "—"
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "—"
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        title = buf.value.replace("●", "").strip()
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc = psutil.Process(pid.value).name().lower()
    except Exception:
        return "—"

    if proc in _IDE_PROCS:
        parts = [p.strip() for p in title.split(" - ") if p.strip()]
        if len(parts) >= 3:
            return f"{parts[-2]}  ·  {parts[0]}"
        if len(parts) == 2:
            return parts[0]
    app = proc.replace(".exe", "").title()
    short = re.sub(r"\s+", " ", title)[:38]
    return f"{app}  ·  {short}" if short else app


def read_system() -> dict[str, Any]:
    batt = None
    try:
        batt = psutil.sensors_battery()
    except Exception:
        pass
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "mem": psutil.virtual_memory().percent,
        "batt": batt.percent if batt else None,
        "plugged": bool(batt.power_plugged) if batt else False,
    }


# --------------------------------------------------------------------------- #
# 5. Core HUD Wake Overlay Widget
# --------------------------------------------------------------------------- #


class WakeOverlay(QWidget):
    """Futuristic Jarvis-Style HUD Overlay Widget."""

    _sig_show = Signal()
    _sig_state = Signal(str)
    _sig_hide = Signal()
    _sig_subtitle = Signal(str)
    _sig_audio = Signal(float)
    _sig_receipt = Signal(str, str, str)
    _sig_theme = Signal(str)
    _sig_mode = Signal(str)

    W_EXPANDED, H_EXPANDED = 780, 340
    W_COMPACT, H_COMPACT = 380, 56
    AUTO_HIDE_SECONDS = 8.0
    WEATHER_TTL = 15 * 60

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # Mode: 'expanded' (Full HUD) or 'compact' (Dynamic Island Pill)
        self._mode = "expanded"
        self._cur_w = float(self.W_EXPANDED)
        self._cur_h = float(self.H_EXPANDED)
        self.setFixedSize(self.W_EXPANDED, self.H_EXPANDED)

        # State & Theme
        self._state = "LISTENING"
        self._theme_name = "JARVIS"
        self._theme = THEMES[self._theme_name]

        # Live Audio Waveform Reactivity
        self._audio_level = 0.0
        self._target_audio_level = 0.0
        self._audio_spectrum = [0.0] * 16

        # Live Ghost Subtitles & Action Receipts
        self._subtitle = ""
        self._subtitle_ts = 0.0
        self._receipt: dict[str, Any] | None = None

        # Telemetry & Timers
        self._sys = {"cpu": 0.0, "mem": 0.0, "batt": None, "plugged": False}
        self._project = "—"
        self._weather = "Fetching weather…"
        self._weather_at = 0.0
        self._weather_busy = False
        self._deadline = 0.0
        self._target_opacity = 0.0
        self._t0 = time.monotonic()
        self._last_stats = 0.0

        psutil.cpu_percent(interval=None)

        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60 FPS
        self._timer.timeout.connect(self._tick)

        # Connect internal Qt signals
        self._sig_show.connect(self._do_show)
        self._sig_state.connect(self._do_state)
        self._sig_hide.connect(self._do_hide)
        self._sig_subtitle.connect(self._do_subtitle)
        self._sig_audio.connect(self._do_audio)
        self._sig_receipt.connect(self._do_receipt)
        self._sig_theme.connect(self._do_theme)
        self._sig_mode.connect(self._do_mode)

        self.setWindowOpacity(0.0)

    # ---- Public Thread-Safe API ------------------------------------------ #

    def show_listening(self) -> None:
        self._sig_show.emit()

    def set_state(self, state: str) -> None:
        self._sig_state.emit(state.upper())

    def hide_overlay(self) -> None:
        self._sig_hide.emit()

    def set_subtitle(self, text: str) -> None:
        self._sig_subtitle.emit(text)

    def set_audio_level(self, level: float) -> None:
        self._sig_audio.emit(max(0.0, min(1.0, level)))

    def show_receipt(self, icon: str, title: str, detail: str = "") -> None:
        self._sig_receipt.emit(icon, title, detail)

    def set_theme(self, theme_name: str) -> None:
        self._sig_theme.emit(theme_name.upper())

    def set_mode(self, mode: str) -> None:
        self._sig_mode.emit(mode.lower())

    def toggle_mode(self) -> None:
        new_mode = "compact" if self._mode == "expanded" else "expanded"
        self.set_mode(new_mode)

    # ---- Internal GUI Thread Slots --------------------------------------- #

    def _do_show(self) -> None:
        self._project = foreground_project()
        self._state = "LISTENING"
        self._subtitle = ""
        self._receipt = None
        self._refresh_stats()
        self._maybe_fetch_weather()
        self._reposition()
        self._deadline = time.monotonic() + self.AUTO_HIDE_SECONDS
        self._target_opacity = 1.0

        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()

        _audio_cues.play("wake")
        self._timer.start()

    def _do_state(self, state: str) -> None:
        self._state = state
        if state in ("PROCESSING", "SPEAKING"):
            self._deadline = time.monotonic() + 60.0
        elif state == "STANDBY":
            self._deadline = time.monotonic() + 1.6
            _audio_cues.play("standby")
        else:
            self._deadline = time.monotonic() + self.AUTO_HIDE_SECONDS

    def _do_hide(self) -> None:
        self._target_opacity = 0.0

    def _do_subtitle(self, text: str) -> None:
        self._subtitle = text
        self._subtitle_ts = time.monotonic()
        self.update()

    def _do_audio(self, level: float) -> None:
        self._target_audio_level = level

    def _do_receipt(self, icon: str, title: str, detail: str) -> None:
        self._receipt = {
            "icon": icon,
            "title": title,
            "detail": detail,
            "expires": time.monotonic() + 4.5,
        }
        _audio_cues.play("success")
        self.update()

    def _do_theme(self, theme_name: str) -> None:
        if theme_name in THEMES:
            self._theme_name = theme_name
            self._theme = THEMES[theme_name]
            self.update()

    def _do_mode(self, mode: str) -> None:
        if mode in ("expanded", "compact"):
            self._mode = mode
            target_w = self.W_COMPACT if mode == "compact" else self.W_EXPANDED
            target_h = self.H_COMPACT if mode == "compact" else self.H_EXPANDED
            self.setFixedSize(target_w, target_h)
            self._reposition()
            self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        # Clicking overlay toggles between Dynamic Island and Full HUD
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_mode()
        elif event.button() == Qt.MouseButton.RightButton:
            # Right-click cycles themes
            theme_keys = list(THEMES.keys())
            idx = (theme_keys.index(self._theme_name) + 1) % len(theme_keys)
            self.set_theme(theme_keys[idx])
        super().mousePressEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if sys.platform == "win32":
            try:
                hwnd = self.winId()
                GWL_EXSTYLE = -20
                WS_EX_NOACTIVATE = 0x08000000
                cur = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, cur | WS_EX_NOACTIVATE)
                apply_windows_acrylic_glass(hwnd)
            except Exception:
                pass

    # ---- Animation & Layout Loop ------------------------------------------ #

    def _reposition(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        w = self.width()
        top_offset = 24 if self._mode == "compact" else 48
        self.move(screen.center().x() - w // 2, screen.top() + top_offset)

    def _refresh_stats(self) -> None:
        self._sys = read_system()
        self._last_stats = time.monotonic()

    def _maybe_fetch_weather(self) -> None:
        if self._weather_busy or time.monotonic() - self._weather_at < self.WEATHER_TTL:
            return
        self._weather_busy = True

        def work() -> None:
            try:
                self._weather = fetch_weather()
                self._weather_at = time.monotonic()
            except BaseException:
                self._weather = "Weather unavailable"
                self._weather_at = time.monotonic() - self.WEATHER_TTL + 60
            finally:
                self._weather_busy = False

        threading.Thread(target=work, name="DenverWeatherFetch", daemon=True).start()

    def _tick(self) -> None:
        now = time.monotonic()
        if now > self._deadline:
            self._target_opacity = 0.0

        if now - self._last_stats > 1.2:
            self._refresh_stats()

        # Audio energy smoothing & radial frequency simulation
        self._audio_level += (self._target_audio_level - self._audio_level) * 0.35
        self._target_audio_level *= 0.88
        for i in range(16):
            target_sp = self._audio_level * (0.6 + 0.4 * math.sin(now * 8 + i * 0.7))
            self._audio_spectrum[i] += (target_sp - self._audio_spectrum[i]) * 0.4

        # Smooth opacity transition
        cur = self.windowOpacity()
        step = 0.08
        if cur < self._target_opacity:
            cur = min(self._target_opacity, cur + step)
        elif cur > self._target_opacity:
            cur = max(self._target_opacity, cur - step)
        self.setWindowOpacity(cur)

        if cur <= 0.0 and self._target_opacity <= 0.0:
            self._timer.stop()
            self.hide()
            return

        self.update()

    # ---- Painting & Rendering Engine -------------------------------------- #

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = time.monotonic() - self._t0
        accent = STATE_COLORS.get(self._state, self._theme["primary"])

        if self._mode == "compact":
            self._paint_compact(p, t, accent)
        else:
            self._paint_expanded(p, t, accent)
        p.end()

    # ---- Mode: Compact Dynamic Island ------------------------------------ #

    def _paint_compact(self, p: QPainter, t: float, accent: QColor) -> None:
        panel = QRectF(4, 4, self.width() - 8, self.height() - 8)
        grad = QLinearGradient(panel.topLeft(), panel.bottomRight())
        grad.setColorAt(0, self._theme["bg_top"])
        grad.setColorAt(1, self._theme["bg_bottom"])
        p.setBrush(grad)
        p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 140), 1.5))
        p.drawRoundedRect(panel, 24, 24)

        # Micro Orb on left
        c = QPointF(32, self.height() / 2)
        orb_r = 14 + 4 * self._audio_level
        glow = QRadialGradient(c, orb_r + 10)
        glow.setColorAt(0, QColor(accent.red(), accent.green(), accent.blue(), 180))
        glow.setColorAt(1, QColor(accent.red(), accent.green(), accent.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, orb_r + 10, orb_r + 10)

        p.setBrush(accent)
        p.drawEllipse(c, 8, 8)

        # Center Status Pill or Subtitle
        text_rect = QRectF(60, 0, self.width() - 140, self.height())
        p.setPen(TEXT_COLOR)
        if self._receipt and time.monotonic() < self._receipt["expires"]:
            f = QFont("Segoe UI", 9, QFont.Weight.Bold)
            p.setFont(f)
            p.setPen(GREEN_COLOR)
            p.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{self._receipt['icon']} {self._receipt['title']}")
        elif self._subtitle:
            f = QFont("Segoe UI", 9)
            p.setFont(f)
            fm = p.fontMetrics()
            elided = fm.elidedText(self._subtitle, Qt.TextElideMode.ElideRight, int(text_rect.width()))
            p.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)
        else:
            f = QFont("Segoe UI", 9, QFont.Weight.Bold)
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
            p.setFont(f)
            p.setPen(accent)
            p.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"DENVER · {self._state}")

        # Right indicator: Battery / Online
        right_rect = QRectF(self.width() - 80, 0, 68, self.height())
        s = self._sys
        batt_txt = f"{s['batt']:.0f}%" if s["batt"] is not None else "ONLINE"
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(GREEN_COLOR)
        p.drawText(right_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"● {batt_txt}")

    # ---- Mode: Full Cyber Reactor HUD ------------------------------------ #

    def _paint_expanded(self, p: QPainter, t: float, accent: QColor) -> None:
        panel = QRectF(8, 8, self.width() - 16, self.height() - 16)
        grad = QLinearGradient(panel.topLeft(), panel.bottomRight())
        grad.setColorAt(0, self._theme["bg_top"])
        grad.setColorAt(1, self._theme["bg_bottom"])
        p.setBrush(grad)
        p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 130), 1.5))
        p.drawRoundedRect(panel, 22, 22)

        self._paint_reactor(p, QPointF(175, self.height() / 2 - 12), t, accent)
        self._paint_stats(p, accent)

    def _paint_reactor(self, p: QPainter, c: QPointF, t: float, accent: QColor) -> None:
        pulse = 0.5 + 0.5 * math.sin(t * (7 if self._state == "SPEAKING" else 3))
        pulse_boost = pulse * 0.4 + self._audio_level * 0.6

        # Outer ambient glow reactive to audio level
        glow_radius = 125 + int(45 * self._audio_level)
        glow = QRadialGradient(c, glow_radius)
        glow.setColorAt(0, QColor(accent.red(), accent.green(), accent.blue(), int(80 + 70 * pulse_boost)))
        glow.setColorAt(1, QColor(accent.red(), accent.green(), accent.blue(), 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, glow_radius, glow_radius)

        # Concentric rotating rings
        spin = 1.0 if self._state != "PROCESSING" else 2.8
        rings = [(108, 2.0, 220, 40, 1), (86, 3.0, 140, 70, -1), (64, 2.0, 90, 20, 1)]
        for radius, width, span, gap, direction in rings:
            r_dyn = radius + 4 * self._audio_level
            pen = QPen(accent, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            rect = QRectF(c.x() - r_dyn, c.y() - r_dyn, r_dyn * 2, r_dyn * 2)
            base = (t * 60 * spin * direction * radius / 90) % 360
            for k in range(0, 360, span + gap):
                p.drawArc(rect, int(-(base + k) * 16), int(-span * 16))

        # 16 Radial soundwave spectrum spokes
        for i in range(16):
            ang = math.radians(i * 22.5 + t * 20)
            r_inner = 114
            spoke_len = 6 + int(18 * self._audio_spectrum[i])
            r_outer = r_inner + spoke_len
            spoke_col = QColor(accent.red(), accent.green(), accent.blue(), int(120 + 130 * self._audio_spectrum[i]))
            p.setPen(QPen(spoke_col, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(
                QPointF(c.x() + r_inner * math.cos(ang), c.y() + r_inner * math.sin(ang)),
                QPointF(c.x() + r_outer * math.cos(ang), c.y() + r_outer * math.sin(ang)),
            )

        # Minute tick marks
        p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 85), 1))
        for i in range(60):
            a = math.radians(i * 6)
            r1, r2 = 120, 124 if i % 5 else 128
            p.drawLine(
                QPointF(c.x() + r1 * math.cos(a), c.y() + r1 * math.sin(a)),
                QPointF(c.x() + r2 * math.cos(a), c.y() + r2 * math.sin(a)),
            )

        # Blazing central core
        core_r = 38 + 8 * pulse_boost
        core = QRadialGradient(c, core_r)
        core.setColorAt(0, QColor(255, 255, 255, 245))
        core.setColorAt(0.35, accent)
        core.setColorAt(1, QColor(accent.red(), accent.green(), accent.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(core)
        p.drawEllipse(c, core_r, core_r)

        # State label
        p.setPen(accent)
        f = QFont("Segoe UI", 10, QFont.Weight.Bold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4)
        p.setFont(f)
        p.drawText(QRectF(c.x() - 120, c.y() + 132, 240, 22), Qt.AlignmentFlag.AlignCenter, self._state)

    def _paint_stats(self, p: QPainter, accent: QColor) -> None:
        x0, x1 = 345, self.width() - 40

        # Header branding & Theme Badge
        f = QFont("Segoe UI", 20, QFont.Weight.Bold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 8)
        p.setFont(f)
        p.setPen(TEXT_COLOR)
        p.drawText(QRectF(x0, 24, 220, 32), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "DENVER")

        # Theme indicator pill
        theme_pill = QRectF(x0 + 175, 29, 90, 22)
        p.setBrush(QColor(30, 41, 59, 180))
        p.setPen(QPen(accent, 1.0))
        p.drawRoundedRect(theme_pill, 11, 11)
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(accent)
        p.drawText(theme_pill, Qt.AlignmentFlag.AlignCenter, f"◈ {self._theme_name}")

        # System Online / Action Receipt Pill
        if self._receipt and time.monotonic() < self._receipt["expires"]:
            badge_rect = QRectF(x1 - 240, 26, 240, 28)
            p.setBrush(QColor(16, 185, 129, 45))
            p.setPen(QPen(GREEN_COLOR, 1.2))
            p.drawRoundedRect(badge_rect, 14, 14)
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            p.setPen(GREEN_COLOR)
            rec_text = f"{self._receipt['icon']}  {self._receipt['title'].upper()}"
            p.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, rec_text)
        else:
            p.setFont(QFont("Segoe UI", 9))
            p.setPen(GREEN_COLOR)
            p.drawText(QRectF(x1 - 160, 24, 160, 32), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "●  SYSTEM ONLINE")

        # Live telemetry bars
        s = self._sys
        batt = s["batt"]
        if batt is None:
            batt_txt, batt_val, batt_col = "No battery", 0.0, MUTED_COLOR
        else:
            charging = "  ⚡ charging" if s["plugged"] else ""
            batt_txt, batt_val = f"{batt:.0f}%{charging}", batt / 100
            batt_col = GREEN_COLOR if batt > 40 or s["plugged"] else AMBER_COLOR if batt > 20 else RED_COLOR
        rows = [
            ("BATTERY", batt_txt, batt_val, batt_col),
            ("CPU LOAD", f"{s['cpu']:.0f}%", s["cpu"] / 100, self._load_color(s["cpu"])),
            ("MEMORY", f"{s['mem']:.0f}%", s["mem"] / 100, self._load_color(s["mem"])),
        ]
        y = 76
        for label, value, frac, col in rows:
            self._bar(p, x0, x1, y, label, value, frac, col)
            y += 48

        # Text rows: Weather & Project
        self._text_row(p, x0, x1, 224, "WEATHER", self._weather, self._theme["primary"])
        self._text_row(p, x0, x1, 258, "PROJECT", self._project, self._theme["accent"])

        # Ghost Subtitle pill or Hint line
        sub_rect = QRectF(x0, 292, x1 - x0, 28)
        p.setBrush(QColor(15, 23, 42, 190))
        p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 90), 1))
        p.drawRoundedRect(sub_rect, 14, 14)

        if self._subtitle:
            p.setFont(QFont("Segoe UI", 9, QFont.Bold))
            p.setPen(accent)
            p.drawText(sub_rect.adjusted(14, 0, -14, 0), Qt.AlignLeft | Qt.AlignVCenter, self._subtitle)
        else:
            p.setFont(QFont("Segoe UI", 8))
            p.setPen(MUTED_COLOR)
            p.drawText(sub_rect.adjusted(14, 0, -14, 0), Qt.AlignLeft | Qt.AlignVCenter, "💡 Click to toggle compact pill · Right-click to switch theme")

    @staticmethod
    def _load_color(v: float) -> QColor:
        return GREEN_COLOR if v < 60 else AMBER_COLOR if v < 85 else RED_COLOR

    @staticmethod
    def _bar(p: QPainter, x0: float, x1: float, y: float, label: str, value: str, frac: float, col: QColor) -> None:
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(MUTED_COLOR)
        p.drawText(QRectF(x0, y, 160, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        p.setPen(TEXT_COLOR)
        p.drawText(QRectF(x0, y, x1 - x0, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, value)
        track = QRectF(x0, y + 20, x1 - x0, 5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(30, 41, 59))
        p.drawRoundedRect(track, 2.5, 2.5)
        fill = QRectF(track.x(), track.y(), track.width() * max(0.02, min(1.0, frac)), track.height())
        p.setBrush(col)
        p.drawRoundedRect(fill, 2.5, 2.5)

    @staticmethod
    def _text_row(p: QPainter, x0: float, x1: float, y: float, label: str, value: str, col: QColor) -> None:
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(MUTED_COLOR)
        p.drawText(QRectF(x0, y, 80, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(col)
        fm = p.fontMetrics()
        elided = fm.elidedText(value, Qt.TextElideMode.ElideRight, int(x1 - x0 - 90))
        p.drawText(QRectF(x0 + 90, y, x1 - x0 - 90, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)


# --------------------------------------------------------------------------- #
# 6. Singleton + Cross-Thread Signal Bridge
# --------------------------------------------------------------------------- #

_instance: WakeOverlay | None = None


def get_wake_overlay() -> WakeOverlay:
    """Create (once) and return the overlay. Needs a QApplication to exist."""
    global _instance
    if _instance is None:
        _instance = WakeOverlay()
    return _instance


class _OverlayBridge(QObject):
    state_requested = Signal(str)
    subtitle_requested = Signal(str)
    audio_requested = Signal(float)
    receipt_requested = Signal(str, str, str)
    theme_requested = Signal(str)
    mode_requested = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.state_requested.connect(self._handle_state)
        self.subtitle_requested.connect(self._handle_subtitle)
        self.audio_requested.connect(self._handle_audio)
        self.receipt_requested.connect(self._handle_receipt)
        self.theme_requested.connect(self._handle_theme)
        self.mode_requested.connect(self._handle_mode)

    def _handle_state(self, state: str) -> None:
        overlay = get_wake_overlay()
        st = state.upper()
        if st == "LISTENING":
            overlay.show_listening()
        elif st == "HIDE":
            overlay.hide_overlay()
        else:
            overlay.set_state(st)

    def _handle_subtitle(self, text: str) -> None:
        get_wake_overlay().set_subtitle(text)

    def _handle_audio(self, level: float) -> None:
        get_wake_overlay().set_audio_level(level)

    def _handle_receipt(self, icon: str, title: str, detail: str) -> None:
        get_wake_overlay().show_receipt(icon, title, detail)

    def _handle_theme(self, theme_name: str) -> None:
        get_wake_overlay().set_theme(theme_name)

    def _handle_mode(self, mode: str) -> None:
        get_wake_overlay().set_mode(mode)


_bridge: _OverlayBridge | None = None


def init_overlay_bridge(app: Any = None) -> _OverlayBridge:
    """Initialize the overlay dispatcher bridge on the Qt GUI thread."""
    global _bridge
    if _bridge is None:
        _bridge = _OverlayBridge()
        if app is not None and hasattr(app, "thread"):
            _bridge.moveToThread(app.thread())
    return _bridge


def _ensure_bridge() -> _OverlayBridge | None:
    app = QApplication.instance()
    if app is None:
        return None
    global _bridge
    if _bridge is None:
        _bridge = init_overlay_bridge(app)
    return _bridge


def notify_wake_overlay(state: str) -> None:
    """Safely notify the wake overlay from any thread."""
    try:
        bridge = _ensure_bridge()
        if bridge:
            bridge.state_requested.emit(state)
    except Exception:
        pass


def notify_wake_overlay_subtitle(text: str) -> None:
    """Safely send ghost subtitle text from any thread."""
    try:
        bridge = _ensure_bridge()
        if bridge:
            bridge.subtitle_requested.emit(text)
    except Exception:
        pass


def notify_wake_overlay_audio(level: float) -> None:
    """Safely stream voice energy / volume level (0.0 to 1.0) from any thread."""
    try:
        bridge = _ensure_bridge()
        if bridge:
            bridge.audio_requested.emit(level)
    except Exception:
        pass


def notify_wake_overlay_receipt(icon: str, title: str, detail: str = "") -> None:
    """Safely show action receipt badge from any thread."""
    try:
        bridge = _ensure_bridge()
        if bridge:
            bridge.receipt_requested.emit(icon, title, detail)
    except Exception:
        pass


def notify_wake_overlay_theme(theme_name: str) -> None:
    """Safely switch HUD color theme from any thread."""
    try:
        bridge = _ensure_bridge()
        if bridge:
            bridge.theme_requested.emit(theme_name)
    except Exception:
        pass


def notify_wake_overlay_mode(mode: str) -> None:
    """Safely switch between 'expanded' and 'compact' mode from any thread."""
    try:
        bridge = _ensure_bridge()
        if bridge:
            bridge.mode_requested.emit(mode)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# 7. Interactive Multi-Feature Demo
# --------------------------------------------------------------------------- #


def _demo() -> int:
    """Interactive preview showcasing all 7 upgrades."""
    app = QApplication.instance() or QApplication(sys.argv)
    init_overlay_bridge(app)
    ov = get_wake_overlay()

    # Step 1: Wake listening with JARVIS theme
    QTimer.singleShot(200, ov.show_listening)
    QTimer.singleShot(400, lambda: ov.set_subtitle("> Turn on notepad and write hi"))

    # Audio reactivity simulation
    for idx in range(12):
        lvl = 0.2 + 0.7 * abs(math.sin(idx * 0.8))
        QTimer.singleShot(600 + idx * 120, lambda l=lvl: ov.set_audio_level(l))

    # Step 2: Processing state with action execution
    QTimer.singleShot(2600, lambda: ov.set_state("PROCESSING"))
    QTimer.singleShot(2700, lambda: ov.set_subtitle("⚡ Executing action: open_application"))

    # Step 3: Action receipt pop-up
    QTimer.singleShot(4200, lambda: ov.show_receipt("🚀", "Notepad Launched", "PID 20420"))

    # Step 4: Speaking state with Cyberpunk theme switch
    QTimer.singleShot(4500, lambda: ov.set_state("SPEAKING"))
    QTimer.singleShot(4800, lambda: ov.set_theme("CYBERPUNK"))
    QTimer.singleShot(5000, lambda: ov.set_subtitle("Denver: I've opened Notepad for you."))

    # Step 5: Switch to Matrix theme & morph to Compact Island mode
    QTimer.singleShot(7200, lambda: ov.set_theme("MATRIX"))
    QTimer.singleShot(7800, lambda: ov.set_mode("compact"))

    # Step 6: Expand back and standby fade out
    QTimer.singleShot(10500, lambda: ov.set_mode("expanded"))
    QTimer.singleShot(11200, lambda: ov.set_state("STANDBY"))
    QTimer.singleShot(13500, app.quit)

    return app.exec()


if __name__ == "__main__":
    if "--demo" in sys.argv:
        sys.exit(_demo())
    print("Run with: python wake_overlay.py --demo")
