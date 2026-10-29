"""One lock for heavy work on the whole machine: FLUX on the GPU, Blender, VectorCraft, speech, headless Chrome.

The machine (RTX 4060 8 GB, 32 GB RAM, usually ~4 GB free) must never run two heavy jobs at once:
that ran out of RAM before. Every project takes this lock before a heavy job:

    from ngm_shared.heavy_lock import heavy
    with heavy("blender", owner="klapka", caller="scena-12"):
        subprocess.run([...])

The lock is the file ~/.gpu-lock (named when it guarded only the GPU; GRAFIK Engine takes it since
2026-10-23) holding JSON {owner, pid, since, kind, caller}; older readers use only owner, pid, since.
A lock whose process is gone, or whose pid now belongs to a process started after `since` (Windows
reuses pids), is abandoned and the next caller takes it over. holder() says who holds it, for a UI.

Changes go through a short OS lock on ~/.gpu-lock.mutex (released by Windows when the process dies) and
the file is replaced in one step, so two processes can never both take it. Windows only (msvcrt).
"""
from __future__ import annotations

import json
import msvcrt
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import psutil

KINDS = ("gpu", "blender", "vectorcraft", "speech", "chrome-render")
LOCK_PATH = Path.home() / ".gpu-lock"
# an empty or half-written lock (a writer outside this module) counts as taken for this long
WRITING_GRACE_S = 10.0


class HeavyBusy(RuntimeError):
    """Someone else held the lock longer than the caller would wait; .holder says who."""

    def __init__(self, message: str, holder: dict | None = None):
        super().__init__(message)
        self.holder = holder


def read_lock(path: Path = LOCK_PATH) -> dict | None:
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return lock if isinstance(lock, dict) else None


def _alive(lock: dict) -> bool:
    pid, since = lock.get("pid"), lock.get("since")
    if not isinstance(pid, int):
        return False
    try:
        started = psutil.Process(pid).create_time()
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True
    return not (isinstance(since, (int, float)) and started > since + 2)


def _taken(path: Path, lock: dict | None) -> bool:
    if lock is not None:
        return _alive(lock)
    try:
        return time.time() - path.stat().st_mtime < WRITING_GRACE_S
    except OSError:     # no lock file
        return False


def _retry(fn, *args):
    """Windows refuses to replace or delete a file someone has open for a moment (a reader, antivirus)."""
    for _ in range(50):
        try:
            return fn(*args)
        except PermissionError:
            time.sleep(0.02)
    return fn(*args)


@contextmanager
def _mutex(path: Path):
    with open(path.with_name(path.name + ".mutex"), "a+b") as f:
        deadline = time.monotonic() + 10
        while True:
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.005)
        try:
            yield
        finally:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


def holder(path: Path = LOCK_PATH) -> dict | None:
    """The live holder {owner, pid, since, kind, caller, held_s}, or None when the lock is free or abandoned.
    Reads without the mutex (a health check must not wait): writers replace the file whole."""
    lock = read_lock(path)
    if lock is None or not _alive(lock):
        return None
    since = lock.get("since")
    return {"kind": None, "caller": None, **lock,
            "held_s": round(time.time() - since, 1) if isinstance(since, (int, float)) else None}


def describe(lock: dict | None) -> str:
    """'blender pro klapka (scena-12), PID 4242, od 14:03:10' for messages and UIs."""
    if not lock:
        return "nikdo"
    who = lock.get("owner", "?") + (f" ({lock['caller']})" if lock.get("caller") else "")
    since = lock.get("since")
    at = f", od {datetime.fromtimestamp(since):%H:%M:%S}" if isinstance(since, (int, float)) else ""
    return f"{lock.get('kind') or 'gpu'} pro {who}, PID {lock.get('pid', '?')}{at}"


class HeavyLock:
    def __init__(self, path: Path = LOCK_PATH, owner: str = "ngm"):
        self.path = Path(path)
        self.owner = owner

    def _mine(self, lock: dict | None) -> bool:
        return bool(lock) and lock.get("pid") == os.getpid() and lock.get("owner") == self.owner

    def try_acquire(self, kind: str = "gpu", caller: str | None = None) -> bool:
        if kind not in KINDS:
            raise ValueError(f"neznámý druh těžké práce {kind!r}; povolené: {', '.join(KINDS)}")
        with _mutex(self.path):
            lock = read_lock(self.path)
            if self._mine(lock):
                return True
            if _taken(self.path, lock):
                return False
            tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps({"owner": self.owner, "pid": os.getpid(), "since": time.time(),
                                       "kind": kind, "caller": caller}), encoding="utf-8")
            _retry(os.replace, tmp, self.path)
            return True

    def acquire(self, wait_s: float, kind: str = "gpu", caller: str | None = None, poll_s: float = 2.0) -> None:
        """Waits up to wait_s for the lock; HeavyBusy names the holder when it does not come free."""
        deadline = time.monotonic() + wait_s
        while not self.try_acquire(kind, caller):
            if time.monotonic() >= deadline:
                held = read_lock(self.path)
                raise HeavyBusy(f"Stroj je obsazený těžkou prací ({describe(held)}) déle než {int(wait_s)} s, "
                                f"{kind} pro {self.owner} se teď nespustí.", held)
            time.sleep(poll_s)

    def release(self) -> None:
        with _mutex(self.path):
            if self._mine(read_lock(self.path)):
                _retry(self.path.unlink, True)


@contextmanager
def heavy(kind: str, *, owner: str, caller: str | None = None, wait_s: float = 600.0,
          path: Path = LOCK_PATH, poll_s: float = 2.0):
    """`with heavy("blender", owner="klapka"):` waits for the lock (HeavyBusy after wait_s) and frees it after."""
    lock = HeavyLock(path, owner)
    lock.acquire(wait_s, kind, caller, poll_s)
    try:
        yield lock
    finally:
        lock.release()
