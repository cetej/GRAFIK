"""This checkout's ngm_shared goes first on sys.path, not an editable install from another checkout."""

import sys
from pathlib import Path

SHARED = str(Path(__file__).resolve().parents[1])
if SHARED in sys.path:
    sys.path.remove(SHARED)
sys.path.insert(0, SHARED)
