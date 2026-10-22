"""GRAFIK Engine — FastAPI app, /api/v2 (spec docs/plans/2026-10-22-grafik-v2-greenfield.md § 5).

Run: python -m uvicorn engine.app:app --port 8300
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from engine.backends import BackendError, estimate_usd, make_backends
from engine.config import Settings
from engine.gpu import free_vram_mib
from engine.jobs import JobStore, Worker
from engine.models import ImageRequest
from engine.sdserver import SdServer


def create_app(settings: Settings | None = None, backends: dict | None = None,
               server: SdServer | None = None, start_worker: bool = True) -> FastAPI:
    s = settings or Settings()
    sd = server or SdServer(s)
    store = JobStore(s.db_path)
    bk = backends or make_backends(s, sd)
    worker = Worker(s, store, bk)

    @asynccontextmanager
    async def lifespan(_app):
        store.recover_interrupted()
        if start_worker:
            worker.start()
            sd.start_idle_watcher()
        yield
        if start_worker:
            worker.stop()
            sd.stop_idle_watcher()

    app = FastAPI(title="GRAFIK Engine", version="2.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])
    app.state.settings, app.state.store, app.state.worker, app.state.sd = s, store, worker, sd

    @app.get("/api/v2/health")
    def health():
        return {"engine": "ok", "sd_server": sd.status(), "queue_len": store.queue_len(),
                "running_job": worker.running, "gpu_free_mib": free_vram_mib(),
                "backends": sorted(bk), "default_backend": "flux-local"}

    @app.post("/api/v2/images", status_code=202)
    def submit(req: ImageRequest):
        backend = bk.get(req.backend)
        if backend is None:
            raise HTTPException(400, f"neznámý backend {req.backend!r}; k dispozici: {sorted(bk)}")
        try:
            backend.validate(req)
        except BackendError as e:
            raise HTTPException(400, str(e)) from e
        est = estimate_usd(req, backend)
        if est["total_usd"] > 0 and not req.confirm_cost:
            return JSONResponse(status_code=402, content={
                "detail": "Placená operace — nic nespuštěno. Pošlete znovu s confirm_cost=true.",
                "backend": req.backend, "estimate_usd": est["total_usd"], "items": est["items"]})
        job_id = store.add(req)
        job = store.get(job_id)
        return {"job_id": job_id, "status": job["status"], "position": job["position"],
                "estimate_usd": est["total_usd"]}

    @app.get("/api/v2/jobs")
    def jobs(limit: int = 50):
        return store.list(limit)

    @app.get("/api/v2/jobs/{job_id}")
    def job(job_id: str):
        j = store.get(job_id)
        if not j:
            raise HTTPException(404, "úloha neexistuje")
        return j

    @app.post("/api/v2/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        if not store.cancel(job_id):
            raise HTTPException(409, "zrušit jde jen úlohu, která ještě čeká ve frontě")
        return store.get(job_id)

    @app.get("/api/v2/jobs/{job_id}/images/{n}")
    def image(job_id: str, n: int):
        j = store.get(job_id)
        files = ((j or {}).get("result") or {}).get("files", [])
        if not j or not 0 <= n < len(files):
            raise HTTPException(404, "obrázek neexistuje")
        return FileResponse(files[n], media_type="image/png")

    @app.get("/api/v2/jobs/{job_id}/images/{n}/provenance")
    def provenance(job_id: str, n: int):
        j = store.get(job_id)
        files = ((j or {}).get("result") or {}).get("files", [])
        if not j or not 0 <= n < len(files):
            raise HTTPException(404, "obrázek neexistuje")
        return json.loads(Path(files[n]).with_suffix(".json").read_text(encoding="utf-8"))

    @app.get("/api/v2/costs")
    def costs(limit: int = 100):
        if not s.costs_path.exists():
            return {"total_usd": 0.0, "entries": []}
        entries = [json.loads(line) for line in s.costs_path.read_text(encoding="utf-8").splitlines() if line]
        return {"total_usd": round(sum(e["usd"] for e in entries), 4), "entries": entries[-limit:]}

    return app


app = create_app()
