"""Unit tests for Push-to-Talk (PTT) Global Hotkey Controller."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from denver.audio.push_to_talk import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    MOD_WIN,
    PushToTalkListener,
    parse_hotkey_string,
)


def test_parse_hotkey_string_valid() -> None:
    # ctrl+space
    mods, vk = parse_hotkey_string("ctrl+space")
    assert mods & MOD_CONTROL
    assert mods & MOD_NOREPEAT
    assert vk == 0x20

    # alt+d
    mods, vk = parse_hotkey_string("alt+d")
    assert mods & MOD_ALT
    assert vk == ord("D")

    # ctrl+shift+f1
    mods, vk = parse_hotkey_string("ctrl+shift+f1")
    assert mods & MOD_CONTROL
    assert mods & MOD_SHIFT
    assert vk == 0x70

    # win+space
    mods, vk = parse_hotkey_string("win+space")
    assert mods & MOD_WIN
    assert vk == 0x20


def test_parse_hotkey_string_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid hotkey specification"):
        parse_hotkey_string("")

    with pytest.raises(ValueError, match="No valid non-modifier key"):
        parse_hotkey_string("ctrl+shift")

    with pytest.raises(ValueError, match="Unknown key"):
        parse_hotkey_string("ctrl+nonexistentkey")


def test_ptt_listener_manual_trigger() -> None:
    called = []

    def callback() -> None:
        called.append(True)

    listener = PushToTalkListener(hotkey="ctrl+space", on_trigger=callback)
    listener.trigger()

    assert called == [True]


@pytest.mark.asyncio
async def test_ptt_listener_async_trigger() -> None:
    called = []

    async def async_callback() -> None:
        called.append(True)

    loop = asyncio.get_running_loop()
    listener = PushToTalkListener(
        hotkey="alt+d",
        on_trigger=async_callback,
        loop=loop,
    )
    listener.trigger()
    await asyncio.sleep(0.05)

    assert called == [True]


def test_ptt_listener_start_stop() -> None:
    listener = PushToTalkListener(hotkey="ctrl+space", on_trigger=lambda: None)
    assert not listener.is_running

    # Test lifecycle
    listener.start()
    assert listener.is_running

    listener.stop()
    assert not listener.is_running
