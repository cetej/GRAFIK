"""pytest bootstrap: this checkout's root goes first on sys.path, so `engine` is imported from here
and not from another checkout (worktrees share the interpreter)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# shared/ too: the editable install of ngm_shared points at the main checkout, so a worktree's tests
# imported its old textlayer and passed without testing the change (2026-11-03)
for p in (ROOT / "shared", ROOT):
    if str(p) in sys.path:
        sys.path.remove(str(p))
    sys.path.insert(0, str(p))

# The real termdb (BIOLIB/termdb.db) must not leak into tests; tests/test_termdb.py builds its own.
os.environ["GRAFIK_TERMDB"] = ""
# Nor the operator's shared library (KNIHOVNA): importing engine.app builds the module-level app, whose
# style library seeds an empty knihovna, before any fixture runs.
os.environ["NGM_KNIHOVNA"] = tempfile.mkdtemp(prefix="grafik-tests-knihovna-")


@pytest.fixture(autouse=True)
def _own_knihovna(tmp_path, monkeypatch):
    """Every test gets its own shared library (Settings.knihovna_dir reads NGM_KNIHOVNA)."""
    monkeypatch.setenv("NGM_KNIHOVNA", str(tmp_path / "knihovna"))
