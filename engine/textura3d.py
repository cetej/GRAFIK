"""Realistický povrch vrstev 3D renderu z lokálního FLUXu, tvar drží render v hlíně (role geometry). 0 USD.

Zobecněno ze `scripts/plakaty/vorvan_flux.py` (vorvaň 5. 11.: model z průřezů „vypadá jako z gumy, nebo kovové torpédo“,
vnitřnosti jako „špatně nalepená fotografie“; operátor zvolil „Render jako předloha FLUXu“).

1. `POST /api/v2/models3d/<id>/<ver>/textura`: ke každé vrstvě renderu v hlíně (`hlina`, `samostatne`) a ke každému seedu
   jeden obraz FLUXu na zeleném plátně, vystřižený a vrácený do velikosti renderu, se shodou obrysu (IoU) s předlohou: FLUX
   nesmí změnit tvar ani měřítko k postavě. Úloha `textura3d` spouští FLUX sama (Worker.process), do Knihovny nic nepřidá.
2. `POST …/textura/<t>/vyber`: operátor vybere seed každé vrstvy, Engine složí vrstvy s barevným renderem stejné kamery:
   `okno` = alfa FLUXu oříznutá alfou barevné vrstvy (průsvitné okno v kůži), `pod` = barevná vrstva pod FLUXem (tmavá
   dutina pod vnitřnostmi). Ostatní vrstvy (postava) a body popisků zůstávají. `na_vysku` přidá verzi 9:16 překlopením podle
   úhlopříčky: týž tvor z druhé strany, hlava nahoru; kamera na výšku ukazovala víc břicha a FLUX na něm kreslil rýhy.
Na výšku FLUX předlohu nedrží (vnitřnosti IoU 0,14–0,17), proto se předloha na výšku posílá naležato a výsledek se otočí zpět.
Nic se nepřepisuje: `renders/<r>/textura-<n>/` a v něm `hotovo-<k>/`.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel

from engine.models import ImageRequest, Ref
from engine.models3d import Model3dError, Models3d, _now
from engine.panels import cut_green

KIND = "textura3d"
GREEN = (0, 177, 64)
LONG_SIDE = 1536            # lokální FLUX: 2400 × 1000 → 1536 × 640 (vorvaň)
MAX_SEEDS = 6
MIN_IOU = 0.9               # pod tím FLUX změnil tvar; vorvaň měl 0,98 až 0,99
SCREEN = "on a seamless solid bright chroma key green background, one even green colour, nothing else in the picture. "
SHAPE = " Exactly the shape, pose, angle, size and outline of <ref_image_0>."    # když to prompt sám neříká
NAME = re.compile(r"[a-z0-9_]{1,40}")
DIR = re.compile(r"(textura|hotovo)-(\d+)")


class Vrstva(BaseModel):
    prompt: str                 # anglicky: vzhled povrchu, tvar dodá předloha
    slozeni: str = "pod"        # okno | pod


class TexturaIn(BaseModel):
    render: str                 # barevný render se samostatnými vrstvami (okno v kůži, dutina)
    predloha: str               # render v hlíně se stejnou kamerou a vrstvami
    vrstvy: dict[str, Vrstva]
    seeds: list[int] = [61, 62, 63]
    caller: str = "studio"


class VyberIn(BaseModel):
    seedy: dict[str, int]
    na_vysku: bool = False


def flux_size(w: int, h: int) -> tuple[int, int]:
    """Velikost pro FLUX naležato, násobky 16, stejný poměr jako render."""
    long_, short = max(w, h), min(w, h)
    return LONG_SIDE, max(16, round(LONG_SIDE * short / long_ / 16) * 16)


def on_green(rgba: Image.Image, size: tuple[int, int]) -> Image.Image:
    bg = Image.new("RGBA", rgba.size, (*GREEN, 255))
    bg.alpha_composite(rgba)
    return bg.convert("RGB").resize(size, Image.LANCZOS)


def iou(a: Image.Image, b: Image.Image) -> float:
    x, y = np.asarray(a.getchannel("A")) > 40, np.asarray(b.getchannel("A")) > 40
    return round(float((x & y).sum() / max((x | y).sum(), 1)), 3)


def compose(mode: str, flux: Image.Image, colour: Image.Image) -> Image.Image:
    if mode == "okno":      # obrys a okno do těla z Blenderu, povrch z FLUXu
        window = np.asarray(colour.getchannel("A"), np.float32) / 255
        a = np.minimum(np.asarray(flux.getchannel("A"), np.float32) / 255, np.where(window > 0.03, window, 0))
        out = flux.copy()
        out.putalpha(Image.fromarray((a * 255).astype("uint8")))
        return out
    out = colour.copy()     # tmavá stěna dutiny z Blenderu pod vnitřnostmi
    out.alpha_composite(flux)
    return out


def transpose_points(body: dict) -> dict:
    out = {**body, "points": {k: [y, x] for k, (x, y) in body["points"].items()}, "res": body["res"][::-1]}
    if "ramecky" in body:
        out["ramecky"] = {k: [y0, x0, y1, x1] for k, (x0, y0, x1, y1) in body["ramecky"].items()}
    return out


class Textura3d:
    def __init__(self, models3d: Models3d, worker):
        self.m, self.lib, self.worker = models3d, models3d.lib, worker

    def handlers(self) -> dict:
        return {KIND: self.run}

    def _render(self, mid: str, ver: str, rid: str) -> tuple[dict, Path]:
        info = next((r for r in self.lib.read(mid, ver).get("renders", []) if r["id"] == rid), None)
        if info is None:
            raise Model3dError(f"render {rid} u modelu {mid} {ver} neexistuje")
        return info, self.lib.vdir(mid, ver) / "renders" / rid

    def enqueue(self, mid: str, ver: str, body: TexturaIn) -> dict:
        colour, cdir = self._render(mid, ver, body.render)
        clay, pdir = self._render(mid, ver, body.predloha)
        if not body.vrstvy or not body.seeds or len(body.seeds) > MAX_SEEDS or len(set(body.seeds)) != len(body.seeds):
            raise Model3dError(f"textura chce aspoň jednu vrstvu a 1 až {MAX_SEEDS} různých seedů")
        if colour["res"] != clay["res"]:
            raise Model3dError("barevný render a render v hlíně musí mít stejnou velikost a kameru")
        for name, layer in body.vrstvy.items():
            if not NAME.fullmatch(name) or layer.slozeni not in ("okno", "pod") or not layer.prompt.strip():
                raise Model3dError(f"vrstva {name!r}: název malými písmeny, slozeni okno nebo pod, prompt anglicky")
            for d in (cdir, pdir):
                if not (d / f"vrstva-{name}.png").is_file():
                    raise Model3dError(f"render {d.name} nemá vrstvu {name} (chce vrstvy se samostatne)")
        job_id = self.m.enqueue(KIND, body.caller, "flux-local", {"model_id": mid, "version": ver, **body.model_dump(exclude={"caller"})})
        return {"model_id": mid, "version": ver, "job_id": job_id, "estimate_usd": 0.0, "obrazu": len(body.vrstvy) * len(body.seeds)}

    def run(self, job_id: str, req: dict) -> dict:
        mid, ver = req["model_id"], req["version"]
        _info, cdir = self._render(mid, ver, req["render"])
        _info, pdir = self._render(mid, ver, req["predloha"])
        taken = [int(m.group(2)) for p in cdir.iterdir() if (m := DIR.fullmatch(p.name)) and m.group(1) == "textura"]
        out = cdir / f"textura-{max(taken, default=0) + 1}"
        out.mkdir()
        t0, layers = time.time(), {}
        try:
            for name, layer in req["vrstvy"].items():
                src = Image.open(pdir / f"vrstva-{name}.png").convert("RGBA")
                turn = src.height > src.width
                size = flux_size(*src.size)
                ref = out / f"predloha-{name}-zelena.png"
                on_green(src.rotate(90, expand=True) if turn else src, size).save(ref)
                seeds = {}
                for seed in req["seeds"]:
                    res = self.worker.process(f"{job_id}-{name}-{seed}", ImageRequest(
                        prompt=SCREEN + layer["prompt"] + ("" if "<ref_image_0>" in layer["prompt"] else SHAPE), size=f"{size[0]}x{size[1]}", seed=seed, translate="off",
                        caller=f"textura3d:{mid}", refs=[Ref(path=str(ref), role="geometry", source=f"render {req['predloha']} v hlíně")]), time.time())
                    cut = cut_green(Image.open(res["files"][0]).convert("RGBA"))
                    cut = (cut.rotate(-90, expand=True) if turn else cut).resize(src.size, Image.LANCZOS)
                    cut.save(out / f"flux-{name}-{seed}.png")
                    seeds[str(seed)] = {"soubor": f"flux-{name}-{seed}.png", "iou": iou(cut, src)}
                best = max(seeds, key=lambda s: seeds[s]["iou"])
                layers[name] = {"slozeni": layer["slozeni"], "seedy": seeds, "doporuceny": int(best),
                                "tvar_drzi": seeds[best]["iou"] >= MIN_IOU, "na_vysku_nalezato": turn}
        except Exception:
            shutil.rmtree(out, ignore_errors=True)
            raise
        info = {"id": f"{req['render']}-{out.name}", "slozka": out.name, "render": req["render"], "predloha": req["predloha"], "vrstvy": layers,
                "job_id": job_id, "seconds": round(time.time() - t0, 1), "created": _now()}
        (out / "textura.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        with self.lib._lock:
            self.lib.update(mid, ver, textury=self.lib.read(mid, ver).get("textury", []) + [{**info, "dir": f"renders/{req['render']}/{out.name}"}])
        return {"model_id": mid, "version": ver, **info}

    def pick(self, mid: str, ver: str, tid: str, body: VyberIn) -> dict:
        meta = next((t for t in self.lib.read(mid, ver).get("textury", []) if t["id"] == tid), None)
        if meta is None:
            raise Model3dError(f"textura {tid} u modelu {mid} {ver} neexistuje")
        cdir = self.lib.vdir(mid, ver) / "renders" / meta["render"]
        tdir = cdir / meta["slozka"]
        for name, seed in body.seedy.items():
            if name not in meta["vrstvy"] or str(seed) not in meta["vrstvy"][name]["seedy"]:
                raise Model3dError(f"vrstva {name!r} se seedem {seed} v textuře {tid} není")
        chosen = {name: body.seedy.get(name, layer["doporuceny"]) for name, layer in meta["vrstvy"].items()}
        taken = [int(m.group(2)) for p in tdir.iterdir() if (m := DIR.fullmatch(p.name)) and m.group(1) == "hotovo"]
        out = tdir / f"hotovo-{max(taken, default=0) + 1}"
        out.mkdir()
        body_json = json.loads((cdir / "body.json").read_text(encoding="utf-8"))
        files = []
        for layer in body_json.get("vrstvy", {}):
            colour = Image.open(cdir / f"vrstva-{layer}.png").convert("RGBA")
            img = compose(meta["vrstvy"][layer]["slozeni"], Image.open(tdir / f"flux-{layer}-{chosen[layer]}.png").convert("RGBA"), colour) \
                if layer in chosen else colour
            img.save(out / f"vrstva-{layer}.png")
            files.append(f"vrstva-{layer}.png")
        (out / "body.json").write_text(json.dumps({**body_json, "textura": {"id": tid, "seedy": chosen}}, ensure_ascii=False, indent=1), encoding="utf-8")
        result = {"dir": f"renders/{meta['render']}/{meta['slozka']}/{out.name}", "seedy": chosen, "vrstvy": files}
        if body.na_vysku:
            tall = out / "na-vysku"
            tall.mkdir()
            for f in files:
                Image.open(out / f).transpose(Image.Transpose.TRANSPOSE).save(tall / f)
            (tall / "body.json").write_text(json.dumps(transpose_points(json.loads((out / "body.json").read_text(encoding="utf-8"))), ensure_ascii=False, indent=1), encoding="utf-8")
            result["na_vysku"] = f"{result['dir']}/na-vysku"
        return result


def register(app: FastAPI, tex: Textura3d) -> None:
    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Model3dError as e:
            raise HTTPException(404 if "neexistuje" in str(e) else 400, str(e)) from e

    @app.post("/api/v2/models3d/{model_id}/{version}/textura", status_code=202)
    def models3d_textura(model_id: str, version: str, body: TexturaIn):
        return call(tex.enqueue, model_id, version, body)

    @app.post("/api/v2/models3d/{model_id}/{version}/textura/{textura_id}/vyber", status_code=201)
    def models3d_textura_vyber(model_id: str, version: str, textura_id: str, body: VyberIn):
        return call(tex.pick, model_id, version, textura_id, body)
