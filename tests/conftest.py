"""pytest bootstrap: this checkout's root goes first on sys.path, so `engine` is imported from here
and not from another checkout (worktrees share the interpreter)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

# The real termdb (BIOLIB/termdb.db) must not leak into tests; tests/test_termdb.py builds its own.
os.environ["GRAFIK_TERMDB"] = ""
