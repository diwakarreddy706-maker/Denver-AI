"""Release Artifact & Portable Package Security Verifier for Denver AI Assistant."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from denver.logging.logger import get_logger

logger = get_logger("release.verifier")

TEXT_SUFFIXES = {".txt", ".md", ".json", ".example", ".ini", ".cfg", ".toml", ".yaml", ".yml", ".py"}

SECRET_PATTERNS = [
    re.compile(r"gsk_[A-Za-z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"AIzaSy[A-Za-z0-9_-]{33}", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}", re.IGNORECASE),
    re.compile(r"api[-_]?key\s*[:=]\s*['\"]?(?!your_|\*\*\*|placeholder)[A-Za-z0-9_\-]{20,}['\"]?", re.IGNORECASE),
]

LOCAL_PATH_PATTERN = re.compile(r"[a-zA-Z]:\\Users\\[a-zA-Z0-9_\-]+", re.IGNORECASE)

DENIED_EXACT_NAMES = {".env", ".env.local", "denver_vault.dat", "audit_vault.dat", "secrets.json"}
DENIED_SUFFIXES = {".sqlite3", ".db", ".pyc", ".pyd"}
DENIED_DIR_NAMES = {"__pycache__", ".git", ".pytest_cache", ".ruff_cache", "logs", "meetings"}

SAFE_PLACEHOLDERS = {
    "",
    "false",
    "true",
    "your_groq_api_key_here",
    "your_gemini_api_key_here",
    "your_spotify_client_secret_here",
    "your_openai_api_key_here",
    "your_openrouter_api_key_here",
    "***",
}


@dataclass(frozen=True)
class ArtifactFinding:
    path: str
    reason: str
    severity: str = "ERROR"  # ERROR, WARNING


@dataclass
class VerificationReport:
    target: str
    scanned_count: int = 0
    findings: list[ArtifactFinding] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len([f for f in self.findings if f.severity == "ERROR"]) == 0

    @property
    def error_count(self) -> int:
        return len([f for f in self.findings if f.severity == "ERROR"])

    @property
    def warning_count(self) -> int:
        return len([f for f in self.findings if f.severity == "WARNING"])

    def format_summary(self) -> str:
        status_str = "PASS (Safe for distribution)" if self.is_valid else "FAIL (Security issues detected)"
        lines = [
            f"Release Artifact Verification for: {self.target}",
            f"  • Scanned Files: {self.scanned_count}",
            f"  • Errors: {self.error_count}",
            f"  • Warnings: {self.warning_count}",
            f"  • Status: {status_str}",
        ]
        if self.findings:
            lines.append("  • Findings:")
            for f in self.findings:
                lines.append(f"    - [{f.severity}] {f.path}: {f.reason}")
        return "\n".join(lines)


class ReleaseArtifactVerifier:
    """Verifies release builds, staging directories, and ZIP packages before distribution."""

    def verify_target(self, target_path: str | Path) -> VerificationReport:
        target = Path(target_path)
        if not target.exists():
            report = VerificationReport(target=str(target_path))
            report.findings.append(ArtifactFinding(path=str(target_path), reason="Target file or directory does not exist", severity="ERROR"))
            return report

        if target.is_dir():
            return self.verify_directory(target)
        elif target.suffix.lower() == ".zip":
            return self.verify_zip(target)
        else:
            report = VerificationReport(target=str(target_path))
            report.findings.append(ArtifactFinding(path=str(target_path), reason="Unsupported target (must be a directory or .zip archive)", severity="ERROR"))
            return report

    def verify_directory(self, dir_path: Path) -> VerificationReport:
        report = VerificationReport(target=str(dir_path))
        
        for p in dir_path.rglob("*"):
            if p.is_dir():
                if p.name in DENIED_DIR_NAMES:
                    report.findings.append(ArtifactFinding(path=str(p.relative_to(dir_path)), reason=f"Disallowed directory '{p.name}' in package", severity="ERROR"))
                continue

            rel_path = str(p.relative_to(dir_path))
            report.scanned_count += 1

            # 1. Path and filename checks
            self._check_filename_safety(rel_path, p.name, p.suffix.lower(), report)

            # 2. Content text checks
            if p.suffix.lower() in TEXT_SUFFIXES or p.name in {".env.example", "LICENSE", "README.md"}:
                try:
                    content_bytes = p.read_bytes()
                    self._check_content_safety(rel_path, p.name, content_bytes, report)
                except Exception as exc:
                    logger.debug("Could not read file %s: %s", rel_path, exc)

        return report

    def verify_zip(self, zip_path: Path) -> VerificationReport:
        report = VerificationReport(target=str(zip_path))

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for info in zf.infolist():
                    name = info.filename
                    report.scanned_count += 1

                    # 0. Path traversal check (zip bomb / escape)
                    if ".." in name or name.startswith("/") or name.startswith("\\"):
                        report.findings.append(ArtifactFinding(path=name, reason="Malicious path traversal entry in ZIP", severity="ERROR"))
                        continue

                    if info.is_dir():
                        parts = name.strip("/\\").split("/")
                        for part in parts:
                            if part in DENIED_DIR_NAMES:
                                report.findings.append(ArtifactFinding(path=name, reason=f"Disallowed directory '{part}' in package", severity="ERROR"))
                        continue

                    file_name = Path(name).name
                    suffix = Path(name).suffix.lower()

                    # 1. Check filename & path safety
                    self._check_filename_safety(name, file_name, suffix, report)

                    # 2. Check content safety
                    if suffix in TEXT_SUFFIXES or file_name in {".env.example", "LICENSE", "README.md"}:
                        try:
                            content_bytes = zf.read(name)
                            self._check_content_safety(name, file_name, content_bytes, report)
                        except Exception as exc:
                            logger.debug("Could not read zip entry %s: %s", name, exc)

        except Exception as exc:
            report.findings.append(ArtifactFinding(path=str(zip_path), reason=f"Failed to inspect ZIP file: {exc}", severity="ERROR"))

        return report

    def _check_filename_safety(self, full_path: str, name: str, suffix: str, report: VerificationReport) -> None:
        if name in DENIED_EXACT_NAMES:
            report.findings.append(ArtifactFinding(path=full_path, reason=f"Private credential file '{name}' must not be distributed", severity="ERROR"))
        if suffix in DENIED_SUFFIXES:
            report.findings.append(ArtifactFinding(path=full_path, reason=f"Binary/database artifact with extension '{suffix}' should not be in release", severity="ERROR"))
        
        # Check if inside private folder path
        norm_path = full_path.replace("\\", "/").lower()
        if "/logs/" in norm_path or norm_path.startswith("logs/"):
            report.findings.append(ArtifactFinding(path=full_path, reason="Runtime log files must not be distributed", severity="ERROR"))
        if "/data/meetings/" in norm_path or norm_path.startswith("data/meetings/"):
            report.findings.append(ArtifactFinding(path=full_path, reason="User meeting audio/transcripts must not be distributed", severity="ERROR"))

    def _check_content_safety(self, full_path: str, file_name: str, content: bytes, report: VerificationReport) -> None:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            return

        # Special handling for .env.example
        if file_name == ".env.example":
            for line in text.splitlines():
                line_str = line.strip()
                if not line_str or line_str.startswith("#"):
                    continue
                if "=" in line_str:
                    k, v = line_str.split("=", 1)
                    val_clean = v.strip().strip("'\"").lower()
                    if val_clean and val_clean not in SAFE_PLACEHOLDERS and not val_clean.startswith("your_"):
                        # Check if it looks like a real secret
                        for pattern in SECRET_PATTERNS:
                            if pattern.search(v):
                                report.findings.append(ArtifactFinding(path=full_path, reason=f"Live secret detected in .env.example line '{k}=...'", severity="ERROR"))
                                break
            return

        # General text checks
        for pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            if match:
                report.findings.append(ArtifactFinding(path=full_path, reason=f"Potential unmasked secret or API key: {match.group(0)[:8]}***", severity="ERROR"))
                break

        # Check local path leakage
        path_match = LOCAL_PATH_PATTERN.search(text)
        if path_match:
            report.findings.append(ArtifactFinding(path=full_path, reason=f"Personal user machine path detected: '{path_match.group(0)}'", severity="WARNING"))
