"""Unit tests for Denver Portable Release Builder."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from denver.release.builder import PortableReleaseBuilder


class TestPortableReleaseBuilder(unittest.TestCase):
    """Test suite for PortableReleaseBuilder discovery, staging, exclusion, dry-run, and ZIP creation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.mock_root = self.base_dir / "mock_project"
        self.mock_root.mkdir()

        # Set up mock file structure
        (self.mock_root / "main.py").write_text("# entrypoint", encoding="utf-8")
        (self.mock_root / "pyproject.toml").write_text("[project]\nname='denver'", encoding="utf-8")
        (self.mock_root / ".env.example").write_text("GROQ_API_KEY=your_groq_api_key_here\n", encoding="utf-8")
        (self.mock_root / "README.md").write_text("# Denver", encoding="utf-8")

        # Source tree
        src_dir = self.mock_root / "src" / "denver"
        src_dir.mkdir(parents=True)
        (src_dir / "__init__.py").write_text("__version__ = '0.1.0'", encoding="utf-8")
        (src_dir / "core.py").write_text("class Denver: pass", encoding="utf-8")

        # Pycache that must be excluded
        pycache_dir = src_dir / "__pycache__"
        pycache_dir.mkdir()
        (pycache_dir / "core.cpython-314.pyc").write_bytes(b"fake bytecode")

        # Data tree
        data_dir = self.mock_root / "data"
        data_dir.mkdir()
        (data_dir / "apps.json").write_text("[]", encoding="utf-8")
        (data_dir / "contacts.json").write_text("[]", encoding="utf-8")
        # Forbidden sqlite file in data/
        (data_dir / "denver_memory.sqlite3").write_bytes(b"sqlite db")

        # Forbidden secret .env at root
        (self.mock_root / ".env").write_text("GROQ_API_KEY=gsk_forbiddenLiveKey1234567890", encoding="utf-8")

        self.builder = PortableReleaseBuilder(project_root=self.mock_root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_file_collection_excludes_secrets_databases_and_pycache(self) -> None:
        files = self.builder.collect_source_files()
        file_names = {f.name for f in files}

        # Safe files included
        self.assertIn("main.py", file_names)
        self.assertIn(".env.example", file_names)
        self.assertIn("apps.json", file_names)
        self.assertIn("core.py", file_names)

        # Unsafe / cache files excluded
        self.assertNotIn(".env", file_names)
        self.assertNotIn("denver_memory.sqlite3", file_names)
        self.assertNotIn("core.cpython-314.pyc", file_names)

    def test_dry_run_build_does_not_create_zip(self) -> None:
        out_dir = self.base_dir / "dist"
        result = self.builder.build(output_dir=out_dir, dry_run=True)

        self.assertTrue(result.success)
        self.assertTrue(result.dry_run)
        self.assertGreater(result.files_copied, 0)
        self.assertFalse(out_dir.exists())

    def test_live_build_creates_and_verifies_zip(self) -> None:
        out_dir = self.base_dir / "dist"
        result = self.builder.build(output_dir=out_dir, dry_run=False, run_verifier=True)

        self.assertTrue(result.success)
        self.assertFalse(result.dry_run)
        self.assertIsNotNone(result.zip_path)
        self.assertTrue(result.zip_path.exists())

        # Inspect generated zip
        with zipfile.ZipFile(result.zip_path, "r") as zf:
            names = zf.namelist()
            self.assertTrue(any("main.py" in n for n in names))
            self.assertTrue(any(".env.example" in n for n in names))
            self.assertFalse(any(".env" == n or n.endswith("/.env") for n in names))
            self.assertFalse(any(".sqlite3" in n for n in names))
            self.assertFalse(any("__pycache__" in n for n in names))

        self.assertIsNotNone(result.verification_report)
        self.assertTrue(result.verification_report.is_valid)


if __name__ == "__main__":
    unittest.main()
