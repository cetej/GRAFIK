"""Lifecycle of the local sd-server (stable-diffusion.cpp) process.

Rules (operator, ~/.claude/rules/procesy.md): we only ever stop the process we
started ourselves, identified by PID + create_time + exe stored in
run/sd-server.json. Never by image name, never a tree kill.
API facts: docs/capabilities/sd-server-master-987.md.
"""
from __future__ import annotations

import base64
import json
import subprocess
import threading
import time

import httpx
import psutil

from engine.config import Settings
from engine.gpu import free_vram_mib


class SdServerError(RuntimeError):
    pass


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class SdServer:
    def __init__(self, settings: Settings):
        self.s = settings
        self.base = f"http://127.0.0.1:{settings.sd_port}"
        self.state_path = settings.run_dir / "sd-server.json"
        self.log_path = settings.log_dir / "sd-server.log"
        self._lock = threading.RLock()
        self._busy = 0
        self.last_used = time.monotonic()
        self._watcher: threading.Thread | None = None
        self._stop_watch = threading.Event()

    # -- process identity -------------------------------------------------
    def command(self) -> list[str]:
        s = self.s
        return [
            str(s.flux_dir / s.sd_exe),
            "--diffusion-model", s.sd_model, "--llm", s.sd_llm, "--vae", s.sd_vae,
            "--listen-port", str(s.sd_port),
            "--steps", str(s.steps), "--cfg-scale", str(s.cfg_scale), "--sampling-method", s.sampler,
        ]

    def _read_state(self) -> dict | None:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def owned_process(self) -> psutil.Process | None:
        """The sd-server we started, or None. A PID that was reused by another
        program fails the create_time/exe check and is never touched."""
        st = self._read_state()
        if not st:
            return None
        try:
            p = psutil.Process(st["pid"])
            if abs(p.create_time() - st["create_time"]) > 1.0 or p.exe() != st["exe"]:
                return None
            if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
                return None
            return p
        except (psutil.Error, KeyError):
            return None

    def status(self) -> str:
        p = self.owned_process()
        if p is None:
            return "stopped"
        return "ready" if self._healthy() else "starting"

    def _healthy(self) -> bool:
        try:
            r = httpx.get(f"{self.base}/v1/models", timeout=3)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    # -- start / stop -----------------------------------------------------
    def ensure_running(self) -> None:
        with self._lock:
            if self.owned_process() is not None:
                if self._wait_healthy(self.s.start_timeout_s, self.owned_process()):
                    return
                self.stop("neodpovídal na health check")
            if self._healthy():
                raise SdServerError(
                    f"Port {self.s.sd_port} už obsluhuje jiný sd-server, který Engine nespustil. "
                    "Ukončete ho ručně, Engine cizí procesy nevypíná."
                )
            free = free_vram_mib()
            if free is not None and free < self.s.min_free_vram_mib:
                raise SdServerError(
                    f"Na GPU je volných jen {free} MiB (potřeba {self.s.min_free_vram_mib}). "
                    "GPU nejspíš používá jiný program (dabing, Whisper) — lokální generátor je teď nedostupný."
                )
            self._start()

    def _start(self) -> None:
        self.s.run_dir.mkdir(parents=True, exist_ok=True)
        self.s.log_dir.mkdir(parents=True, exist_ok=True)
        # sd-server panics when its stdout pipe closes -> always a file, never a pipe.
        log = open(self.log_path, "ab")
        try:
            proc = subprocess.Popen(
                self.command(), cwd=self.s.flux_dir, stdout=log, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW,
            )
        finally:
            log.close()
        p = psutil.Process(proc.pid)
        self.state_path.write_text(json.dumps({
            "pid": proc.pid, "create_time": p.create_time(), "exe": p.exe(),
            "port": self.s.sd_port, "started": time.time(),
        }), encoding="utf-8")
        self.last_used = time.monotonic()
        if not self._wait_healthy(self.s.start_timeout_s, p):
            tail = self._log_tail()
            self.stop("nenaběhl")
            raise SdServerError(f"sd-server nenaběhl do {int(self.s.start_timeout_s)} s. Konec logu:\n{tail}")

    def _wait_healthy(self, timeout: float, proc: psutil.Process | None) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if proc is None or not proc.is_running():
                return False
            if self._healthy():
                return True
            time.sleep(0.5)
        return False

    def _log_tail(self, n: int = 8) -> str:
        try:
            lines = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(lines[-n:])
        except OSError:
            return "(log nedostupný)"

    def stop(self, reason: str = "") -> bool:
        """Terminate only our own process. Returns True when something was stopped."""
        with self._lock:
            p = self.owned_process()
            self.state_path.unlink(missing_ok=True)
            if p is None:
                return False
            p.terminate()
            try:
                p.wait(timeout=15)
            except psutil.TimeoutExpired:
                p.kill()
                p.wait(timeout=10)
            with open(self.s.log_dir / "engine-events.log", "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} stop sd-server pid={p.pid} reason={reason}\n")
            return True

    # -- idle watcher -----------------------------------------------------
    def start_idle_watcher(self, interval_s: float = 5.0) -> None:
        def loop():
            while not self._stop_watch.wait(interval_s):
                self.stop_if_idle()
        self._watcher = threading.Thread(target=loop, name="sd-idle", daemon=True)
        self._watcher.start()

    def stop_idle_watcher(self) -> None:
        self._stop_watch.set()

    def stop_if_idle(self) -> bool:
        with self._lock:
            if self._busy or time.monotonic() - self.last_used < self.s.idle_timeout_s:
                return False
            return self.stop(f"nečinnost {int(self.s.idle_timeout_s)} s")

    # -- generation -------------------------------------------------------
    def generate(self, payload: dict) -> list[bytes]:
        with self._lock:
            self._busy += 1
        try:
            self.ensure_running()
            r = httpx.post(f"{self.base}/sdcpp/v1/img_gen", json=payload, timeout=60)
            if r.status_code >= 300:
                raise SdServerError(f"sd-server odmítl úlohu ({r.status_code}): {r.text[:300]}")
            job = r.json()
            poll = job.get("poll_url") or f"/sdcpp/v1/jobs/{job['id']}"
            deadline = time.monotonic() + self.s.job_timeout_s
            while True:
                st = httpx.get(f"{self.base}{poll}", timeout=30).json()
                if st.get("status") == "completed":
                    break
                if st.get("status") in ("failed", "cancelled"):
                    raise SdServerError(f"sd-server úloha selhala: {st.get('error')}")
                if time.monotonic() > deadline:
                    raise SdServerError(f"sd-server úloha nedoběhla do {int(self.s.job_timeout_s)} s")
                time.sleep(1.0)
            images = (st.get("result") or {}).get("images") or []
            if not images:
                raise SdServerError("sd-server vrátil prázdný výsledek")
            return [base64.b64decode(im["b64_json"]) for im in images]
        except httpx.HTTPError as e:
            raise SdServerError(f"spojení se sd-serverem selhalo: {e}") from e
        finally:
            with self._lock:
                self._busy -= 1
                self.last_used = time.monotonic()

