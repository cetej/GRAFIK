"""This checkout's ngm_shared goes first on sys.path, not an editable install from another checkout."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

SHARED = str(Path(__file__).resolve().parents[1])
if SHARED in sys.path:
    sys.path.remove(SHARED)
sys.path.insert(0, SHARED)
os.environ["NGM_KNIHOVNA"] = tempfile.mkdtemp(prefix="ngm-shared-tests-knihovna-")


@pytest.fixture(autouse=True)
def _own_knihovna(tmp_path, monkeypatch):
    """No test may touch the operator's shared library (KNIHOVNA)."""
    monkeypatch.setenv("NGM_KNIHOVNA", str(tmp_path / "knihovna"))
