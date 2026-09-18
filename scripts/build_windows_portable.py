#!/usr/bin/env python3
"""Standalone script to build and verify Denver AI Assistant Windows Portable Release."""

import argparse
import sys
from pathlib import Path

# Add src/ to sys.path
root_dir = Path(__file__).resolve().parent.parent
src_dir = root_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from denver import assistant_name, product_name
from denver.release.builder import PortableReleaseBuilder


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Build portable distribution package for {product_name}."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(root_dir / "dist"),
        help="Destination directory for distribution ZIP and staged files (default: dist/).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate file discovery and staging without writing files.",
    )
    parser.add_argument(
        "--skip-verifier",
        action="store_true",
        help="Skip automated security verification check on the resulting build.",
    )
    args = parser.parse_args()

    builder = PortableReleaseBuilder(project_root=root_dir)
    print(f"[{assistant_name}] Staging portable release build...")
    result = builder.build(
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        run_verifier=not args.skip_verifier,
    )

    print(result.format_summary())
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
