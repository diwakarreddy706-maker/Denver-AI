"""Unit tests for Denver AudioDeviceManager."""

import pytest
from denver.audio.device import AudioDeviceManager
from denver.audio.models import AudioDevice


def test_device_manager_initialization() -> None:
    dm = AudioDeviceManager()
    assert dm is not None


def test_device_manager_list_devices() -> None:
    dm = AudioDeviceManager()
    devices = dm.list_devices()
    assert isinstance(devices, list)

    input_devices = dm.list_input_devices()
    assert all(d.is_input for d in input_devices)

    output_devices = dm.list_output_devices()
    assert all(d.is_output for d in output_devices)


def test_device_manager_get_device_by_index() -> None:
    dm = AudioDeviceManager()
    dev = dm.get_device_by_index(99999)
    assert dev is None


def test_device_manager_health_status() -> None:
    dm = AudioDeviceManager()
    health = dm.get_health_status()
    assert "status" in health
    assert health["status"] in {"READY", "DEGRADED", "UNAVAILABLE"}
    assert "input_devices" in health
    assert "output_devices" in health
