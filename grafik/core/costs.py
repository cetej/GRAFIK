"""Cost ledger — per-project JSONL of paid API calls + in-process session totals.

Single write point for every paid call (M4 rule: "zapisuj v jednom místě"):
call sites route through grafik.fal.client.tracked_subscribe (fal endpoints)
or call record_paid_call directly (async video submit, NB Pro image gen).
Attribution to a project works two ways, explicit argument winning:

- explicitly, via `record_paid_call(..., project_dir=...)` or `with
  cost_context(project_dir):` around a paid call (FalClient.decompose does
  this for library use), or
- implicitly, via the request-scoped context set by the API layer's
  `_load_project` — FastAPI runs each sync route in its own copied context
  (anyio.to_thread), so the ContextVar never leaks between requests.

USD amounts are ESTIMATES derived from registry rate fields
(est_cost_usd_per_mp / _per_second / _per_call — secondary-sourced, see each
entry's price_note). When no rate is known the entry records est_usd=None,
never a guess presented as fact (same rule as grafik.motion.jobs._cost_note).
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

LEDGER_FILENAME = "costs.jsonl"

_active_project_dir: ContextVar[str | None] = ContextVar("grafik_cost_project_dir", default=None)

_session_lock = threading.Lock()
_session_entries: list[dict] = []


def set_active_project_dir(project_dir: Path | None) -> None:
    """Bind subsequent paid calls in the current context to a project dir."""
    _active_project_dir.set(str(project_dir) if project_dir else None)


def active_project_dir() -> Path | None:
    value = _active_project_dir.get()
    return Path(value) if value else None


@contextmanager
def cost_context(project_dir: Path | None) -> Iterator[None]:
    """Scoped variant of set_active_project_dir (restores the previous value)."""
    token = _active_project_dir.set(str(project_dir) if project_dir else None)
    try:
        yield
    finally:
        _active_project_dir.reset(token)


def estimate_usd(
    endpoint: str,
    *,
    mp: float | None = None,
    seconds: float | None = None,
    calls: int = 1,
) -> float | None:
    """Estimate one call's USD cost from the registry rates for `endpoint`.

    Preference order matches how fal actually bills each endpoint kind:
    per-MP when the caller measured megapixels, per-second for video, flat
    per-call otherwise. Returns None when no applicable rate is registered.
    """
    from grafik.providers.registry import REGISTRY  # lazy: avoids import cycle via providers

    info = next((e.info for e in REGISTRY.values() if e.info.endpoint == endpoint), None)
    if info is None:
        return None
    if info.est_cost_usd_per_mp is not None and mp is not None:
        return info.est_cost_usd_per_mp * mp
    if info.est_cost_usd_per_second is not None and seconds is not None:
        return info.est_cost_usd_per_second * seconds
    if info.est_cost_usd_per_call is not None:
        return info.est_cost_usd_per_call * calls
    return None


def record_paid_call(
    endpoint: str,
    kind: str,
    *,
    mp: float | None = None,
    seconds: float | None = None,
    calls: int = 1,
    note: str = "",
    project_dir: Path | None = None,
) -> dict:
    """Record one paid call: append to the project ledger (when a project is
    known) and always to the in-process session list. Returns the entry."""
    est = estimate_usd(endpoint, mp=mp, seconds=seconds, calls=calls)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "kind": kind,
        "mp": round(mp, 4) if mp is not None else None,
        "seconds": seconds,
        "calls": calls,
        "est_usd": round(est, 4) if est is not None else None,
        "note": note,
    }
    target = project_dir or active_project_dir()
    if target is not None:
        append_entry(target, entry)
    with _session_lock:
        _session_entries.append(entry)
    return entry


def append_entry(project_dir: Path, entry: dict) -> None:
    """Append one already-built entry to a project's costs.jsonl (used by
    record_paid_call and by the API when adopting a pre-project generation)."""
    path = Path(project_dir) / LEDGER_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with _session_lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_ledger(project_dir: Path) -> list[dict]:
    """All entries from a project's costs.jsonl; corrupt lines are skipped."""
    path = Path(project_dir) / LEDGER_FILENAME
    if not path.exists():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def total_usd(entries: list[dict]) -> float:
    return round(sum(e["est_usd"] for e in entries if e.get("est_usd") is not None), 4)


def session_entries() -> list[dict]:
    with _session_lock:
        return list(_session_entries)


def reset_session() -> None:
    """Test helper: forget the in-process session accumulator."""
    with _session_lock:
        _session_entries.clear()
