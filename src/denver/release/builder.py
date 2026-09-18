"""Automated Windows Portable Release Builder for Denver AI Assistant."""

from __future__ import annotations

import os
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from denver import __version__, product_name
from denver.logging.logger import get_logger
from denver.release.verifier import ReleaseArtifactVerifier, VerificationReport

logger = get_logger("release.builder")

DENIED_DIRS = {
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".vscode",
    "build",
    "dist",
    "logs",
    "meetings",
    "_reference_repo",
    "reference_file",
}

DENIED_EXTENSIONS = {
    ".sqlite3",
    ".db",
    ".pyc",
    ".pyd",
}

DENIED_EXACT_FILES = {
    ".env",
    ".env.local",
    "denver_memory.sqlite3",
    "denver_vault.dat",
    "audit_vault.dat",
    "secrets.json",
}

ALLOWED_DATA_FILES = {
    "apps.json",
    "contacts.json",
    "routines.json",
    "plugin_state.json",
    ".gitkeep",
}


@dataclass
class BuildResult:
    """Outcome of a portable build run."""

    success: bool
    version: str = __version__
    dry_run: bool = False
    stage_dir: Path | None = None
    zip_path: Path | None = None
    files_copied: int = 0
    total_bytes: int = 0
    verification_report: VerificationReport | None = None
    errors: list[str] = field(default_factory=list)

    def format_summary(self) -> str:
        """Format a human-readable summary of the build outcome."""
        status = "SUCCESS" if self.success else "FAILED"
        lines = [
            f"=== {product_name} Portable Build Summary ===",
            f"  • Version: v{self.version}",
            f"  • Mode: {'DRY RUN (No files modified/created)' if self.dry_run else 'LIVE BUILD'}",
            f"  • Status: {status}",
            f"  • Staged Files: {self.files_copied} ({self.total_bytes / (1024 * 1024):.2f} MB)",
        ]
        if self.stage_dir:
            lines.append(f"  • Staging Directory: {self.stage_dir}")
        if self.zip_path and not self.dry_run:
            lines.append(f"  • Distribution Package: {self.zip_path}")
        if self.verification_report:
            lines.append(f"  • Security Verification: {'PASS (0 Findings)' if self.verification_report.is_valid else f'FAIL ({self.verification_report.error_count} Errors)'}")
        if self.errors:
            lines.append("  • Build Errors:")
            for err in self.errors:
                lines.append(f"    - {err}")
        return "\n".join(lines)


class PortableReleaseBuilder:
    """Builds, stages, and packages safe portable distribution packages for Windows."""

    def __init__(self, project_root: str | Path | None = None, verifier: ReleaseArtifactVerifier | None = None) -> None:
        if project_root is None:
            # Default to root of the repo (3 levels up from this file: src/denver/release/ -> project_root)
            self.project_root = Path(__file__).resolve().parent.parent.parent.parent
        else:
            self.project_root = Path(project_root).resolve()
        self.verifier = verifier or ReleaseArtifactVerifier()

    def _should_include_file(self, rel_path: Path) -> bool:
        """Evaluate whether a file should be included in the portable release package."""
        parts = rel_path.parts
        # Check forbidden directory in any path component
        for part in parts[:-1]:
            if part in DENIED_DIRS:
                return False

        filename = rel_path.name
        if filename in DENIED_EXACT_FILES:
            return False

        if rel_path.suffix.lower() in DENIED_EXTENSIONS:
            return False

        # If file is inside data/, only allow safe seed datasets
        if parts[0] == "data" and len(parts) > 1:
            if parts[1] == "cache" or parts[1] == "screenshots" or parts[1] == "meetings":
                return False
            if filename not in ALLOWED_DATA_FILES:
                return False

        return True

    def collect_source_files(self) -> list[Path]:
        """Discover all files in the project suitable for inclusion."""
        collected: list[Path] = []

        # 1. Top-level files
        root_candidates = [
            "main.py",
            "pyproject.toml",
            ".env.example",
            "README.md",
            "LICENSE",
            "CHECKPOINT.md",
        ]
        for name in root_candidates:
            p = self.project_root / name
            if p.is_file():
                collected.append(p)

        # 2. Source directories to scan recursively
        scan_dirs = ["src", "plugins", "data", "docs"]
        for d in scan_dirs:
            dir_path = self.project_root / d
            if not dir_path.is_dir():
                continue
            for root, dirs, files in os.walk(dir_path):
                # Prune forbidden directories in-place
                dirs[:] = [sub for sub in dirs if sub not in DENIED_DIRS]
                for file in files:
                    file_path = Path(root) / file
                    try:
                        rel = file_path.relative_to(self.project_root)
                        if self._should_include_file(rel):
                            collected.append(file_path)
                    except ValueError:
                        continue

        return sorted(list(set(collected)))

    def build(
        self,
        output_dir: str | Path | None = None,
        zip_name: str | None = None,
        dry_run: bool = False,
        run_verifier: bool = True,
    ) -> BuildResult:
        """Assemble the portable package, compress into ZIP, and verify safety."""
        out_root = Path(output_dir or (self.project_root / "dist")).resolve()
        package_name = f"Denver-v{__version__}-Windows-Portable"
        stage_dir = out_root / package_name
        zip_path = out_root / f"{zip_name or package_name}.zip"

        result = BuildResult(
            success=False,
            version=__version__,
            dry_run=dry_run,
            stage_dir=stage_dir,
            zip_path=zip_path,
        )

        files_to_pack = self.collect_source_files()
        if not files_to_pack:
            result.errors.append("No source files found to package.")
            return result

        result.files_copied = len(files_to_pack)
        result.total_bytes = sum(p.stat().st_size for p in files_to_pack if p.exists())

        if dry_run:
            logger.info("Dry run completed: %d files (%d bytes) ready for portable build.", len(files_to_pack), result.total_bytes)
            result.success = True
            return result

        try:
            # Clean and recreate staging directory
            if stage_dir.exists():
                shutil.rmtree(stage_dir)
            stage_dir.mkdir(parents=True, exist_ok=True)

            # Copy all files preserving relative path structure
            for src_file in files_to_pack:
                rel_path = src_file.relative_to(self.project_root)
                dest_file = stage_dir / rel_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dest_file)

            # Package into ZIP archive
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            if zip_path.exists():
                zip_path.unlink()

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(stage_dir):
                    for file in files:
                        abs_p = Path(root) / file
                        arcname = abs_p.relative_to(stage_dir)
                        zf.write(abs_p, arcname=str(arcname))

            logger.info("Successfully created portable distribution ZIP at: %s", zip_path)

            # Run Release Artifact Verification
            if run_verifier:
                report = self.verifier.verify_zip(zip_path)
                result.verification_report = report
                if not report.is_valid:
                    result.errors.append(f"Security verification failed with {report.error_count} error(s).")
                    result.success = False
                    return result

            result.success = True
            return result

        except Exception as exc:
            logger.exception("Portable build failed: %s", exc)
            result.errors.append(f"Build failed with exception: {exc}")
            result.success = False
            return result
