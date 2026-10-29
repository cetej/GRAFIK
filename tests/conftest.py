"""pytest bootstrap: this checkout's root goes first on sys.path, so `engine` is imported from here
and not from another checkout (worktrees share the interpreter)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

# The real termdb (BIOLIB/termdb.db) must not leak into tests; tests/test_termdb.py builds its own.
os.environ["GRAFIK_TERMDB"] = ""
# Nor the operator's shared library (KNIHOVNA): importing engine.app builds the module-level app, whose
# style library seeds an empty knihovna, before any fixture runs.
os.environ["NGM_KNIHOVNA"] = tempfile.mkdtemp(prefix="grafik-tests-knihovna-")


@pytest.fixture(autouse=True)
def _own_knihovna(tmp_path, monkeypatch):
    """Every test gets its own shared library (Settings.knihovna_dir reads NGM_KNIHOVNA)."""
    monkeypatch.setenv("NGM_KNIHOVNA", str(tmp_path / "knihovna"))
