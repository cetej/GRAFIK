"""GRAFIK Engine — FastAPI app, /api/v2 (spec docs/plans/2026-10-22-grafik-v2-greenfield.md § 5).

Run: python -m uvicorn engine.app:app --port 8300
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image
from pydantic import BaseModel

from engine.backends import EXPAND_USD, BackendError, estimate_usd, expand_prompt, make_backends
from engine.config import Settings
from engine.gpu import free_vram_mib
from engine.jobs import JobStore, Worker
from engine.models import ImageRequest, Ref
from engine.sdserver import SdServer


# Body models live at module level: with `from __future__ import annotations` FastAPI
# resolves annotations from module globals, so a class local to create_app would be
# misread as a query parameter.
class Review(BaseModel):
    reviewed_by: str


class Expand(BaseModel):
    text: str
    confirm_cost: bool = False
    caller: str = "studio"


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
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
                       allow_methods=["*"], allow_headers=["*"])
    app.state.settings, app.state.store, app.state.worker, app.state.sd = s, store, worker, sd

    @app.get("/api/v2/health")
    def health():
        return {"engine": "ok", "sd_server": sd.status(), "queue_len": store.queue_len(),
                "running_job": worker.running, "gpu_free_mib": free_vram_mib(),
                "backends": sorted(bk), "default_backend": "flux-local"}

    def prepare(req: ImageRequest):
        """Resolve backend and the edit parent; raise HTTPException on a bad request."""
        backend = bk.get(req.backend)
        if backend is None:
            raise HTTPException(400, f"neznámý backend {req.backend!r}; k dispozici: {sorted(bk)}")
        if req.edit:
            parent = store.image_path(req.parent)
            if parent is None:
                raise HTTPException(404, f"upravovaný obrázek {req.parent} neexistuje")
            w, h = Image.open(parent).size
            req = req.model_copy(update={
                "size": f"{w // 16 * 16}x{h // 16 * 16}",
                "refs": [Ref(path=str(parent), role="scene", source=f"verze {req.parent}")] + req.refs})
        try:
            backend.validate(req)
        except BackendError as e:
            raise HTTPException(400, str(e)) from e
        return req, backend

    @app.get("/api/v2/backends")
    def backends():
        out = []
        for name, b in bk.items():
            probe = ImageRequest(prompt="x")
            out.append({"id": name, "paid": bool(b.usd_for(probe)), "usd_1024": round(b.usd_for(probe), 4),
                        "refs": name in ("flux-local", "nb-pro") or bool(getattr(b, "spec", {}).get("edit")),
                        "supersample": name == "flux-local"})
        return sorted(out, key=lambda x: (x["paid"], x["id"]))

    @app.post("/api/v2/estimate")
    def estimate(req: ImageRequest):
        req, backend = prepare(req)
        est = estimate_usd(req, backend)
        eta = backend.eta_s(req) if hasattr(backend, "eta_s") else None
        render = backend.render_size(req) if hasattr(backend, "render_size") else (req.width, req.height)
        return {**est, "eta_s": eta, "size": req.size, "render_size": f"{render[0]}x{render[1]}"}

    @app.post("/api/v2/images", status_code=202)
    def submit(req: ImageRequest):
        req, backend = prepare(req)
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
    def image(job_id: str, n: int, w: int | None = None):
        path = store.image_path(f"{job_id}/{n}")
        if path is None:
            raise HTTPException(404, "obrázek neexistuje")
        if w:
            w = max(64, min(w, 1024))
            thumb = path.with_name(f"thumb-{path.stem}-{w}.jpg")
            if not thumb.exists():
                img = Image.open(path).convert("RGB")
                img.thumbnail((w, w * 4))
                img.save(thumb, quality=85)
            return FileResponse(thumb, media_type="image/jpeg")
        return FileResponse(path, media_type="image/png")

    @app.get("/api/v2/lineage/{job_id}/{n}")
    def lineage(job_id: str, n: int):
        if store.get(job_id) is None:
            raise HTTPException(404, "úloha neexistuje")
        return store.lineage(f"{job_id}/{n}")

    @app.post("/api/v2/jobs/{job_id}/images/{n}/review")
    def review(job_id: str, n: int, body: Review):
        path = store.image_path(f"{job_id}/{n}")
        if path is None:
            raise HTTPException(404, "obrázek neexistuje")
        prov_path = path.with_suffix(".json")
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
        prov["reviewed_by"] = body.reviewed_by
        prov["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
        prov_path.write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
        return prov

    @app.post("/api/v2/prompt/expand")
    def expand(body: Expand):
        if not body.confirm_cost:
            return JSONResponse(status_code=402, content={
                "detail": "Rozepsání zadání je placené (Claude) — pošlete znovu s confirm_cost=true.",
                "estimate_usd": EXPAND_USD})
        try:
            text = expand_prompt(body.text)
        except BackendError as e:
            raise HTTPException(502, str(e)) from e
        s.library_dir.mkdir(parents=True, exist_ok=True)
        with open(s.costs_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "job_id": None,
                                "caller": body.caller, "backend": "claude:prompt-expand", "n": 0,
                                "usd": EXPAND_USD, "items": [{"what": "rozepsání zadání", "usd": EXPAND_USD}]},
                               ensure_ascii=False) + "\n")
        return {"prompt": text, "usd": EXPAND_USD}

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
