"""Single FIFO job queue (SQLite) + one worker thread = one GPU user at a time.

A job that was running when the Engine stopped is marked failed on the next
start — it is never silently re-run (a paid job must not run twice).
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

from engine import prompt as promptlib
from engine.backends import BackendError, Generated, describe_style, estimate_usd
from engine.config import Settings
from engine.gpu import GpuBusy, GpuLock
from engine.models import ImageRequest
from engine.refs import RefError, load_ref_png, sha256
from engine.sdserver import SdServerError

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, seq INTEGER, status TEXT, caller TEXT, backend TEXT,
  request TEXT, result TEXT, error TEXT,
  created REAL, started REAL, finished REAL
)"""
FINAL = ("done", "failed", "cancelled")


def new_job_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)


class JobStore:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self.db.execute(SCHEMA)

    def recover_interrupted(self) -> int:
        with self._lock:
            cur = self.db.execute(
                "UPDATE jobs SET status='failed', error=?, finished=? WHERE status='running'",
                ("přerušeno restartem Engine", time.time()))
            return cur.rowcount

    def add(self, req: ImageRequest) -> str:
        job_id = new_job_id()
        with self._lock:
            seq = self.db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM jobs").fetchone()[0]
            self.db.execute(
                "INSERT INTO jobs (id, seq, status, caller, backend, request, created) VALUES (?,?,?,?,?,?,?)",
                (job_id, seq, "queued", req.caller, req.backend, req.model_dump_json(by_alias=True), time.time()))
        return job_id

    def next_queued(self) -> sqlite3.Row | None:
        with self._lock:
            row = self.db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY seq LIMIT 1").fetchone()
            if row:
                self.db.execute("UPDATE jobs SET status='running', started=? WHERE id=?", (time.time(), row["id"]))
            return row

    def finish(self, job_id: str, result: dict | None = None, error: str | None = None) -> None:
        with self._lock:
            self.db.execute(
                "UPDATE jobs SET status=?, result=?, error=?, finished=? WHERE id=?",
                ("failed" if error else "done", json.dumps(result, ensure_ascii=False) if result else None,
                 error, time.time(), job_id))

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            cur = self.db.execute(
                "UPDATE jobs SET status='cancelled', finished=? WHERE id=? AND status='queued'", (time.time(), job_id))
            return cur.rowcount == 1

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            row = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                return None
            pos = None
            if row["status"] == "queued":
                pos = self.db.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running') AND seq < ?",
                    (row["seq"],)).fetchone()[0]
        return self._public(row, pos)

    def list(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self.db.execute("SELECT * FROM jobs ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        return [self._public(r, None) for r in rows]

    def queue_len(self) -> int:
        with self._lock:
            return self.db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]

    @staticmethod
    def _public(row: sqlite3.Row, position: int | None) -> dict:
        result = json.loads(row["result"]) if row["result"] else None
        return {
            "job_id": row["id"], "status": row["status"], "caller": row["caller"], "backend": row["backend"],
            "position": position, "error": row["error"],
            "images": [f"/api/v2/jobs/{row['id']}/images/{i}" for i in range(len((result or {}).get("files", [])))],
            "result": result, "created": row["created"], "started": row["started"], "finished": row["finished"],
        }


class Worker:
    """Pulls jobs in FIFO order and runs them one by one."""

    def __init__(self, settings: Settings, store: JobStore, backends: dict, poll_s: float = 0.5):
        self.s = settings
        self.store = store
        self.backends = backends
        self.poll_s = poll_s
        self.gpu_lock = GpuLock(settings.gpu_lock_path)
        self._stop = threading.Event()
        self.running: str | None = None
        self._thread = threading.Thread(target=self._loop, name="grafik-worker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            row = self.store.next_queued()
            if row is None:
                self._stop.wait(self.poll_s)
                continue
            self.running = row["id"]
            try:
                result = self.process(row["id"], ImageRequest.model_validate_json(row["request"]), row["created"])
                self.store.finish(row["id"], result=result)
            except (BackendError, SdServerError, GpuBusy, RefError) as e:
                self.store.finish(row["id"], error=str(e))
            except Exception as e:  # keep the worker alive; surface the reason to the caller
                self.store.finish(row["id"], error=f"{type(e).__name__}: {e}")
            finally:
                self.running = None

    def process(self, job_id: str, req: ImageRequest, created: float) -> dict:
        backend = self.backends[req.backend]
        t_start = time.time()
        job_dir = self.s.library_dir / datetime.now().strftime("%Y-%m") / job_id
        (job_dir / "refs").mkdir(parents=True, exist_ok=True)

        refs_meta, image_refs, described = [], [], {}
        for i, ref in enumerate(req.refs):
            png = None
            if ref.b64 or ref.path or ref.url:
                png = load_ref_png(ref)
                (job_dir / "refs" / f"ref-{i}.png").write_bytes(png)
            if ref.role == "style" and not ref.text:
                described[i] = describe_style(png)
            if ref.role in ("subject", "geometry", "scene"):
                image_refs.append(png)
            refs_meta.append({
                "index": i, "role": ref.role, "sha256": sha256(png) if png else None,
                "source": ref.source or ref.url or ref.path or ("b64" if ref.b64 else None),
                "license": ref.license, "text": ref.text or described.get(i),
                "sent_as": "image" if ref.role in ("subject", "geometry", "scene") else "words",
            })

        prompt = promptlib.build_prompt(req, described)
        use_gpu = req.backend == "flux-local"
        if use_gpu:
            self.gpu_lock.acquire(self.s.gpu_lock_wait_s)
        try:
            gen: Generated = backend.run(req, prompt, image_refs)
        finally:
            if use_gpu:
                self.gpu_lock.release()
        t_done = time.time()

        est = estimate_usd(req, backend)
        files = []
        for n, data in enumerate(gen.images):
            name = f"image-{n}.png"
            (job_dir / name).write_bytes(data)
            prov = {
                "job_id": job_id, "file": name, "backend": backend.name, "model": gen.model,
                "seed": gen.seeds[n], "params": gen.params,
                "prompt_original": req.prompt, "prompt_sent": prompt,
                "refs": refs_meta, "layout": [i.model_dump(by_alias=True, exclude_none=True) for i in req.layout],
                "style": req.style, "caller": req.caller,
                "ai_generated": True, "reviewed_by": None,
                "cost_usd": round(backend.usd_for(req) / req.n, 4),
                "timing_s": {"queue": round(t_start - created, 1), "generate": round(t_done - t_start, 1)},
                "created": datetime.now().isoformat(timespec="seconds"),
            }
            (job_dir / f"image-{n}.json").write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
            files.append(str(job_dir / name))

        self.s.library_dir.mkdir(parents=True, exist_ok=True)
        with open(self.s.costs_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "job_id": job_id,
                                "caller": req.caller, "backend": backend.name, "n": len(gen.images),
                                "usd": est["total_usd"], "items": est["items"]}, ensure_ascii=False) + "\n")
        return {"files": files, "dir": str(job_dir), "prompt_sent": prompt, "seeds": gen.seeds,
                "cost_usd": est["total_usd"], "timing_s": {"queue": round(t_start - created, 1),
                                                          "generate": round(t_done - t_start, 1)}}
