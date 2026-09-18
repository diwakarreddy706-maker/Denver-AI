"""Unit tests for Denver Release Artifact & Package Verifier."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from denver.release.verifier import ReleaseArtifactVerifier


class TestReleaseArtifactVerifier(unittest.TestCase):
    """Test suite for directory scanning, ZIP auditing, secret leakage detection, and path traversal."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.verifier = ReleaseArtifactVerifier()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_clean_directory_passes_verification(self) -> None:
        pkg_dir = self.base_dir / "clean_pkg"
        pkg_dir.mkdir()

        (pkg_dir / "README.md").write_text("# Denver AI", encoding="utf-8")
        (pkg_dir / "LICENSE").write_text("MIT License", encoding="utf-8")
        (pkg_dir / "SECURITY.md").write_text("Security policy", encoding="utf-8")
        (pkg_dir / ".env.example").write_text("GROQ_API_KEY=your_groq_api_key_here\nPORT=8000\n", encoding="utf-8")

        report = self.verifier.verify_directory(pkg_dir)
        self.assertTrue(report.is_valid)
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.scanned_count, 4)

    def test_leaked_secret_and_env_fails_verification(self) -> None:
        pkg_dir = self.base_dir / "leaky_pkg"
        pkg_dir.mkdir()

        # Real .env file forbidden
        (pkg_dir / ".env").write_text("GROQ_API_KEY=gsk_realActiveSecretKey1234567890\n", encoding="utf-8")

        # SQLite database file forbidden
        (pkg_dir / "app.sqlite3").write_text("fake db content", encoding="utf-8")

        # Source code with hardcoded secret
        src_dir = pkg_dir / "src"
        src_dir.mkdir()
        (src_dir / "config.py").write_text('API_KEY = "sk-liveOpenAISecretKey1234567890"', encoding="utf-8")

        report = self.verifier.verify_directory(pkg_dir)
        self.assertFalse(report.is_valid)
        self.assertGreaterEqual(report.error_count, 3)

    def test_zip_archive_verification_and_traversal_detection(self) -> None:
        zip_path = self.base_dir / "test_release.zip"

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("README.md", "# Denver AI")
            zf.writestr(".env.example", "GEMINI_API_KEY=your_gemini_api_key_here\n")
            # Leaky entry inside zip
            zf.writestr("secrets.json", '{"key": "gsk_liveSecretKey9988776655"}')

        report = self.verifier.verify_zip(zip_path)
        self.assertFalse(report.is_valid)
        self.assertEqual(report.scanned_count, 3)
        self.assertTrue(any("secrets.json" in f.path for f in report.findings))


if __name__ == "__main__":
    unittest.main()
