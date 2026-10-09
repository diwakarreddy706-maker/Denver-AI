"""Unit tests for Denver Windows autostart launcher."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from denver.automation.autostart import (
    STARTUP_FILENAME,
    disable_autostart,
    enable_autostart,
    generate_vbs_content,
    get_autostart_info,
    get_autostart_path,
    is_autostart_enabled,
)


def test_generate_vbs_content() -> None:
    fake_proj = Path("C:/Users/test/Denver")
    vbs = generate_vbs_content(project_dir=fake_proj, headless=True)

    assert "WScript.Shell" in vbs
    assert "WshShell.CurrentDirectory = \"C:\\Users\\test\\Denver\"" in vbs
    assert "--headless" in vbs
    assert ", 0, False" in vbs


def test_enable_and_disable_autostart() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_startup = Path(tmp_dir) / "Startup"
        fake_proj = Path(tmp_dir) / "Project"
        fake_proj.mkdir()

        with patch("denver.automation.autostart.get_startup_directory", return_value=fake_startup):
            with patch("denver.automation.autostart.get_project_root", return_value=fake_proj):
                # Initially disabled
                assert not is_autostart_enabled()

                # Enable autostart
                vbs_path = enable_autostart(project_dir=fake_proj, headless=True)
                assert vbs_path.is_file()
                assert vbs_path.name == STARTUP_FILENAME
                assert is_autostart_enabled()

                # Check file content written directly by Python
                content = vbs_path.read_text(encoding="utf-8")
                assert "WScript.Shell" in content
                assert str(fake_proj) in content

                # Check info dictionary
                info = get_autostart_info()
                assert info["enabled"] is True
                assert info["path"] == str(vbs_path)

                # Disable autostart
                disabled = disable_autostart()
                assert disabled is True
                assert not vbs_path.exists()
                assert not is_autostart_enabled()

                # Second disable should be False gracefully
                assert disable_autostart() is False
