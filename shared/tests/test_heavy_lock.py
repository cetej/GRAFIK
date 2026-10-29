"""Heavy-work lock (ngm_shared.heavy_lock): processes racing for it, abandoned locks, time limit."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

from ngm_shared.heavy_lock import HeavyBusy, HeavyLock, heavy, holder, read_lock

WORKER = Path(__file__).with_name("lock_worker.py")


def spawn(*args) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(WORKER), *map(str, args)], stdout=subprocess.PIPE, text=True)


def test_processes_starting_at_once_exactly_one_wins(tmp_path):
    path = tmp_path / "gpu.lock"
    start = time.time() + 3
    procs = [spawn("once", path, start) for _ in range(6)]
    out = [p.communicate(timeout=30)[0].strip() for p in procs]
    assert "late" not in out, out
    assert sorted(out) == ["0"] * 5 + ["1"], out
    assert not path.exists()


def test_many_rounds_never_two_holders(tmp_path):
    path, marker = tmp_path / "gpu.lock", tmp_path / "inside"
    procs = [spawn("stress", path, marker, 20) for _ in range(6)]
    out = [p.communicate(timeout=120)[0].strip() for p in procs]
    assert out == ["0"] * 6, f"překryvy na proces: {out}"
    assert not path.exists() and not marker.exists()


def test_live_holder_blocks_with_clear_error_then_killed_holder_is_abandoned(tmp_path):
    path = tmp_path / "gpu.lock"
    child = spawn("hold", path)
    try:
        assert child.stdout.readline().strip() == "held"
        h = holder(path)
        assert (h["kind"], h["owner"], h["caller"], h["pid"]) == ("blender", "klapka", "scena-12", child.pid)
        assert h["held_s"] >= 0
        lock = HeavyLock(path, "grafik-engine")
        t0 = time.monotonic()
        with pytest.raises(HeavyBusy) as exc:
            lock.acquire(0.5, "gpu", poll_s=0.1)
        assert 0.5 <= time.monotonic() - t0 < 5
        msg = str(exc.value)
        assert all(s in msg for s in ("blender", "klapka", "scena-12", str(child.pid), "0 s")), msg
        assert exc.value.holder["pid"] == child.pid
    finally:
        child.kill()
        child.wait()
    assert holder(path) is None, "zabitý proces zámek nedrží"
    lock.acquire(1, "gpu", caller="ng-robot", poll_s=0.1)
    assert read_lock(path)["owner"] == "grafik-engine" and read_lock(path)["kind"] == "gpu"
    lock.release()
    assert not path.exists()


def test_dead_pid_and_reused_pid_are_abandoned(tmp_path):
    path = tmp_path / "gpu.lock"
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    path.write_text(json.dumps({"owner": "dead", "pid": gone.pid, "since": time.time()}))
    assert HeavyLock(path, "a").try_acquire()
    HeavyLock(path, "a").release()
    # a live pid that started after the lock was taken is someone else: Windows reuses pids
    started = psutil.Process().create_time()
    path.write_text(json.dumps({"owner": "old-engine", "pid": os.getpid(), "since": started - 60}))
    assert holder(path) is None
    assert HeavyLock(path, "a").try_acquire()


def test_old_format_from_live_process_blocks(tmp_path):
    path = tmp_path / "gpu.lock"
    parent = psutil.Process().parent()
    path.write_text(json.dumps({"owner": "ng-robot-dabing", "pid": parent.pid, "since": time.time()}))
    assert not HeavyLock(path, "a").try_acquire()
    assert holder(path)["owner"] == "ng-robot-dabing" and holder(path)["kind"] is None
    with pytest.raises(HeavyBusy, match="ng-robot-dabing"):
        HeavyLock(path, "a").acquire(0.3, poll_s=0.1)


def test_half_written_lock_is_taken_until_grace_runs_out(tmp_path):
    path = tmp_path / "gpu.lock"
    path.write_text("")
    assert not HeavyLock(path, "a").try_acquire()
    old = time.time() - 60
    os.utime(path, (old, old))
    assert HeavyLock(path, "a").try_acquire()
    assert read_lock(path)["owner"] == "a"


def test_reentrant_for_own_owner_and_release_only_own(tmp_path):
    path = tmp_path / "gpu.lock"
    a, b = HeavyLock(path, "a"), HeavyLock(path, "b")
    assert a.try_acquire("gpu") and a.try_acquire("gpu")
    assert not b.try_acquire("gpu")
    b.release()
    assert read_lock(path)["owner"] == "a"
    a.release()
    assert not path.exists() and b.try_acquire("speech")


def test_unknown_kind_is_refused(tmp_path):
    with pytest.raises(ValueError, match="vectorcraft"):
        HeavyLock(tmp_path / "gpu.lock").try_acquire("whisper")


def test_heavy_context_releases_on_error(tmp_path):
    path = tmp_path / "gpu.lock"
    with pytest.raises(RuntimeError, match="render"):
        with heavy("chrome-render", owner="kartograf", caller="mapa", path=path):
            assert read_lock(path)["kind"] == "chrome-render"
            raise RuntimeError("render spadl")
    assert not path.exists()
