"""Denver AI Assistant module CLI execution wrapper."""

from __future__ import annotations

import sys
from denver.app.bootstrap import main

if __name__ == "__main__":
    sys.exit(main())
