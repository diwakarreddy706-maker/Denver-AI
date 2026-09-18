#!/usr/bin/env python3
"""Convenience root shortcut for Windows portable release builder."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True

# Add root to sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from scripts.build_windows_portable import main

if __name__ == "__main__":
    sys.exit(main())
