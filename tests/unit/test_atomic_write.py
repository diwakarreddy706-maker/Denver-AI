"""Unit tests for Atomic File Writing Utility."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from denver.utils.atomic_write import atomic_write_json, atomic_write_text


class TestAtomicWrite(unittest.TestCase):
    """Test suite for atomic file writing and JSON serialization."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_atomic_write_text(self) -> None:
        target = self.base_dir / "nested" / "test.txt"
        atomic_write_text(target, "Hello Denver Atomic!")

        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(encoding="utf-8"), "Hello Denver Atomic!")

        # Overwrite atomically
        atomic_write_text(target, "Overwritten cleanly.")
        self.assertEqual(target.read_text(encoding="utf-8"), "Overwritten cleanly.")

    def test_atomic_write_json(self) -> None:
        target = self.base_dir / "data.json"
        data = {"key": "value", "count": 42, "active": True}
        atomic_write_json(target, data)

        self.assertTrue(target.exists())
        loaded = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(loaded, data)


if __name__ == "__main__":
    unittest.main()
