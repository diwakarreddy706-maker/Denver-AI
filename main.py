"""Denver AI Assistant — Root Entrypoint."""

import sys
from pathlib import Path

# Ensure src/ is in sys.path
root_dir = Path(__file__).resolve().parent
src_dir = root_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from denver.app.bootstrap import main

if __name__ == "__main__":
    sys.exit(main())
