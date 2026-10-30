"""GRAFIK Engine — FastAPI app, /api/v2 (spec docs/plans/2026-10-22-grafik-v2-greenfield.md § 5).

Run: python -m uvicorn engine.app:app --port 8300
"""
from __future__ import annotations

import base64
import json
from contextlib import asynccontextmanager
from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from PIL import Image
from pydantic import BaseModel

from engine.backends import (EXPAND_USD, LABELS_USD, STYLE_CARD_MAX_IMAGES, STYLE_DESCRIBE_USD, BackendError,
                             describe_style_card, estimate_usd, expand_prompt, make_backends, suggest_labels)
from engine.config import Settings
from engine.gpu import free_vram_mib
from engine.keys import get_key
from engine.jobs import JobStore, Worker, load_costs
from engine.models import ImageRequest, Ref
from engine import api3d, api_knihovna, api_scenes3d, archive, checks, localize, models3d as m3d, scenes3d
from engine.sdserver import SdServer
from engine import commons
from engine.reflib import RefLibError, RefLibrary
from engine.styles import StyleError, StyleLibrary, palette, slugify
from engine.infographics import InfoError, InfographicStore
from engine.termdb import TermDB
from engine.translate import Translator
from engine.variants import PAGE, VariantsIn, VariantStore, plan, waiting_page
from engine.workflows import RotateStep, SideStep, Workflow, WorkflowRef, WorkflowStore, rotate_request, side_request
from ngm_shared import claude
from ngm_shared.heavy_lock import holder
from ngm_shared.knihovna import KnihovnaError


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


class StyleIn(BaseModel):
    label: str
    note: str = ""
    medium: str = ""
    light: str = ""
    line: str = ""
    composition: str = ""
    avoid: str = ""
    signature: str = ""
    palette: list[dict] = []
    origin: str | None = None       # default | detected | manual
    puvod: str = ""


class StyleImages(BaseModel):
    b64: list[str] = []             # uploaded images
    jobs: list[str] = []            # "<job_id>/<n>" images from the library
    ref_ids: list[str] = []         # reference library
    confirm_cost: bool = False


class StyleSample(BaseModel):
    b64: str | None = None
    job: str | None = None          # "<job_id>/<n>"


class InfoNew(BaseModel):
    base: str                       # "<job_id>/<n>" image the infographic is built on
    title: str = ""


class InfoUpload(BaseModel):
    b64: str                        # image from the operator's computer
    name: str = ""


class InfoExport(BaseModel):
    svg: str                        # rendered by the studio (one renderer: preview = export)
    format: str = "png"


class SchemaIn(BaseModel):
    title: str
    svg: str


class SuggestLabels(BaseModel):
    confirm_cost: bool = False


class TermCheck(BaseModel):
    texts: list[str]


class Expand(BaseModel):
    text: str
    confirm_cost: bool = False
    caller: str = "studio"


def create_app(settings: Settings | None = None, backends: dict | None = None,
               server: SdServer | None = None, start_worker: bool = True, backends3d: dict | None = None,
               blender=None, ask=claude.ask) -> FastAPI:
    """`ask` = volání Claude pro počeštění a kontroly (testy ho mockují, ngm_shared.claude)."""
    s = settings or Settings()
    sd = server or SdServer(s)
    store = JobStore(s.db_path)
    bk = backends or make_backends(s, sd)
    termdb = TermDB(Path(s.termdb) if s.termdb else None)
    translator = Translator(s.translations_path, termdb)
    reflib = RefLibrary(s.reflib_dir)
    stylelib = StyleLibrary(s.knihovna_dir, defaults=s.styles_dir)
    infos = InfographicStore(s.library_dir / "infographics", s.data_dir / "schemas")
    workflows = WorkflowStore(s.data_dir / "workflows")
    batches = VariantStore(s.library_dir / "variants")
    worker = Worker(s, store, bk, translator=translator)
    models3d = m3d.Models3d(s, store, sd, worker.gpu_lock,
                            m3d.make_backends3d(s) if backends3d is None else backends3d, worker._log_cost, blender)
    worker.handlers.update(models3d.handlers())
    scenes = scenes3d.Scenes3d(models3d)
    worker.handlers.update(scenes.handlers())
    localizer = localize.Localizer(s, store, worker._log_cost, ask)
    worker.handlers.update(localizer.handlers())

    @asynccontextmanager
    async def lifespan(_app):
        store.recover_interrupted()
        models3d.lib.mark_interrupted()
        models3d.lib.migrate_legacy()
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
    app.state.models3d = models3d
    api3d.register(app, models3d, store, reflib)
    api_scenes3d.register(app, scenes, models3d, store)
    localize.register(app, localizer, store, reflib)
    checks.register(app, store, reflib, worker._log_cost, ask)
    archive.register(app, s)
    api_knihovna.register(app, s)

    @app.get("/api/v2/health")
    def health():
        return {"engine": "ok", "sd_server": sd.status(), "queue_len": store.queue_len(),
                "running_job": worker.running, "gpu_free_mib": free_vram_mib(),
                "heavy_lock": holder(s.gpu_lock_path),
                "backends": sorted(bk), "default_backend": "flux-local"}

    def prepare(req: ImageRequest):
        """Resolve backend and the edit parent; raise HTTPException on a bad request."""
        backend = bk.get(req.backend)
        if backend is None:
            raise HTTPException(400, f"neznámý backend {req.backend!r}; k dispozici: {sorted(bk)}")
        if any((r.ref_id or r.knihovna) and not r.path for r in req.refs):
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
                elif r.knihovna and not r.path:
                    try:
                        found = api_knihovna.resolve(s.knihovna_dir, r.knihovna)
                    except KnihovnaError as e:
                        raise HTTPException(400, str(e)) from e
                    except LookupError as e:
                        raise HTTPException(404, str(e)) from e
                    p = found["puvod"]
                    r = r.model_copy(update={
                        "path": str(found["path"]), "knihovna": found["knihovna"],
                        "source": r.source or p.get("page_url") or p.get("source_url") or f"knihovna {found['knihovna']}",
                        "license": r.license or p.get("license"), "author": r.author or p.get("author")})
                refs.append(r)
            req = req.model_copy(update={"refs": refs})
        if req.style_id or req.style:
            # a library slug in `style` (spec § 5) or `style_id` -> the card's words; free text stays as it is
            slug = req.style_id or req.style.strip()
            try:
                card = stylelib.get(slug)
            except StyleError:
                card = None
            if card:
                req = req.model_copy(update={"style": card["prompt"], "style_id": slug})
            elif req.style_id:
                raise HTTPException(404, f"styl {req.style_id} v knihovně neexistuje")
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
        est = estimate_usd(req, backend, *translator.pending(req))
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
        today = datetime.now().strftime("%Y-%m-%d")
        spent = load_costs(s.costs_path)
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
                {"id": "termdb", "label": "Terminologická databáze (termdb, sdílená s NG-ROBOT)", "connected": termdb.available,
                 "note": "jen čtení, zdarma" if termdb.available else f"nenalezena: {s.termdb or 'vypnuta'}"},
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
        est = estimate_usd(req, backend, *translator.pending(req))
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

    # -- batch of variants to pick from ("Dávka na výběr") ----------------
    @app.post("/api/v2/variants", status_code=201)
    def create_variants(body: VariantsIn):
        """count images spread over styles as ordinary jobs; the estimate covers the WHOLE batch.
        Local FLUX only: a paid generator gets no batch button (operator decision 2026-10-26)."""
        if body.request.backend != "flux-local":
            raise HTTPException(400, "dávka variant jen s lokálním FLUX (0 USD)")
        reqs = [prepare(body.request.model_copy(update={"n": n, "style": style or body.request.style,
                                                        "style_id": None if style else body.request.style_id}))[0]
                for style, n in plan(body.count, body.styles or [None])]
        items, total = [], 0.0
        for req in reqs:
            est = estimate_usd(req, bk[req.backend], *translator.pending(req))
            total += est["total_usd"]
            items += est["items"]
        if total > 0 and not body.request.confirm_cost:
            return JSONResponse(status_code=402, content={
                "detail": "Placená operace — nic nespuštěno. Pošlete znovu s confirm_cost=true.",
                "backend": body.request.backend, "estimate_usd": round(total, 4), "items": items})
        job_ids = [store.add(r) for r in reqs]
        batch = batches.create(body.title or body.request.prompt[:80], body.request.prompt, job_ids, body.count)
        return {**batch, "page": f"/api/v2/variants/{batch['id']}/{PAGE}"}

    @app.get("/api/v2/variants/{batch_id}")
    def variants_status(batch_id: str):
        batch = batches.get(batch_id)
        if batch is None:
            raise HTTPException(404, "dávka neexistuje")
        statuses = [(store.get(j) or {}).get("status") for j in batch["job_ids"]]
        return {**batch, "page": f"/api/v2/variants/{batch_id}/{PAGE}", "jobs_total": len(statuses),
                "jobs_done": sum(st in ("done", "failed", "cancelled") for st in statuses),
                "jobs_failed": sum(st in ("failed", "cancelled") for st in statuses)}

    @app.get("/api/v2/variants/{batch_id}/{name}")
    def variants_file(batch_id: str, name: str):
        batch = batches.get(batch_id)
        if batch is None:
            raise HTTPException(404, "dávka neexistuje")
        if name == PAGE and batches.file(batch_id, PAGE) is None:
            jobs_ = [store.get(j) for j in batch["job_ids"]]
            finished = [j for j in jobs_ if j and j["status"] in ("done", "failed", "cancelled")]
            if len(finished) < len(jobs_):
                failed = sum(j["status"] != "done" for j in finished)
                return HTMLResponse(waiting_page(batch, len(finished), len(jobs_), failed))
            if not any(j["status"] == "done" for j in finished):
                raise HTTPException(409, "žádná úloha dávky se nepovedla")
            batches.build_page(batch, finished, store.image_path)
        path = batches.file(batch_id, name)
        if path is None:
            raise HTTPException(404, "soubor dávky neexistuje")
        return FileResponse(path)

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

    # -- style library (G4) -------------------------------------------------
    def _style_public(card: dict) -> dict:
        base = f"/api/v2/styles/{card['slug']}/samples/"
        return {**card, "sample_urls": [base + n for n in card["samples"]]}

    def _style_or_404(slug: str) -> dict:
        try:
            card = stylelib.get(slug)
        except StyleError as e:
            raise HTTPException(400, str(e)) from e
        if card is None:
            raise HTTPException(404, f"styl {slug} neexistuje")
        return card

    def _style_images(body: StyleImages) -> list[bytes]:
        out = []
        try:
            out += [base64.b64decode(b.split(",", 1)[-1]) for b in body.b64]
        except ValueError as e:
            raise HTTPException(400, f"neplatné base64 ({e})") from e
        for ref in body.jobs:
            path = store.image_path(ref)
            if path is None:
                raise HTTPException(404, f"obrázek {ref} neexistuje")
            out.append(path.read_bytes())
        for ref_id in body.ref_ids:
            path = reflib.image_path(ref_id)
            if path is None:
                raise HTTPException(404, f"předloha {ref_id} neexistuje")
            out.append(path.read_bytes())
        if not out:
            raise HTTPException(400, "pošlete aspoň jeden obrázek")
        if len(out) > STYLE_CARD_MAX_IMAGES:
            raise HTTPException(400, f"nejvýš {STYLE_CARD_MAX_IMAGES} obrázků")
        return out

    @app.get("/api/v2/styles")
    def styles():
        try:
            cards = stylelib.list()
        except StyleError as e:  # a hand-broken card in the shared library: say which one
            raise HTTPException(500, str(e)) from e
        return [_style_public(c) for c in cards]

    @app.get("/api/v2/styles/{slug}")
    def style(slug: str):
        return _style_public(_style_or_404(slug))

    @app.post("/api/v2/styles", status_code=201)
    def style_create(body: StyleIn):
        slug = slugify(body.label)
        if stylelib.get(slug):
            raise HTTPException(409, f"styl {slug} už existuje, zvolte jiný název")
        try:
            return _style_public(stylelib.save(slug, body.model_dump()))
        except StyleError as e:
            raise HTTPException(400, str(e)) from e

    @app.put("/api/v2/styles/{slug}")
    def style_save(slug: str, body: StyleIn):
        _style_or_404(slug)
        try:
            return _style_public(stylelib.save(slug, body.model_dump()))
        except StyleError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/api/v2/styles/{slug}")
    def style_delete(slug: str):
        _style_or_404(slug)
        return {"moved_to": stylelib.delete(slug)}

    @app.get("/api/v2/styles/{slug}/samples/{name}")
    def style_sample(slug: str, name: str):
        _style_or_404(slug)
        path = stylelib.sample_path(slug, name)
        if path is None:
            raise HTTPException(404, "ukázka neexistuje")
        return FileResponse(path, media_type="image/png" if path.suffix == ".png" else "image/jpeg")

    @app.post("/api/v2/styles/{slug}/samples", status_code=201)
    def style_add_sample(slug: str, body: StyleSample):
        _style_or_404(slug)
        if body.job:
            path = store.image_path(body.job)
            if path is None:
                raise HTTPException(404, f"obrázek {body.job} neexistuje")
            data = path.read_bytes()
        elif body.b64:
            data = base64.b64decode(body.b64.split(",", 1)[-1])
        else:
            raise HTTPException(400, "pošlete b64 nebo job")
        try:
            return _style_public(stylelib.add_sample(slug, data))
        except StyleError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/api/v2/styles/{slug}/samples/{name}")
    def style_remove_sample(slug: str, name: str):
        _style_or_404(slug)
        try:
            return _style_public(stylelib.remove_sample(slug, name))
        except StyleError as e:
            raise HTTPException(404, str(e)) from e

    @app.post("/api/v2/styles/palette")
    def style_palette(body: StyleImages):
        """Free: k-means over the pixels."""
        return {"palette": palette(_style_images(body))}

    @app.post("/api/v2/styles/describe")
    def style_describe(body: StyleImages):
        """Paid: Claude looks at the samples and writes the card (draft, nothing is saved)."""
        images = _style_images(body)
        if not body.confirm_cost:
            return JSONResponse(status_code=402, content={
                "detail": "Popis stylu je placený (Claude) — pošlete znovu s confirm_cost=true.",
                "estimate_usd": STYLE_DESCRIBE_USD,
                "items": [{"what": f"popis stylu z {len(images)} obrázků (Claude Haiku)", "usd": STYLE_DESCRIBE_USD}]})
        try:
            card = describe_style_card(images)
        except BackendError as e:
            raise HTTPException(502, str(e)) from e
        s.library_dir.mkdir(parents=True, exist_ok=True)
        with open(s.costs_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "job_id": None,
                                "caller": "studio", "backend": "claude:style-card", "n": len(images),
                                "usd": STYLE_DESCRIBE_USD,
                                "items": [{"what": "popis stylu z obrázků", "usd": STYLE_DESCRIBE_USD}]},
                               ensure_ascii=False) + "\n")
        return {**card, "palette": palette(images), "origin": "detected", "usd": STYLE_DESCRIBE_USD}

    # -- infographics (G5) ---------------------------------------------------
    def _prov(ref: str) -> dict | None:
        j = store.get(ref.split("/")[0])
        files = ((j or {}).get("result") or {}).get("files", [])
        n = int(ref.split("/")[1])
        if not j or not 0 <= n < len(files):
            return None
        return json.loads(Path(files[n]).with_suffix(".json").read_text(encoding="utf-8"))

    def _info_or_404(info_id: str) -> dict:
        try:
            doc = infos.get(info_id)
        except InfoError as e:
            raise HTTPException(400, str(e)) from e
        if doc is None:
            raise HTTPException(404, "infografika neexistuje")
        return doc

    @app.get("/api/v2/infographics")
    def info_list():
        return infos.list()

    @app.post("/api/v2/infographics", status_code=201)
    def info_create(body: InfoNew):
        if store.image_path(body.base) is None:
            raise HTTPException(404, f"obrázek {body.base} neexistuje")
        return infos.create(body.base, body.title.strip(), _prov(body.base))

    @app.post("/api/v2/infographics/upload", status_code=201)
    def info_upload(body: InfoUpload):
        try:
            with Image.open(BytesIO(base64.b64decode(body.b64.split(",", 1)[-1]))) as im:
                im.load()
                rgb = im.convert("RGB")
        except (ValueError, OSError) as e:
            raise HTTPException(400, f"obrázek nejde přečíst ({e})") from e
        job_id = store.add_done("upload", "studio", {"prompt": "", "refs": [], "source": body.name}, {"files": []})
        job_dir = s.library_dir / datetime.now().strftime("%Y-%m") / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        path = job_dir / "image-0.png"
        rgb.save(path)
        (job_dir / "image-0.json").write_text(json.dumps({
            "job_id": job_id, "file": path.name, "source": body.name, "ai_generated": False, "reviewed_by": None,
            "created": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False, indent=2), encoding="utf-8")
        store.finish(job_id, {"files": [str(path)], "dir": str(job_dir), "cost_usd": 0.0})
        return infos.create(f"{job_id}/0", Path(body.name).stem, _prov(f"{job_id}/0"))

    @app.get("/api/v2/infographics/{info_id}")
    def info_get(info_id: str):
        return _info_or_404(info_id)

    @app.put("/api/v2/infographics/{info_id}")
    def info_save(info_id: str, body: dict):
        _info_or_404(info_id)
        if body.get("base") and store.image_path(body["base"]) is None:
            raise HTTPException(404, f"obrázek {body['base']} neexistuje")
        try:
            return infos.save(info_id, body)
        except InfoError as e:
            raise HTTPException(400, str(e)) from e

    @app.delete("/api/v2/infographics/{info_id}")
    def info_delete(info_id: str):
        _info_or_404(info_id)
        return {"moved_to": infos.delete(info_id)}

    @app.post("/api/v2/infographics/{info_id}/export", status_code=201)
    def info_export(info_id: str, body: InfoExport):
        doc = _info_or_404(info_id)
        try:
            out = infos.export(info_id, body.svg, body.format, _prov(doc["base"]))
        except InfoError as e:
            raise HTTPException(400, str(e)) from e
        return {**out, "url": f"/api/v2/infographics/{info_id}/exports/{out['file']}"}

    @app.get("/api/v2/infographics/{info_id}/exports/{name}")
    def info_export_file(info_id: str, name: str):
        _info_or_404(info_id)
        path = infos.export_path(info_id, name)
        if path is None:
            raise HTTPException(404, "export neexistuje")
        media = {"png": "image/png", "svg": "image/svg+xml", "pdf": "application/pdf"}[path.suffix[1:]]
        return FileResponse(path, media_type=media, filename=f"infografika-{info_id}{path.suffix}")

    @app.post("/api/v2/infographics/{info_id}/suggest-labels")
    def info_suggest(info_id: str, body: SuggestLabels):
        """Paid: Claude proposes parts of the object to label (names and points, never facts)."""
        doc = _info_or_404(info_id)
        if not body.confirm_cost:
            return JSONResponse(status_code=402, content={
                "detail": "Návrh popisků je placený (Claude) — pošlete znovu s confirm_cost=true.",
                "estimate_usd": LABELS_USD, "items": [{"what": "návrh popisků (Claude Haiku)", "usd": LABELS_USD}]})
        try:
            labels = suggest_labels(store.image_path(doc["base"]).read_bytes(), doc["title"])
        except BackendError as e:
            raise HTTPException(502, str(e)) from e
        s.library_dir.mkdir(parents=True, exist_ok=True)
        with open(s.costs_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "job_id": None,
                                "caller": "studio", "backend": "claude:labels", "n": len(labels), "usd": LABELS_USD,
                                "items": [{"what": "návrh popisků infografiky", "usd": LABELS_USD}]},
                               ensure_ascii=False) + "\n")
        return {"labels": labels, "usd": LABELS_USD}

    @app.post("/api/v2/terms/check")
    def terms_check(body: TermCheck):
        """Free, local: what termdb confirms, what is ambiguous and what it does not know (infographic check)."""
        if not termdb.available:
            return {"available": False, "results": []}
        return {"available": True, "results": [termdb.check(t) for t in body.texts[:40] if t.strip()]}

    @app.get("/api/v2/schemas")
    def schemas():
        return infos.schemas()

    @app.post("/api/v2/schemas", status_code=201)
    def schema_save(body: SchemaIn):
        try:
            return infos.save_schema(body.title.strip() or "schéma", body.svg)
        except InfoError as e:
            raise HTTPException(400, str(e)) from e

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
        entries = load_costs(s.costs_path)
        return {"total_usd": round(sum(e["usd"] for e in entries), 4), "entries": entries[-limit:],
                "pending": [e for e in entries if e.get("status") == "pending"]}

    return app


app = create_app()
