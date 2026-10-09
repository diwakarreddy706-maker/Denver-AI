"""Denver HUD Wake Overlay — Root Convenience Script.

Allows running:
    python wake_overlay.py --demo
directly from the workspace root.
"""

from __future__ import annotations

import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent
src_dir = root_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from denver.ui.widgets.wake_overlay import _demo, get_wake_overlay

if __name__ == "__main__":
    if "--demo" in sys.argv or len(sys.argv) == 1:
        sys.exit(_demo())
    print("Run with: python wake_overlay.py --demo")
