"""Limit klienta se počítá od spuštění úlohy: fronta Engine je sdílená a čekání v ní není selhání (1. 11. spadl klient po 900 s, úloha doběhla)."""
from __future__ import annotations

import pytest

from ngm_shared import grafik_client as gc


@pytest.fixture
def clock(monkeypatch):
    now = {"t": 0.0}
    monkeypatch.setattr(gc.time, "monotonic", lambda: now["t"])
    monkeypatch.setattr(gc.time, "sleep", lambda s: now.__setitem__("t", now["t"] + s))
    return now


def _jobs(monkeypatch, clock, script):
    """script: [(do kolika sekund, stav), ...]"""
    def request(method, path, body=None, timeout=30):
        for until, status in script:
            if clock["t"] < until:
                return 200, {"status": status, "error": None}
        return 200, {"status": script[-1][1], "error": None}
    monkeypatch.setattr(gc, "_request", request)


def test_time_in_queue_does_not_count(monkeypatch, clock):
    _jobs(monkeypatch, clock, [(1500, "queued"), (1600, "running"), (1e9, "done")])
    assert gc.wait("j", timeout=900, poll_s=10)["status"] == "done"


def test_running_too_long_fails_and_says_it_goes_on(monkeypatch, clock):
    _jobs(monkeypatch, clock, [(100, "queued"), (1e9, "running")])
    with pytest.raises(gc.GrafikError, match="běží dál"):
        gc.wait("j", timeout=300, poll_s=10)
    assert 390 <= clock["t"] <= 420


def test_stuck_queue_still_ends(monkeypatch, clock):
    _jobs(monkeypatch, clock, [(1e9, "queued")])
    with pytest.raises(gc.GrafikError, match="ve frontě"):
        gc.wait("j", timeout=300, poll_s=60, queue_timeout=1000)
