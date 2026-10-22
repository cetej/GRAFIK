"""Vendor keys via the operator's shared loader (STOPA scripts/load_keys.py):
reads sibling project .env files into os.environ, never overwrites, never prints."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

LOADER = Path("C:/Users/stock/Documents/000_NGM/STOPA/scripts/load_keys.py")
_loaded = False


def get_key(*names: str) -> str | None:
    global _loaded
    if not _loaded and LOADER.is_file():
        spec = importlib.util.spec_from_file_location("stopa_load_keys", LOADER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.load_project_keys()
        _loaded = True
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return None
