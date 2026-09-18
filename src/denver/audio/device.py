"""Audio device discovery and hardware endpoint inspection for Denver."""

from __future__ import annotations

import ctypes
import platform
from typing import Any

from denver.audio.models import AudioDevice
from denver.logging.logger import get_logger

logger = get_logger("audio.device")

_IS_WINDOWS = platform.system() == "Windows"

# Check sounddevice availability
try:
    import sounddevice as sd
    _SOUNDDEVICE_AVAILABLE = True
except (ImportError, OSError):
    _SOUNDDEVICE_AVAILABLE = False


class _WAVEINCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", ctypes.c_ushort),
        ("wPid", ctypes.c_ushort),
        ("vDriverVersion", ctypes.c_uint),
        ("szPname", ctypes.c_wchar * 32),
        ("dwFormats", ctypes.c_uint),
        ("wChannels", ctypes.c_ushort),
        ("wReserved1", ctypes.c_ushort),
    ]


class _WAVEOUTCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", ctypes.c_ushort),
        ("wPid", ctypes.c_ushort),
        ("vDriverVersion", ctypes.c_uint),
        ("szPname", ctypes.c_wchar * 32),
        ("dwFormats", ctypes.c_uint),
        ("wChannels", ctypes.c_ushort),
        ("wReserved1", ctypes.c_ushort),
        ("dwSupport", ctypes.c_uint),
    ]


class AudioDeviceManager:
    """Manages audio endpoint discovery, default device selection, and capability inspection."""

    def __init__(self) -> None:
        self._cached_devices: list[AudioDevice] | None = None

    def list_devices(self, force_refresh: bool = False) -> list[AudioDevice]:
        """Query and return all accessible audio input and output endpoints."""
        if self._cached_devices is not None and not force_refresh:
            return list(self._cached_devices)

        devices: list[AudioDevice] = []

        if _SOUNDDEVICE_AVAILABLE:
            try:
                sd_devices = sd.query_devices()
                default_in, default_out = sd.default.device
                for idx, d in enumerate(sd_devices):
                    is_in = d.get("max_input_channels", 0) > 0
                    is_out = d.get("max_output_channels", 0) > 0
                    is_def = (idx == default_in if is_in else idx == default_out)
                    channels = max(d.get("max_input_channels", 0), d.get("max_output_channels", 0))

                    devices.append(
                        AudioDevice(
                            index=idx,
                            name=str(d.get("name", f"Device {idx}")),
                            channels=channels,
                            default_samplerate=int(d.get("default_samplerate", 16000)),
                            is_input=is_in,
                            is_output=is_out,
                            is_default=is_def,
                            host_api=str(d.get("hostapi", "PortAudio")),
                        )
                    )
                self._cached_devices = devices
                return list(devices)
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("sounddevice query failed, falling back to winmm: %s", exc)

        # Fallback for Windows winmm
        if _IS_WINDOWS:
            try:
                winmm = ctypes.windll.winmm
                in_count = winmm.waveInGetNumDevs()
                for i in range(in_count):
                    caps = _WAVEINCAPSW()
                    if winmm.waveInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
                        devices.append(
                            AudioDevice(
                                index=i,
                                name=caps.szPname.strip() or f"Microphone {i}",
                                channels=caps.wChannels or 1,
                                default_samplerate=16000,
                                is_input=True,
                                is_output=False,
                                is_default=(i == 0),
                                host_api="winmm",
                            )
                        )

                out_count = winmm.waveOutGetNumDevs()
                for i in range(out_count):
                    caps = _WAVEOUTCAPSW()
                    if winmm.waveOutGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
                        devices.append(
                            AudioDevice(
                                index=1000 + i,
                                name=caps.szPname.strip() or f"Speaker {i}",
                                channels=caps.wChannels or 2,
                                default_samplerate=44100,
                                is_input=False,
                                is_output=True,
                                is_default=(i == 0),
                                host_api="winmm",
                            )
                        )
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("winmm audio query failed: %s", exc)

        self._cached_devices = devices
        return list(devices)

    def list_input_devices(self) -> list[AudioDevice]:
        """Return list of available microphone endpoints."""
        return [d for d in self.list_devices() if d.is_input]

    def list_output_devices(self) -> list[AudioDevice]:
        """Return list of available speaker/headphone endpoints."""
        return [d for d in self.list_devices() if d.is_output]

    def get_default_input_device(self) -> AudioDevice | None:
        """Find the preferred/default microphone."""
        inputs = self.list_input_devices()
        for d in inputs:
            if d.is_default:
                return d
        return inputs[0] if inputs else None

    def get_default_output_device(self) -> AudioDevice | None:
        """Find the preferred/default output speaker."""
        outputs = self.list_output_devices()
        for d in outputs:
            if d.is_default:
                return d
        return outputs[0] if outputs else None

    def get_device_by_name_or_index(self, target: str | int | None, is_input: bool = True) -> AudioDevice | None:
        """Find specific device by index or partial name match."""
        if target is None:
            return self.get_default_input_device() if is_input else self.get_default_output_device()

        devices = self.list_input_devices() if is_input else self.list_output_devices()

        if isinstance(target, int):
            for d in devices:
                if d.index == target:
                    return d
            return None

        # String search
        target_lower = str(target).lower().strip()
        for d in devices:
            if target_lower in d.name.lower():
                return d

        return None

    def get_device_by_index(self, index: int) -> AudioDevice | None:
        """Find specific audio device by absolute index."""
        for d in self.list_devices():
            if d.index == index:
                return d
        return None

    def get_health_status(self) -> dict[str, Any]:
        """Produce hardware audio endpoint diagnostic health summary."""
        in_devs = self.list_input_devices()
        out_devs = self.list_output_devices()

        status = "READY"
        if not in_devs and not out_devs:
            status = "UNAVAILABLE"
        elif not in_devs or not out_devs:
            status = "DEGRADED"

        return {
            "status": status,
            "input_devices": [d.to_dict() for d in in_devs],
            "output_devices": [d.to_dict() for d in out_devs],
            "default_input": self.get_default_input_device().to_dict() if self.get_default_input_device() else None,
            "default_output": self.get_default_output_device().to_dict() if self.get_default_output_device() else None,
        }
