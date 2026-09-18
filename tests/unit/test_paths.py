"""Unit tests for Denver runtime path resolution and release utilities."""

import os
from pathlib import Path
from unittest.mock import patch

from denver.config.paths import (
    get_app_root,
    get_user_data_dir,
    is_frozen,
    resolve_runtime_path,
)


def test_is_frozen_false_in_dev():
    assert is_frozen() is False


def test_get_app_root_returns_existing_path():
    root = get_app_root()
    assert isinstance(root, Path)
    assert root.exists()
    assert (root / "pyproject.toml").exists() or (root / "src").exists()


def test_get_user_data_dir_creates_dir(tmp_path):
    with patch.dict(os.environ, {"DENVER_USER_DATA_DIR": str(tmp_path / "denver_test_dir")}):
        data_dir = get_user_data_dir()
        assert data_dir.exists()
        assert data_dir == tmp_path / "denver_test_dir"


def test_resolve_runtime_path_absolute(tmp_path):
    abs_path = tmp_path / "some_file.txt"
    resolved = resolve_runtime_path(abs_path)
    assert resolved == abs_path


def test_resolve_runtime_path_relative():
    rel_path = Path("logs/denver.log")
    resolved = resolve_runtime_path(rel_path)
    assert resolved == rel_path
