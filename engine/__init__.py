"""GRAFIK Engine — local image service (v2)."""
import sys
from pathlib import Path

# ngm_shared (the heavy-work lock) from this checkout's shared/: every way the Engine is started
# (start-grafik.bat, a client's autostart, tests in a worktree) works without installing it first.
_shared = str(Path(__file__).resolve().parent.parent / "shared")
if _shared not in sys.path:
    sys.path.insert(0, _shared)
