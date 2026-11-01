"""Model z dílů a jeho barevný render jako úlohy Engine (krok 3b, docs/plans/2026-11-01-infografika-z-tematu.md).

Popis stavby (`engine/parts_spec.py`) zůstává u verze modelu jako `popis.json`, protože render staví geometrii znovu a po
pojmenovaných dílech. Každý render má vlastní `renders/r-<n>/`: obraz, `body.json` s kotvami a podle požadavku vrstvy po
objektech; nic se nepřepisuje. 0 USD, Blender jen pod zámkem těžké práce.

Render jde na GPU a před ním se zastaví vlastní sd-server: 9 s na snímek proti 61 s na CPU (1920 × 1080, 96 vzorků), takže
zámek pro ostatní projekty drží sedmkrát kratší dobu. Když OptiX není, přejde sám na CPU; `GRAFIK_RENDER_CPU=1` si CPU vynutí.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from engine.models3d import Model3dError, Models3d, _now, is_glb, opaque_share
from engine.parts_spec import CUTS, MAX_METRES, NAME, SpecError, validate

BLENDER_DIR = Path(__file__).resolve().parent / "blender"
PARTS_SCRIPT = BLENDER_DIR / "lod_parts.py"
RENDER_SCRIPT = BLENDER_DIR / "render_parts.py"
POHLEDY = ("celek", "rez", "pudorys", "pruceli", "bok", "rozklad")   # kopie klíčů VIEWS z render_parts.py, hlídá test
MAX_LAYERS = 12     # víc dílů dá render_parts.py dohromady podle materiálu
RENDER_DIR = re.compile(r"r-(\d+)")


class PartsIn(BaseModel):
    title: str = ""
    model_id: str | None = None
    spec: dict
    caller: str = "studio"


class RenderIn(BaseModel):
    pohled: str = "celek"
    res: tuple[int, int] = (1920, 1080)
    samples: int = 96
    vrstvy: bool = False
    posuny: dict[str, float] = {}   # metry nahoru nebo dolů po dílech, rozložený pohled
    skupiny: dict[str, list[str]] | None = None     # vlastní vrstvy; bez nich po dílech, u víc dílů podle materiálu
    caller: str = "studio"


def part_names(spec: dict) -> list[str]:
    return [p["nazev"] for p in spec["dily"] if p["typ"] not in CUTS]


def check_render(body: RenderIn, spec: dict) -> dict:
    """Požadavek pro render_parts.py; co nejde vyrenderovat, řekne API hned, ne až úloha ve frontě."""
    if body.pohled not in POHLEDY:
        raise Model3dError(f"neznámý pohled {body.pohled!r}, jde použít {', '.join(POHLEDY)}")
    if not all(64 <= v <= 6000 for v in body.res):
        raise Model3dError("rozměr renderu musí být 64 až 6000 pixelů")
    if not 8 <= body.samples <= 1024:
        raise Model3dError("počet vzorků musí být 8 až 1024")
    names = part_names(spec)
    if body.pohled == "rozklad" and not body.posuny:
        raise Model3dError("rozložený pohled potřebuje posuny dílů v metrech")
    for name, dz in body.posuny.items():
        if name not in names:
            raise Model3dError(f"posun dílu {name!r}: takový díl model nemá")
        if abs(dz) > MAX_METRES:
            raise Model3dError(f"posun dílu {name!r} je mimo rozsah")
    if body.skupiny is not None:
        for key in body.skupiny:
            if not NAME.fullmatch(key):
                raise Model3dError(f"název vrstvy {key!r} musí být malá písmena bez diakritiky, číslice a podtržítka")
        grouped = [n for group in body.skupiny.values() for n in group]
        if sorted(grouped) != sorted(names):     # díl mimo vrstvy by z ruční úpravy potichu zmizel
            raise Model3dError(f"vrstvy musí obsahovat každý díl právě jednou, díly modelu: {', '.join(names)}")
    out = {"pohled": body.pohled, "res": list(body.res), "samples": body.samples, "posuny": body.posuny}
    if body.vrstvy or body.skupiny is not None:
        out["vrstvy"] = True
    if body.skupiny is not None:
        out["skupiny"] = body.skupiny
    return out


class Parts3d:
    """Úlohy nad knihovnou modelů: `parts3d` postaví GLB z popisu, `render3d` z popisu udělá barevný obraz."""

    def __init__(self, models3d: Models3d):
        self.m = models3d
        self.lib = models3d.lib

    def handlers(self) -> dict:
        return {"parts3d": self.run_parts, "render3d": self.run_render}

    def create(self, body: PartsIn, spec: dict) -> dict:
        meta = self.lib.new_version(body.model_id, body.title or spec["nazev"], method="parts", backend=None, request_id=None)
        d = self.lib.vdir(meta["id"], meta["version"])
        (d / "popis.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        job_id = self.m.enqueue("parts3d", body.caller, "blender", {"model_id": meta["id"], "version": meta["version"], "caller": body.caller})
        return {"model_id": meta["id"], "version": meta["version"], "job_id": job_id, "estimate_usd": 0.0}

    def spec_of(self, model_id: str, version: str) -> dict:
        p = self.lib.vdir(model_id, version) / "popis.json"
        if not p.is_file():
            raise Model3dError("barevný render po objektech umí jen model z dílů, tahle verze popis nemá")
        return json.loads(p.read_text(encoding="utf-8"))

    def enqueue_render(self, model_id: str, version: str, body: RenderIn) -> dict:
        render = check_render(body, self.spec_of(model_id, version))
        job_id = self.m.enqueue("render3d", body.caller, "blender", {"model_id": model_id, "version": version, "render": render})
        return {"model_id": model_id, "version": version, "job_id": job_id, "estimate_usd": 0.0}

    def run_parts(self, job_id: str, req: dict) -> dict:
        mid, ver = req["model_id"], req["version"]
        d = self.lib.vdir(mid, ver)
        self.lib.update(mid, ver, status="generating", started=_now(), error=None)
        t0 = time.time()
        tmp, report = d / "model.tmp.glb", d / "model.tmp.glb.dily.json"
        try:
            self.m.lock_for_blender(job_id)
            try:
                self.m.blender.run(PARTS_SCRIPT, [str(tmp), str(d / "popis.json")], d / "blender-parts.log")
            finally:
                self.m.gpu_lock.release()
            if not tmp.is_file() or not is_glb(tmp.read_bytes()[:4]) or not report.is_file():
                raise Model3dError("Blender nezapsal model z dílů (log blender-parts.log)")
            dily = json.loads(report.read_text(encoding="utf-8"))
            tmp.replace(d / "model.glb")
            report.replace(d / "dily.json")
        except Exception as e:
            tmp.unlink(missing_ok=True)
            report.unlink(missing_ok=True)
            self.m._fail(req, e)
            raise
        self.lib.update(mid, ver, status="model", glb_bytes=(d / "model.glb").stat().st_size, dily=sorted(dily["dily"]),
                        bez_kontaktu=dily["bez_kontaktu"], timing_s={"model": round(time.time() - t0, 1)})
        viewer_job = self.m.enqueue("viewer3d", req.get("caller", "studio"), "blender", {"model_id": mid, "version": ver})
        return {"model_id": mid, "version": ver, "glb": str(d / "model.glb"), "viewer_job": viewer_job, "bez_kontaktu": dily["bez_kontaktu"]}

    def run_render(self, job_id: str, req: dict) -> dict:
        mid, ver, render = req["model_id"], req["version"], req["render"]
        d = self.lib.vdir(mid, ver)
        root = d / "renders"
        root.mkdir(exist_ok=True)
        taken = [int(m.group(1)) for p in root.iterdir() if (m := RENDER_DIR.match(p.stem))]     # i po pádu, nic se nepřepisuje
        name = f"r-{max(taken, default=0) + 1}"
        out, log = root / name, root / f"{name}.log"
        out.mkdir()
        layers = len(render["skupiny"]) if "skupiny" in render else MAX_LAYERS
        passes = 1 + (min(layers, len(part_names(self.spec_of(mid, ver)))) if render.get("vrstvy") else 0)
        t0 = time.time()
        try:
            self.m.lock_for_blender(job_id)
            try:
                self.m.sd.stop("barevný render v Blenderu")
                self.m.blender.run(RENDER_SCRIPT, [str(d / "popis.json"), str(out), json.dumps(render, ensure_ascii=False)], log,
                                   self.m.s.blender_timeout_s * passes)
            finally:
                self.m.gpu_lock.release()
            if not (out / "obraz.png").is_file() or not (out / "body.json").is_file():
                raise Model3dError(f"Blender nezapsal render (log renders/{log.name})")
            if opaque_share(out / "obraz.png") < 0.005:
                raise Model3dError(f"render je prázdný: model je mimo záběr (log renders/{log.name})")
        except Exception:
            shutil.rmtree(out, ignore_errors=True)
            raise
        body = json.loads((out / "body.json").read_text(encoding="utf-8"))
        info = {"id": name, "pohled": render["pohled"], "res": render["res"], "samples": render["samples"], "posuny": render["posuny"],
                "vrstvy": body.get("vrstvy", {}), "file": f"renders/{name}/obraz.png", "body": f"renders/{name}/body.json", "job_id": job_id,
                "zarizeni": body.get("zarizeni"), "seconds": round(time.time() - t0, 1), "rendered": _now()}
        with self.lib._lock:
            self.lib.update(mid, ver, renders=self.lib.read(mid, ver).get("renders", []) + [info])
        return {"model_id": mid, "version": ver, **info}


def register(app: FastAPI, parts: Parts3d) -> None:
    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Model3dError as e:
            raise HTTPException(404 if "neexistuje" in str(e) else 400, str(e)) from e

    @app.post("/api/v2/models3d/parts", status_code=202)
    def models3d_parts(body: PartsIn):
        try:
            spec = validate(body.spec)
        except SpecError as e:
            raise HTTPException(400, str(e)) from e
        return call(parts.create, body, spec)

    @app.post("/api/v2/models3d/{model_id}/{version}/render", status_code=202)
    def models3d_render(model_id: str, version: str, body: RenderIn):
        return call(parts.enqueue_render, model_id, version, body)
