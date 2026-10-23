"""GRAFIK Engine — FastAPI app, /api/v2 (spec docs/plans/2026-10-22-grafik-v2-greenfield.md § 5).

Run: python -m uvicorn engine.app:app --port 8300
"""
from __future__ import annotations

import base64
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
from engine.keys import get_key
from engine.jobs import JobStore, Worker
from engine.models import ImageRequest, Ref
from engine.sdserver import SdServer
from engine import commons
from engine.reflib import RefLibError, RefLibrary
from engine.translate import Translator
from engine.workflows import RotateStep, SideStep, Workflow, WorkflowRef, WorkflowStore, rotate_request, side_request


# Body models live at module level: with `from __future__ import annotations` FastAPI
# resolves annotations from module globals, so a class local to create_app would be
# misread as a query parameter.
class Review(BaseModel):
    reviewed_by: str


class Repeat(BaseModel):
    n: int = 0                  # which image of the job the variant comes from
    confirm_cost: bool = False


class RefIn(BaseModel):
    url: str | None = None          # image URL or a Pinterest pin page (resolved via og:image)
    b64: str | None = None
    page_url: str | None = None
    title: str | None = None
    author: str | None = None
    license: str | None = None
    origin: str | None = None       # commons | pinterest | web | upload; guessed from the URL when empty


class WorkflowIn(BaseModel):
    object: str | None = None
    refs: list[dict] | None = None
    side_pick: str | None = None
    fixed: str | None = None
    pick: str | None = None


class CommonsImport(BaseModel):
    file: str                       # "File:Name.jpg" or "Name.jpg"


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
    translator = Translator(s.translations_path)
    reflib = RefLibrary(s.reflib_dir)
    workflows = WorkflowStore(s.data_dir / "workflows")
    worker = Worker(s, store, bk, translator=translator)

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
        if any(r.ref_id and not r.path for r in req.refs):
            refs = []
            for r in req.refs:
                if r.ref_id and not r.path:
                    meta = reflib.get(r.ref_id)
                    if meta is None:
                        raise HTTPException(404, f"předloha {r.ref_id} v knihovně neexistuje")
                    r = r.model_copy(update={
                        "path": str(reflib.image_path(r.ref_id)),
                        "source": r.source or meta.get("page_url") or meta.get("source_url") or meta["title"],
                        "license": r.license or meta.get("license"), "author": r.author or meta.get("author")})
                refs.append(r)
            req = req.model_copy(update={"refs": refs})
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
        est = estimate_usd(req, backend, translator.pending(req))
        eta = backend.eta_s(req) if hasattr(backend, "eta_s") else None
        render = backend.render_size(req) if hasattr(backend, "render_size") else (req.width, req.height)
        return {**est, "eta_s": eta, "size": req.size, "render_size": f"{render[0]}x{render[1]}"}

    @app.get("/api/v2/settings")
    def settings_status():
        """What the Settings card shows: which services are connected (key found yes/no, never the value),
        the local generator, the reference library. Pinterest needs no account here: pins come in through
        the operator's own logged-in Chrome (docs/pinterest.md)."""
        def key(*names):
            return any(get_key(n) for n in names)
        costs = s.costs_path.read_text(encoding="utf-8").splitlines() if s.costs_path.exists() else []
        today = datetime.now().strftime("%Y-%m-%d")
        spent = [json.loads(line) for line in costs if line]
        return {
            "flux_local": {"model": s.sd_model, "dir": str(s.flux_dir), "exe_found": (s.flux_dir / s.sd_exe).exists(),
                           "model_found": (s.flux_dir / s.sd_model).exists(), "sd_server": sd.status(),
                           "gpu_free_mib": free_vram_mib(), "min_free_vram_mib": s.min_free_vram_mib,
                           "idle_timeout_s": s.idle_timeout_s},
            "services": [
                {"id": "claude", "label": "Claude (překlad a rozepsání zadání)", "connected": key("ANTHROPIC_API_KEY")},
                {"id": "gemini", "label": "Google Gemini (Nano Banana Pro)",
                 "connected": key("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GEMINI_API_KEY")},
                {"id": "fal", "label": "fal.ai (FLUX.2 pro, Krea, Nano Banana přes fal)", "connected": key("FAL_KEY", "FAL_API_KEY")},
                {"id": "commons", "label": "Wikimedia Commons", "connected": True, "note": "bez účtu"},
                {"id": "pinterest", "label": "Pinterest", "connected": True,
                 "note": "bez účtu v GRAFIK: piny přes váš přihlášený Chrome (záložka → GRAFIK nebo Claude in Chrome)"},
            ],
            "keys_from": "proměnné prostředí a .env v NG-ROBOT / ADOBE-AUTOMAT (STOPA load_keys.py), hodnoty se nezobrazují",
            "library": {"refs": len(reflib.list())},
            "costs": {"today_usd": round(sum(e["usd"] for e in spent if e["ts"].startswith(today)), 4),
                      "total_usd": round(sum(e["usd"] for e in spent), 4)},
        }

    @app.post("/api/v2/images", status_code=202)
    def submit(req: ImageRequest):
        req, backend = prepare(req)
        est = estimate_usd(req, backend, translator.pending(req))
        if est["total_usd"] > 0 and not req.confirm_cost:
            return JSONResponse(status_code=402, content={
                "detail": "Placená operace — nic nespuštěno. Pošlete znovu s confirm_cost=true.",
                "backend": req.backend, "estimate_usd": est["total_usd"], "items": est["items"]})
        job_id = store.add(req)
        job = store.get(job_id)
        return {"job_id": job_id, "status": job["status"], "position": job["position"],
                "estimate_usd": est["total_usd"]}

    @app.post("/api/v2/jobs/{job_id}/repeat", status_code=202)
    def repeat(job_id: str, body: Repeat):
        """Another variant: same request (refs included), new seed. A variant of an edit is
        its sibling (same parent and box); otherwise the source image becomes the parent."""
        raw = store.raw_request(job_id)
        if raw is None:
            raise HTTPException(404, "úloha neexistuje")
        raw.update(seed=None, n=1, confirm_cost=body.confirm_cost)
        if raw.get("edit"):  # prepare() prepends the parent again
            raw["refs"] = [r for r in raw["refs"] if r.get("source") != f"verze {raw['parent']}"]
        else:
            raw["parent"] = f"{job_id}/{body.n}"
        return submit(ImageRequest.model_validate(raw))

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

    @app.get("/api/v2/jobs/{job_id}/refs/{i}")
    def ref_image(job_id: str, i: int):
        j = store.get(job_id)
        files = ((j or {}).get("result") or {}).get("files", [])
        path = Path(files[0]).parent / "refs" / f"ref-{i}.png" if files else None
        if path is None or not path.exists():
            raise HTTPException(404, "předloha neexistuje")
        return FileResponse(path, media_type="image/png")

    # -- reference library ("Schránka předloh") ---------------------------
    def _ref_public(meta: dict) -> dict:
        return {**meta, "image": f"/api/v2/refs/{meta['id']}/image"}

    @app.get("/api/v2/refs")
    def refs(origin: str | None = None):
        return [_ref_public(m) for m in reflib.list(origin)]

    @app.post("/api/v2/refs", status_code=201)
    def add_ref(body: RefIn):
        try:
            if body.url:
                meta = reflib.add_url(body.url, page_url=body.page_url, title=body.title or "", author=body.author,
                                      license=body.license, origin=body.origin)
            elif body.b64:
                meta = reflib.add(base64.b64decode(body.b64.split(",", 1)[-1]), origin=body.origin or "upload",
                                  title=body.title or "", page_url=body.page_url, author=body.author,
                                  license=body.license)
            else:
                raise HTTPException(400, "pošlete url nebo b64")
        except RefLibError as e:
            raise HTTPException(400, str(e)) from e
        return _ref_public(meta)

    @app.get("/api/v2/refs/{ref_id}/image")
    def ref_lib_image(ref_id: str, w: int | None = None):
        try:
            path = reflib.image_path(ref_id)
        except RefLibError as e:
            raise HTTPException(400, str(e)) from e
        if path is None:
            raise HTTPException(404, "předloha neexistuje")
        if w:
            w = max(64, min(w, 1024))
            thumb = path.with_name(f"thumb-{w}.jpg")
            if not thumb.exists():
                img = Image.open(path).convert("RGB")
                img.thumbnail((w, w * 4))
                img.save(thumb, quality=85)
            return FileResponse(thumb, media_type="image/jpeg")
        return FileResponse(path, media_type="image/png")

    @app.post("/api/v2/refs/{ref_id}/seen")
    def ref_seen(ref_id: str):
        try:
            return _ref_public(reflib.mark_seen(ref_id))
        except RefLibError as e:
            raise HTTPException(404, str(e)) from e

    @app.get("/api/v2/commons/search")
    def commons_search(q: str, limit: int = 24):
        try:
            return commons.search(q, min(max(limit, 1), 50))
        except RefLibError as e:
            raise HTTPException(502, str(e)) from e

    @app.post("/api/v2/commons/import", status_code=201)
    def commons_import(body: CommonsImport):
        try:
            return _ref_public(commons.import_file(reflib, body.file))
        except RefLibError as e:
            raise HTTPException(400, str(e)) from e

    # -- guided workflow "historický objekt" -------------------------------
    def _wf(wf_id: str) -> Workflow:
        try:
            wf = workflows.get(wf_id)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if wf is None:
            raise HTTPException(404, "průvodce neexistuje")
        return wf

    def _run_step(req: ImageRequest, confirm: bool, estimate_only: bool):
        req = req.model_copy(update={"confirm_cost": confirm})
        return estimate(req) if estimate_only else submit(req)

    @app.post("/api/v2/workflows/historical", status_code=201)
    def wf_create(body: WorkflowIn):
        return workflows.create(object=body.object or "", refs=body.refs or [])

    @app.get("/api/v2/workflows")
    def wf_list():
        return workflows.list()

    @app.get("/api/v2/workflows/{wf_id}")
    def wf_get(wf_id: str):
        return _wf(wf_id)

    @app.patch("/api/v2/workflows/{wf_id}")
    def wf_patch(wf_id: str, body: WorkflowIn):
        wf = _wf(wf_id)
        for key, val in body.model_dump(exclude_unset=True).items():
            if key in ("side_pick", "fixed", "pick") and val and store.image_path(val) is None:
                raise HTTPException(404, f"obrázek {val} neexistuje")
            setattr(wf, key, [WorkflowRef(**r) for r in val] if key == "refs" else val)
        if "side_pick" in body.model_fields_set:
            wf.fixed = None  # a new elevation invalidates fixes of the old one
        return workflows.save(wf)

    @app.post("/api/v2/workflows/{wf_id}/side")
    def wf_side(wf_id: str, body: SideStep):
        wf = _wf(wf_id)
        try:
            req = side_request(wf, body.n)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        r = _run_step(req, body.confirm_cost, body.estimate_only)
        if isinstance(r, dict) and "job_id" in r:
            wf.side_job, wf.side_pick, wf.fixed = r["job_id"], None, None
            workflows.save(wf)
        return r

    @app.post("/api/v2/workflows/{wf_id}/rotate")
    def wf_rotate(wf_id: str, body: RotateStep):
        wf = _wf(wf_id)
        base = wf.base and store.image_path(wf.base)
        if not base:
            raise HTTPException(400, "nejdřív vyberte bokorys (krok 2)")
        try:
            req = rotate_request(wf, body, str(base))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        r = _run_step(req, body.confirm_cost, body.estimate_only)
        if isinstance(r, dict) and "job_id" in r:
            wf.rotate_job, wf.pick, wf.view, wf.background = r["job_id"], None, body.view, body.background
            workflows.save(wf)
        return r

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
