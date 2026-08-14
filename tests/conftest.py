"""pytest bootstrap: force this worktree's `grafik` package onto sys.path[0].

`grafik` is also pip-installed in editable mode from the MAIN repo checkout
(C:\\Users\\stock\\Documents\\000_NGM\\GRAFIK), so an unqualified `import grafik`
can silently resolve to that copy instead of this worktree's copy. Insert
the worktree root first (ahead of site-packages) and assert the resolved
module actually lives under this worktree, so a green test run can't be
quietly testing the wrong code.
"""

from __future__ import annotations

import sys
from pathlib import Path

WORKTREE_ROOT = Path(__file__).resolve().parents[1]

# Make sure the worktree root wins over any other sys.path entry (e.g. the
# main repo's editable install in site-packages).
_root_str = str(WORKTREE_ROOT)
if _root_str in sys.path:
    sys.path.remove(_root_str)
sys.path.insert(0, _root_str)

import grafik  # noqa: E402  (must import after the sys.path fix above)

_resolved = Path(grafik.__file__).resolve()
assert _resolved.is_relative_to(WORKTREE_ROOT), (
    f"grafik resolved to {_resolved}, expected it under worktree root {WORKTREE_ROOT} "
    "(check for a stale editable install shadowing this worktree)"
)
