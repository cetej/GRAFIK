"""/api/v2/models3d… — the 3D step (docs/plans/2026-10-27-3d-v1.md; v2: orbit viewer, sheet on a button, a clay
render from the viewer's camera). Separate endpoints, so /api/v2/images and its clients stay unchanged (sc-7)."""
from __future__ import annotations

import base64
import hashlib
import json
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image

from pydantic import BaseModel

from engine import hotove3d
from ngm_shared import sklad3d
from ngm_shared.sklad import SkladError
from engine import models3d as m3d
from engine.models3d import (ELEVATIONS, PARTS, CameraIn, CutoutIn, Model3dError, Model3dIn, Models3d, OpotrebeniIn,
                             ReviewIn, RotateIn, StretchIn, ViewsIn)


class HotoveIn(BaseModel):
    zdroj: str                      # sklad | smithsonian | sketchfab
    id: str                         # id ve skladu (polyhaven/<slug>) / balíček Smithsonianu / uid Sketchfabu
    title: str = ""
    model_id: str | None = None     # nová verze existujícího modelu
    caller: str = "studio"


def register(app: FastAPI, models3d: Models3d, store, reflib) -> None:
    lib = models3d.lib

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Model3dError as e:
            raise HTTPException(404 if "neexistuje" in str(e) else 400, str(e)) from e

    def resolve_refs(body: Model3dIn) -> list[tuple]:
        """[(view, png, meta)]: library refs resolved, every image re-encoded as PNG."""
        out = []
        for r in body.refs:
            src, lic, author = r.source, r.license, r.author
            if r.ref_id:
                meta = reflib.get(r.ref_id)
                if meta is None:
                    raise HTTPException(404, f"předloha {r.ref_id} v knihovně neexistuje")
                raw = reflib.image_path(r.ref_id).read_bytes()
                src = src or meta.get("page_url") or meta.get("source_url") or meta["title"]
                lic, author = lic or meta.get("license"), author or meta.get("author")
            elif r.b64:
                raw = r.b64
            elif r.path and Path(r.path).is_file():
                raw = Path(r.path).read_bytes()
            else:
                raise HTTPException(400, f"předloha {m3d.VIEW_LABEL[r.view]} bez obrázku")
            png = call(m3d.decode_png, raw if isinstance(raw, str) else base64.b64encode(raw).decode())
            out.append((r.view, png, {"view": r.view, "source": src, "license": lic, "author": author,
                                      "ref_id": r.ref_id}))
        return out

    def estimate(body: Model3dIn) -> dict:
        views = [r.view for r in body.refs]
        if body.glb_b64 or body.method == "upload":
            return {"method": "upload", "recommended": "upload", "items": [], "total_usd": 0.0, "eta_s": 40,
                    "label": "Nahrát GLB"}
        method = body.method or m3d.recommend(views)
        backend = models3d.backends.get(method)
        if backend is None:
            raise HTTPException(400, f"neznámá metoda {method!r}; k dispozici: {sorted(models3d.backends)} nebo upload")
        call(backend.validate, views)
        items = backend.items(views)
        # + ~40 s for the clay views that follow automatically (spike 2026-10-27-3d-t1)
        return {"method": method, "recommended": m3d.recommend(views), "items": items,
                "total_usd": round(sum(i["usd"] for i in items), 4), "eta_s": backend.eta + 40, "label": backend.label}

    @app.get("/api/v2/models3d")
    def models3d_list():
        return lib.list()

    @app.get("/api/v2/models3d/jobs")
    def models3d_jobs(limit: int = 30):
        return store.list(limit, kinds=m3d.KINDS)

    @app.post("/api/v2/models3d/estimate")
    def models3d_estimate(body: Model3dIn):
        return estimate(body)

    @app.post("/api/v2/models3d/cutout")
    def models3d_cutout(body: CutoutIn):
        png = call(m3d.decode_png, body.b64)
        return {"b64": base64.b64encode(m3d.cutout(png)).decode("ascii")}

    def store_glb(glb: bytes, model_id: str | None, title: str, origin: str | None, caller: str, **extra) -> dict:
        """Hotový GLB do knihovny jako metoda upload (0 USD) a hned náhled v prohlížeči."""
        if not m3d.is_glb(glb):
            raise HTTPException(400, "soubor není GLB (binární glTF)")
        meta = call(lib.new_version, model_id, title, method="upload", backend=None,
                    origin=origin, request_id=None, status="model", glb_bytes=len(glb), **extra)
        (lib.vdir(meta["id"], meta["version"]) / "model.glb").write_bytes(glb)
        job_id = models3d.enqueue("viewer3d", caller, "blender", {"model_id": meta["id"], "version": meta["version"]})
        return {"model_id": meta["id"], "version": meta["version"], "job_id": job_id, "estimate_usd": 0.0}

    @app.post("/api/v2/models3d", status_code=202)
    def models3d_create(body: Model3dIn):
        est = estimate(body)
        if body.glb_b64:
            try:
                glb = base64.b64decode(body.glb_b64.split(",", 1)[-1], validate=True)
            except ValueError as e:
                raise HTTPException(400, f"GLB: neplatné base64 ({e})") from e
            return store_glb(glb, body.model_id, body.title, body.origin or None, body.caller)
        if est["method"] == "upload":
            raise HTTPException(400, "nahrání bez souboru: pošlete glb_b64")
        if not body.confirm_cost:
            return JSONResponse(status_code=402, content={
                "detail": "Placená operace — nic nespuštěno. Pošlete znovu s confirm_cost=true.",
                "method": est["method"], "estimate_usd": est["total_usd"], "items": est["items"]})
        refs = resolve_refs(body)
        backend = models3d.backends[est["method"]]
        meta = call(lib.new_version, body.model_id, body.title, method=est["method"],
                    backend=f"fal:{backend.endpoint}", request_id=None, cost_usd=est["total_usd"], items=est["items"])
        d = lib.vdir(meta["id"], meta["version"])
        saved = []
        for view, png, rmeta in refs:
            (d / f"ref-{view}.png").write_bytes(png)
            saved.append({**rmeta, "file": f"ref-{view}.png", "sha256": hashlib.sha256(png).hexdigest()})
        lib.update(meta["id"], meta["version"], refs=saved)
        job_id = models3d.enqueue("model3d", body.caller, f"fal:{backend.endpoint}",
                                  {"model_id": meta["id"], "version": meta["version"], "caller": body.caller})
        return {"model_id": meta["id"], "version": meta["version"], "job_id": job_id, "estimate_usd": est["total_usd"]}

    @app.get("/api/v2/models3d/hotove")
    def models3d_hotove_search(q: str):
        """Hotové modely zdarma (Smithsonian, Sketchfab) dřív, než se generuje; jen nabídka, nic nestahuje."""
        if not q.strip():
            raise HTTPException(400, "prázdný dotaz")
        return hotove3d.search(q.strip())

    @app.post("/api/v2/models3d/hotove", status_code=202)
    def models3d_hotove_import(body: HotoveIn):
        """Stáhne vybraný model po ověření licence (jen CC0 a CC BY) a uloží ho s autorem, licencí a odkazem."""
        try:
            glb, info = hotove3d.fetch(body.zdroj, body.id)
        except hotove3d.Hotove3dError as e:
            raise HTTPException(400, str(e)) from e
        extra = {"sklad_id": info["sklad_id"]} if body.zdroj == "sklad" else {}
        return store_glb(glb, body.model_id, body.title or info["nazev"], info["origin"], body.caller,
                         license=info["licence"], author=info["autor"], source_url=info["stranka"], zdroj=body.zdroj, **extra)

    @app.get("/api/v2/models3d/sklad/nahled")
    def models3d_sklad_nahled(id: str):
        """Náhled modelu ze skladu pro kartu ve Studiu; cesta jen ze záznamu indexu."""
        try:
            path = sklad3d.cesta(sklad3d.zaznam(id), "nahled")
        except (SkladError, OSError) as e:
            raise HTTPException(404, str(e)) from e
        if path is None or not path.is_file():
            raise HTTPException(404, "model ve skladu nemá náhled")
        return FileResponse(path)

    @app.get("/api/v2/models3d/{model_id}")
    def models3d_get(model_id: str):
        return call(lib.get, model_id)

    def has_glb(model_id: str, version: str) -> dict:
        meta = call(lib.read, model_id, version)
        if not (lib.vdir(model_id, version) / "model.glb").is_file():
            raise HTTPException(409, f"verze {version} zatím nemá model (stav {meta['status']})")
        return meta

    @app.post("/api/v2/models3d/{model_id}/{version}/views", status_code=202)
    def models3d_views(model_id: str, version: str, body: ViewsIn):
        if body.elevation not in ELEVATIONS:
            raise HTTPException(400, f"výška kamery musí být jedna z {sorted(ELEVATIONS)}")
        has_glb(model_id, version)
        job_id = models3d.enqueue("views3d", "studio", "blender",
                                  {"model_id": model_id, "version": version, "elevation": body.elevation})
        return {"job_id": job_id}

    def pending(model_id: str, version: str, kind: str) -> str | None:
        return next((j["job_id"] for j in store.list(200, kinds=(kind,)) if j["status"] in ("queued", "running")
                     and j["request"].get("model_id") == model_id and j["request"].get("version") == version), None)

    @app.post("/api/v2/models3d/{model_id}/{version}/viewer", status_code=202)
    def models3d_viewer(model_id: str, version: str, optimize_only: bool = False):
        """The light copy for the viewer; models from before v2 get it on first open (0 USD, ~10 s).
        `optimize_only`: a viewer copy from before the optimizer gets just viewer.opt.glb (~2 s)."""
        has_glb(model_id, version)
        job_id = pending(model_id, version, "viewer3d") or models3d.enqueue(
            "viewer3d", "studio", "blender", {"model_id": model_id, "version": version, "optimize_only": optimize_only})
        return {"job_id": job_id}

    @app.get("/api/v2/models3d/{model_id}/{version}/viewer.glb")
    def models3d_viewer_glb(model_id: str, version: str):
        return FileResponse(file_of(model_id, version, "viewer.glb"), media_type="model/gltf-binary")

    @app.get("/api/v2/models3d/{model_id}/{version}/viewer.opt.glb")
    def models3d_viewer_opt_glb(model_id: str, version: str):
        return FileResponse(file_of(model_id, version, "viewer.opt.glb"), media_type="model/gltf-binary")

    @app.post("/api/v2/models3d/{model_id}/{version}/review")
    def models3d_review(model_id: str, version: str, body: ReviewIn):
        # v2: the check happens in the viewer or on the sheet, so a model with a viewer copy can be ticked
        meta = call(lib.read, model_id, version)
        if body.reviewed and not meta["views"] and not meta.get("viewer"):
            raise HTTPException(409, "model nejde zkontrolovat: ještě není v prohlížeči ani na sheetu")
        meta = lib.update(model_id, version, review={"by": body.by, "at": m3d._now()} if body.reviewed else None)
        if body.reviewed and (lib.vdir(model_id, version) / "model.glb").is_file():
            # operátor 2026-11-05: zkontrolovaný model jde jako kopie i do skladu; kontrola na skladu nezávisí
            try:
                meta = lib.update(model_id, version, sklad=sklad3d.uloz_nas(lib.vdir(model_id, version), meta)["id"],
                                  sklad_chyba=None)
            except (SkladError, OSError) as e:
                meta = lib.update(model_id, version, sklad_chyba=f"kopie do skladu se nepovedla: {e}")
        return meta

    def require_review(meta: dict) -> None:
        if not meta.get("review"):
            raise HTTPException(409, "model není zkontrolovaný: otočte ho v prohlížeči (nebo projděte sheet) "
                                     "a zaškrtněte „Model zkontrolován“")

    @app.post("/api/v2/models3d/{model_id}/{version}/camera", status_code=202)
    def models3d_camera(model_id: str, version: str, body: CameraIn):
        """A clay render from exactly the viewer's camera, to be used as a geometry ref (sc-3 gate first)."""
        meta = has_glb(model_id, version)
        require_review(meta)
        key = body.key()
        if (lib.vdir(model_id, version) / "camera" / f"{key}.png").is_file():
            return {"key": key, "job_id": None, "file": f"camera/{key}.png"}
        job_id = models3d.enqueue("camera3d", "studio", "blender", {
            "model_id": model_id, "version": version, "key": key, "camera": body.model_dump()})
        return {"key": key, "job_id": job_id, "file": f"camera/{key}.png"}

    @app.post("/api/v2/models3d/{model_id}/{version}/rotate", status_code=202)
    def models3d_rotate(model_id: str, version: str, body: RotateIn):
        """Narovná model (třeba převzatý, který leží na boku): nová verze s rotací, 0 USD, původní zůstane."""
        if body.axis not in ("x", "y", "z") or body.deg not in (90, -90, 180):
            raise HTTPException(400, "osa x, y nebo z a úhel 90, -90 nebo 180")
        src = has_glb(model_id, version)
        glb = call(m3d.rotate_glb, (lib.vdir(model_id, version) / "model.glb").read_bytes(), body.axis, body.deg)
        keep = {k: src[k] for k in ("license", "author", "source_url", "zdroj", "origin") if src.get(k)}
        meta = call(lib.new_version, model_id, src["title"], method="rotate", parent=version, refs=src["refs"],
                    status="model", glb_bytes=len(glb), rotate={"axis": body.axis, "deg": body.deg}, **keep)
        (lib.vdir(model_id, meta["version"]) / "model.glb").write_bytes(glb)
        job_id = models3d.enqueue("viewer3d", "studio", "blender", {"model_id": model_id, "version": meta["version"]})
        return {"model_id": model_id, "version": meta["version"], "job_id": job_id}

    @app.post("/api/v2/models3d/{model_id}/{version}/stretch", status_code=202)
    def models3d_stretch(model_id: str, version: str, body: StretchIn):
        if body.part not in PARTS:
            raise HTTPException(400, f"část musí být jedna z {PARTS}")
        if len(body.dims) != 3 or min(body.dims) <= 0:
            raise HTTPException(400, "rozměry: délka, šířka a výška v metrech, všechny kladné")
        src = has_glb(model_id, version)
        meta = lib.new_version(model_id, src["title"], method="stretch", parent=version, refs=src["refs"],
                               stretch={"dims": body.dims, "part": body.part, "source": body.source})
        job_id = models3d.enqueue("stretch3d", "studio", "blender", {
            "model_id": model_id, "version": meta["version"], "parent": version, "dims": body.dims, "part": body.part})
        return {"model_id": model_id, "version": meta["version"], "job_id": job_id}

    @app.post("/api/v2/models3d/{model_id}/{version}/opotrebeni", status_code=202)
    def models3d_opotrebeni(model_id: str, version: str, body: OpotrebeniIn):
        """Špína ve spárách a odřené hrany v TextureCraftu: nová verze s texturami, 0 USD, původní zůstane
        (DECISIONS 2026-11-06, volba vedle dnešního opotřebení v Blenderu)."""
        from engine import texturecraft as tc
        if body.sila not in tc.SILY:
            raise HTTPException(400, f"síla musí být jedna z {sorted(tc.SILY)}")
        if not (body.spina or body.hrany):
            raise HTTPException(400, "vyberte špínu, odřené hrany, nebo obojí")
        if not tc.cli_path().is_file():
            raise HTTPException(503, f"TextureCraft není nainstalovaný ({tc.cli_path()}); CRAFT_HOME")
        src = has_glb(model_id, version)
        keep = {k: src[k] for k in ("license", "author", "source_url", "zdroj", "origin") if src.get(k)}
        meta = call(lib.new_version, model_id, src["title"], method="texturecraft", parent=version, refs=src["refs"],
                    opotrebeni=body.model_dump(), **keep)
        job_id = models3d.enqueue("opotrebeni3d", "studio", "texturecraft", {
            "model_id": model_id, "version": meta["version"], "parent": version, **body.model_dump()})
        return {"model_id": model_id, "version": meta["version"], "job_id": job_id}

    @app.post("/api/v2/models3d/{model_id}/{version}/recover", status_code=202)
    def models3d_recover(model_id: str, version: str):
        """Fetch an already paid fal result again (the step failed after submit): no second payment."""
        meta = call(lib.read, model_id, version)
        if not meta.get("request_id") or meta["method"] not in models3d.backends:
            raise HTTPException(409, "verze nemá odeslanou placenou úlohu (request_id)")
        if (lib.vdir(model_id, version) / "model.glb").is_file():
            raise HTTPException(409, "model už je stažený")
        job_id = models3d.enqueue("model3d", "studio", meta["backend"],
                                  {"model_id": model_id, "version": version, "recover": True})
        return {"job_id": job_id}

    def file_of(model_id: str, version: str, name: str) -> Path:
        d = call(lib.vdir, model_id, version)
        p = (d / name).resolve()
        if not p.is_file() or not p.is_relative_to(d.resolve()):
            raise HTTPException(404, "soubor neexistuje")
        return p

    @app.get("/api/v2/models3d/{model_id}/{version}/model.glb")
    def models3d_glb(model_id: str, version: str):
        return FileResponse(file_of(model_id, version, "model.glb"), media_type="model/gltf-binary",
                            filename=f"{model_id}-{version}.glb")

    @app.get("/api/v2/models3d/{model_id}/{version}/files/{name:path}")
    def models3d_file(model_id: str, version: str, name: str, w: int | None = None):
        p = file_of(model_id, version, name)
        if w and p.suffix == ".png":
            im = Image.open(p)
            im.thumbnail((w, w))
            buf = BytesIO()
            im.save(buf, "PNG")
            return Response(buf.getvalue(), media_type="image/png")
        return FileResponse(p)

    @app.get("/api/v2/models3d/{model_id}/{version}/as-ref")
    def models3d_as_ref(model_id: str, version: str, azimuth: int = 45, elevation: int = 20, cam: str | None = None):
        """A clay view as an image-generator ref (role geometry), only after the operator's check (sc-3).
        `cam` = a render from the viewer's camera (POST …/camera), otherwise a sheet view."""
        meta = call(lib.read, model_id, version)
        require_review(meta)
        # Převzatý model nese licenci a autora sám (CC BY chce uvést autora i u odvozeného obrazu)
        lic = sorted({r["license"] for r in meta["refs"] if r.get("license")} | ({meta["license"]} if meta.get("license") else set()))
        if meta.get("author"):
            lic = [f"{x}, autor {meta['author']}" if x == meta.get("license") else x for x in lic]
        if cam:
            info_path = file_of(model_id, version, f"camera/{cam}.json")
            c = json.loads(info_path.read_text(encoding="utf-8"))
            return {"path": str(file_of(model_id, version, c["file"])), "role": "geometry", "file": c["file"],
                    "source": f"3D model {meta['title']} {version}, bílý render z kamery prohlížeče "
                              f"(azimut {c['azimuth']:.0f}°, výška {c['elevation']:.0f}°, ohnisko {c['lens']:.0f} mm)",
                    "license": ", ".join(lic) or None}
        view = meta["views"].get(str(elevation))
        name = f"az{azimuth:03d}.png"
        if not view or name not in view["files"]:
            raise HTTPException(404, f"pohled {azimuth}° při výšce {elevation}° není vyrenderovaný")
        return {"path": str(lib.vdir(model_id, version) / view["dir"] / name), "role": "geometry",
                "file": f"{view['dir']}/{name}",
                "source": f"3D model {meta['title']} {version}, bílý pohled {azimuth}°, kamera {elevation}°",
                "license": ", ".join(lic) or None}
