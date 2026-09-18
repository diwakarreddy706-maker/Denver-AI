#!/usr/bin/env python3
"""Automated Repository Hygiene, Secret Scanning & Pre-Release Cleaner for Denver AI Assistant."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent

# Files/Directories that should never be in a clean git release
CLEANABLE_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
}

CLEANABLE_EXTENSIONS = {
    ".pyc",
    ".pyd",
}

FORBIDDEN_FILES = {
    ".env.local",
    "denver_vault.dat",
    "audit_vault.dat",
    "secrets.json",
}

SECRET_PATTERNS = [
    (re.compile(r"gsk_[A-Za-z0-9_-]{20,}"), "Groq API Key"),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "OpenAI API Key"),
    (re.compile(r"AIzaSy[A-Za-z0-9_-]{33}"), "Google AI / Firebase Key"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{25,}"), "Bearer Token"),
]


def clean_hygiene_artifacts(root_dir: Path = ROOT) -> int:
    """Purge temporary cache folders and compiled bytecode files."""
    cleaned_count = 0
    print(f"Cleaning repository artifacts in: {root_dir}")

    for root, dirs, files in os.walk(root_dir, topdown=False):
        rel_root = Path(root).relative_to(root_dir)
        parts = rel_root.parts

        # Skip reference archives
        if any(p in {"reference_file", "_reference_repo", ".git"} for p in parts):
            continue

        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in CLEANABLE_EXTENSIONS:
                try:
                    p.unlink()
                    cleaned_count += 1
                except Exception:
                    pass

        for d in dirs:
            if d in CLEANABLE_DIRS:
                p = Path(root) / d
                try:
                    shutil.rmtree(p, ignore_errors=True)
                    cleaned_count += 1
                except Exception:
                    pass

    print(f"Purged {cleaned_count} temporary cache & bytecode files.")
    return cleaned_count


def audit_repository(root_dir: Path = ROOT) -> int:
    """Scan the repository for forbidden files, caches, and active hardcoded secrets."""
    issues: list[str] = []
    scanned_count = 0

    print(f"=== Denver Repository Hygiene & Safety Audit ===")
    print(f"Scanning target: {root_dir}")

    for root, dirs, files in os.walk(root_dir):
        rel_root = Path(root).relative_to(root_dir)
        parts = rel_root.parts

        # Skip reference archives, dist packages, and git internals
        if any(p in {".git", "reference_file", "_reference_repo", "dist", "build"} for p in parts):
            continue

        for d in dirs:
            if d in CLEANABLE_DIRS and not any(p in {"src", "plugins"} for p in parts):
                issues.append(f"[CACHE DIRECTORY] Found '{d}' in {rel_root / d}")

        for file in files:
            file_path = Path(root) / file
            rel_file = file_path.relative_to(root_dir)

            # Local .env at root is ignored by git (.gitignore)
            if file == ".env" and str(rel_file) == ".env":
                continue

            if file in FORBIDDEN_FILES:
                issues.append(f"[FORBIDDEN FILE] Sensitive file found: {rel_file}")

            if file_path.suffix.lower() in CLEANABLE_EXTENSIONS:
                issues.append(f"[FORBIDDEN EXTENSION] Bytecode found: {rel_file}")

            # Secret scan in text files
            if file_path.suffix.lower() in {".py", ".json", ".md", ".toml", ".yaml", ".yml", ".txt", ".example"}:
                # Skip test suite files when they are testing secret masking and regex verifiers
                if "tests" in parts:
                    continue

                scanned_count += 1
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    for pattern, label in SECRET_PATTERNS:
                        matches = pattern.findall(content)
                        for m in matches:
                            if "your_" in m or "***" in m or "placeholder" in m or "example" in m or "fake_" in m or "mock_" in m or "test_" in m:
                                continue
                            issues.append(f"[HARDCODED SECRET] {label} detected in {rel_file}")
                except Exception:
                    pass

    print(f"Scanned files: {scanned_count}")
    if issues:
        print(f"Status: FAILED ({len(issues)} hygiene findings):")
        for iss in issues:
            print(f"  • {iss}")
        print("\nTip: Run 'python scripts/repo_hygiene.py --clean' to automatically remove cache and bytecode.")
        return 1

    print("Status: PASS (Repository is clean and meets zero-leak hygiene standards)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Denver Repository Hygiene & Pre-Release Scanner.")
    parser.add_argument("--clean", action="store_true", help="Automatically clean temporary caches and bytecode before audit.")
    args = parser.parse_args()

    if args.clean:
        clean_hygiene_artifacts(ROOT)

    return audit_repository(ROOT)


if __name__ == "__main__":
    sys.exit(main())
