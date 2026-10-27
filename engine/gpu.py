"""GPU guard: free VRAM via nvidia-smi and a cooperative machine-wide lock file.

The lock file (default ~/.gpu-lock) is a convention other projects (NG-ROBOT
dubbing, Whisper) can take too: JSON {owner, pid, since}. A lock whose pid is
dead is stale and gets replaced.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import psutil


class GpuBusy(RuntimeError):
    pass


def free_vram_mib() -> int | None:
    """Free memory of GPU 0, or None when nvidia-smi is unavailable."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return int(out.stdout.splitlines()[0].strip())


def read_lock(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _is_stale(lock: dict | None) -> bool:
    if not lock:
        return True
    pid = lock.get("pid")
    return not (isinstance(pid, int) and psutil.pid_exists(pid))


class GpuLock:
    def __init__(self, path: Path, owner: str = "grafik-engine"):
        self.path = path
        self.owner = owner

    def try_acquire(self) -> bool:
        payload = json.dumps({"owner": self.owner, "pid": os.getpid(), "since": time.time()})
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                lock = read_lock(self.path)
                if lock and lock.get("pid") == os.getpid() and lock.get("owner") == self.owner:
                    return True
                if not _is_stale(lock):
                    return False
                self.path.unlink(missing_ok=True)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            return True
        return False

    def acquire(self, wait_s: float, poll_s: float = 2.0) -> None:
        deadline = time.monotonic() + wait_s
        while not self.try_acquire():
            if time.monotonic() >= deadline:
                holder = read_lock(self.path) or {}
                raise GpuBusy(
                    f"GPU drží jiný program ({holder.get('owner', '?')}, PID {holder.get('pid', '?')}) "
                    f"déle než {int(wait_s)} s — lokální generátor je teď nedostupný."
                )
            time.sleep(poll_s)

    def release(self) -> None:
        lock = read_lock(self.path)
        if lock and lock.get("pid") == os.getpid() and lock.get("owner") == self.owner:
            self.path.unlink(missing_ok=True)
