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
3. `POST …/textura/<t>/stranka` složí stránky 16:9 a 9:16 do Infografik, `POST …/textura/<t>/tema` dá hotového tvora tématu
   jako vlastní obraz a řetězec infografiky z něj pak stránky složí sám (fáze 3b).
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


def flatten(folder: Path, files: list[str]) -> None:
    """obraz.png = vrstvy na sobě zdola nahoru: dokument s panely (engine/panels.py copy_render) a náhledy ho potřebují."""
    layers = [Image.open(folder / f).convert("RGBA") for f in files]
    out = Image.new("RGBA", layers[0].size, (0, 0, 0, 0))
    for layer in layers:
        out.alpha_composite(layer)
    out.save(folder / "obraz.png")


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
                layers[name] = {"slozeni": layer["slozeni"], "prompt": layer["prompt"], "seedy": seeds, "doporuceny": int(best),
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
        # pořadí vrstev zdola nahoru: co se skládá `pod` (vnitřnosti), pak ostatní, jak je render vyjmenoval (kůže, postava)
        order = sorted(body_json.get("vrstvy", {}), key=lambda n: (meta["vrstvy"].get(n, {}).get("slozeni") != "pod"))
        files = []
        for layer in order:
            colour = Image.open(cdir / f"vrstva-{layer}.png").convert("RGBA")
            img = compose(meta["vrstvy"][layer]["slozeni"], Image.open(tdir / f"flux-{layer}-{chosen[layer]}.png").convert("RGBA"), colour) \
                if layer in chosen else colour
            img.save(out / f"vrstva-{layer}.png")
            files.append(f"vrstva-{layer}.png")
        flatten(out, files)
        (out / "body.json").write_text(json.dumps({**body_json, "vrstvy": {n: body_json["vrstvy"][n] for n in order}, "textura": {"id": tid, "seedy": chosen}},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
        result = {"dir": f"renders/{meta['render']}/{meta['slozka']}/{out.name}", "seedy": chosen, "vrstvy": files}
        if body.na_vysku:
            tall = out / "na-vysku"
            tall.mkdir()
            for f in files:
                Image.open(out / f).transpose(Image.Transpose.TRANSPOSE).save(tall / f)
            flatten(tall, files)
            (tall / "body.json").write_text(json.dumps(transpose_points(json.loads((out / "body.json").read_text(encoding="utf-8"))), ensure_ascii=False, indent=1), encoding="utf-8")
            result["na_vysku"] = f"{result['dir']}/na-vysku"
        return result


class StrankaIn(BaseModel):
    hotovo: str                         # hotovo-<k> z výběru seedu
    titulek: str
    popisky: dict[str, str] = {}        # bod z body.json -> český popisek; prázdný se nevypíše, druhý řádek za „\n“
    nazvy_vrstev: dict[str, str] = {}   # vrstva -> název ve VectorCraftu
    formaty: list[str] = ["16:9", "9:16"]


FORMATS = {"16:9": ("1920x1080", ""), "9:16": ("1080x1920", "na-vysku")}
GAP = 24        # mezera mezi tvorem a řadou popisků


def _row(labels: list[dict], size: float, width: int) -> None:
    """Popisky v jedné řadě se nesmí překrýt: každý začíná až za koncem předchozího, co přeteče vpravo, se posune zpět."""
    from engine.panels import _text_box
    labels.sort(key=lambda lb: lb["pos"][0])
    edge = 20.0
    for lb in labels:
        x = _text_box(lb, size)[0]
        if x < edge:
            lb["pos"][0] += edge - x
        x, _y, w, _h = _text_box(lb, size)
        edge = x + w + size * 0.6
    right = width - 20.0        # co přeteče vpravo, jde zpět jen o tolik, kolik je třeba, a nikdy přes levý okraj
    for lb in reversed(labels):
        x, _y, w, _h = _text_box(lb, size)
        if x + w > right:
            lb["pos"][0] -= min(x + w - right, x - 20)
        right = _text_box(lb, size)[0] - size * 0.6


def _column(labels: list[dict], size: float, top: float, bottom: float) -> None:
    """Popisky ve sloupci pod sebou, každý co nejblíž výšce své věci a bez překryvu."""
    from engine.panels import _text_box
    labels.sort(key=lambda lb: lb["pos"][1])
    edge = top
    for lb in labels:
        lb["pos"][1] = max(lb["pos"][1], edge)
        edge = lb["pos"][1] + _text_box(lb, size)[3] + size * 0.5
    over = edge - size * 0.5 - bottom
    for lb in reversed(labels):
        if over <= 0:
            break
        lb["pos"][1] -= over


def crop_to_content(src: Path, dst: Path, margin: float = 0.02) -> None:
    """Vrstvy, obraz a body oříznuté na společný obsah: tvor pak vyplní plochu stránky, ne prázdné okolí renderu."""
    if (dst / "body.json").is_file():
        return
    dst.mkdir(parents=True, exist_ok=True)
    files = ["obraz.png", *sorted(p.name for p in src.glob("vrstva-*.png"))]
    with Image.open(src / "obraz.png") as im:
        w, h = im.size
        x0, y0, x1, y1 = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox() or (0, 0, w, h)
    pad = round(max(x1 - x0, y1 - y0) * margin)
    box = (max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad))
    for f in files:
        with Image.open(src / f) as im:
            im.crop(box).save(dst / f)
    body = json.loads((src / "body.json").read_text(encoding="utf-8"))
    body["points"] = {k: [x - box[0], y - box[1]] for k, (x, y) in body["points"].items()}
    body["ramecky"] = {k: [a - box[0], b - box[1], c - box[0], d - box[1]] for k, (a, b, c, d) in body.get("ramecky", {}).items()}
    if "origin" in body:
        body["origin"] = [body["origin"][0] - box[0], body["origin"][1] - box[1]]
    body["res"] = [box[2] - box[0], box[3] - box[1]]
    body["viditelne"] = visible_points(dst, body)
    (dst / "body.json").write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")


def visible_points(folder: Path, body: dict) -> list[str]:
    """Blender počítá viditelnost paprskem, který skončí na kůži; orgán za průsvitným oknem je ale vidět. Bod je vidět, když leží
    na některé vrstvě a vrstvy nad ní jsou v tom místě průsvitné (vrstvy zdola nahoru jako v body.json)."""
    alphas = [np.asarray(Image.open(folder / f"vrstva-{n}.png").getchannel("A")) for n in body.get("vrstvy", {})]
    out = []
    for name, (x, y) in body["points"].items():
        xi, yi = int(round(x)), int(round(y))
        if not alphas or not (0 <= yi < alphas[0].shape[0] and 0 <= xi < alphas[0].shape[1]):
            continue
        hit = next((i for i, a in enumerate(alphas) if a[yi, xi] > 40), None)
        if hit is not None and all(a[yi, xi] < 200 for a in alphas[hit + 1:]):
            out.append(name)
    return out


def _wrap(text: str, chars: int) -> list[str]:
    out, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > chars:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return out + ([cur] if cur else [])


def page_fields(fmt: str, folder: Path, rel: str, req: StrankaIn, model_title: str, textured: dict) -> dict:
    """Stránka s jedním velkým tvorem z vrstev: vnitřnosti oříznuté obrysem kůže, záře kolem netexturovaných vrstev (postava).
    Na šířku popisky střídavě v řadě nad a pod tvorem se svislým vodítkem, na výšku ve sloupci vedle tvora, vždy u bodu z body.json
    (vorvan_stranka.py). Písmo: nejmenší text 1/30 šířky stránky (docs/infografiky-zasady.md, Web a mobil)."""
    from engine.panels import MOBIL, _text_box, placement, to_page
    size_name = FORMATS[fmt][0]
    W, H = (int(v) for v in size_name.split("x"))
    k = W / MOBIL["jednotek"]
    font = round(W / 30 / 0.86 + 0.5)          # druhý řádek je 0,86 písma a má mít aspoň 1/30 šířky
    body = json.loads((folder / "body.json").read_text(encoding="utf-8"))
    top = MOBIL["titulek_y"] * k + GAP
    drafts = []
    for point, text in req.popisky.items():
        lines = [t.strip() for t in text.split("\n") if t.strip()]
        if lines and point in body["points"]:
            small = [row for line in lines[1:] for row in _wrap(line, 28 if fmt == "16:9" else 18)]
            drafts.append({"text": lines[0], "small": small, "kotva": point, "align": "left", "size": font, "pos": [0.0, 0.0]})
    # na šířku nejdřív jedna řada nad tvorem, dokud se vejde; řada pod ním bere tvoru druhý pás výšky (vorvaň 5. 11.: dvě řady 49 %
    # šířky, jedna 94 %). Popisky jdou do řad podle důležitosti, v řadě pak podle polohy bodu zleva doprava.
    order = sorted(range(len(drafts)), key=lambda i: body["points"][drafts[i]["kotva"]][0 if fmt == "16:9" else 1])
    rows, used = {}, 0.0
    for i in range(len(drafts)):
        used += _text_box(drafts[i], font)[2] + font
        rows[i] = "nad" if used <= W - 40 else "dole"
    if fmt == "16:9":
        band = {r: max((_text_box(lb, font)[3] for i, lb in enumerate(drafts) if rows[i] == r), default=-GAP) + GAP for r in ("nad", "dole")}
        rect = [20.0, top + band["nad"], W - 40.0, H - top - band["nad"] - band["dole"] - 20.0]
    else:       # tvor vlevo, popisky vpravo (vorvan_stranka.py, operátor: obraz a popisky zrcadlově): tlama je vpravo a vodítko ji nekříží
        column = max((_text_box(lb, font)[2] for lb in drafts), default=0) + GAP
        rect = [20.0, top, W - 40.0 - column, H - top - 20.0]
    place = placement({"rect": rect}, body)
    with Image.open(folder / "obraz.png") as im:
        bx0, by0, bx1, by1 = im.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    bx0, bx1 = place["x"] + bx0 * place["k"], place["x"] + bx1 * place["k"]
    by0, by1 = place["y"] + by0 * place["k"], place["y"] + by1 * place["k"]
    above, below = [], []
    for i in order:
        label = drafts[i]
        ax, ay = to_page(place, label["kotva"], "hlavni")
        h = _text_box(label, font)[3]
        if fmt == "16:9" and rows[i] == "nad":
            label.update(nad=True, pos=[ax - 10, max(top, by0 - GAP - h)])
            above.append(label)
        elif fmt == "16:9":
            label.update(dole=True, pos=[ax - 10, min(by1 + GAP, H - 20 - h)])
            below.append(label)
        else:
            label.update(pos=[bx1 + GAP, ay - font * 0.72])
            above.append(label)
    if fmt == "16:9":
        _row(above, font, W)
        _row(below, font, W)
    else:
        _column(above, font, top, H - 20)
    labels = above + below
    layers = body.get("vrstvy", {})
    inner = [n for n, v in textured.items() if v.get("slozeni") == "pod" and n in layers]
    skin = next((n for n, v in textured.items() if v.get("slozeni") == "okno" and n in layers), None)
    main = {"id": "hlavni", "typ": "obraz", "poradi": 1, "nazev": model_title, "rect": rect, "zdroj": {"slozka": rel},
            "vrstvy": {n: req.nazvy_vrstev.get(n, n) for n in layers}, "hrana": False,
            "zar_vrstvy": [n for n in layers if n not in textured], "labels": labels}
    if skin:
        main["orez"] = {n: skin for n in inner}
    # hlavní věc dominuje: na šířku podíl šířky stránky, na výšku podíl výšky, který tvor zabírá
    share = (bx1 - bx0) / W if fmt == "16:9" else (by1 - by0) / H
    return {"title": req.titulek, "size": size_name, "panels": [main], "_podil": share}


def _done(tex: Textura3d, mid: str, ver: str, tid: str, hotovo: str) -> tuple[dict, dict, Path]:
    """(model, textura, složka hotovo-<k>) z výběru seedu."""
    meta = tex.lib.read(mid, ver)
    info = next((t for t in meta.get("textury", []) if t["id"] == tid), None)
    if info is None:
        raise Model3dError(f"textura {tid} u modelu {mid} {ver} neexistuje")
    if not DIR.fullmatch(hotovo):
        raise Model3dError("hotovo je hotovo-<k> z výběru seedu")
    base = tex.lib.vdir(mid, ver) / "renders" / info["render"] / info["slozka"] / hotovo
    if not (base / "obraz.png").is_file():
        raise Model3dError(f"{hotovo} u textury {tid} nemá obraz.png")
    return meta, info, base


MIN_SHARE = {"16:9": 0.55, "9:16": 0.6}    # tvor menší než tohle je vedle popisků vedlejší (vorvaň z řetězce 5. 11.: 41 % šířky)


def fit_labels(fmt: str, folder: Path, rel: str, req: StrankaIn, model_title: str, textured: dict) -> tuple[dict, list[str]]:
    """Pole stránky a co vypadlo: obraz před počtem popisků (operátor 2. 11.), dokud je tvor malý, vypadne poslední, tedy nejméně důležitý."""
    popisky = {k: v for k, v in req.popisky.items() if v.strip()}
    dropped = []
    while True:
        fields = page_fields(fmt, folder, rel, req.model_copy(update={"popisky": popisky}), model_title, textured)
        if fields.pop("_podil") >= MIN_SHARE[fmt] or len(popisky) <= 1:
            return fields, dropped
        last = list(popisky)[-1]
        dropped.append(popisky.pop(last).split("\n")[0])


def make_pages(tex: Textura3d, library_dir: Path, mid: str, ver: str, tid: str, req: StrankaIn, make_doc, extra: dict | None = None) -> tuple[list[dict], list[str]]:
    """Dokumenty s panely ze stejných vrstev, jeden na formát, a hlášení o vypadlých popiscích; `make_doc(fields)` dokument vytvoří a uloží."""
    meta, info, base = _done(tex, mid, ver, tid, req.hotovo)
    if not req.formaty or set(req.formaty) - set(FORMATS):
        raise Model3dError(f"formáty {', '.join(FORMATS)}")
    if not any(t.strip() for t in req.popisky.values()):
        raise Model3dError("stránka chce aspoň jeden popisek")
    docs, notes = [], []
    for fmt in req.formaty:
        source = base / FORMATS[fmt][1] if FORMATS[fmt][1] else base
        if not (source / "obraz.png").is_file():
            raise Model3dError(f"{req.hotovo} nemá {'verzi na výšku (vyber s na_vysku)' if FORMATS[fmt][1] else 'obraz.png'}")
        folder = base / f"stranka-{fmt.replace(':', 'x')}"
        crop_to_content(source, folder)
        rel = folder.relative_to(library_dir).as_posix()
        fields, dropped = fit_labels(fmt, folder, rel, req, meta["title"], info["vrstvy"])
        notes += [f"{fmt}: popisek {name} vypadl, jinak by byl tvor na stránce malý" for name in dropped]
        docs.append(make_doc({**fields, **(extra or {})}))
    return docs, notes


class TemaIn(BaseModel):
    qid: str                            # položka Wikidaty tématu, např. Q81214 vorvaň
    hotovo: str
    nazev: str                          # co obraz ukazuje, čte ho model návrhů
    popisky: dict[str, str]             # bod z body.json -> krátký český název části


def to_topic(tex: Textura3d, library_dir: Path, mid: str, ver: str, tid: str, req: TemaIn) -> dict:
    """Hotový 3D tvor jako vlastní obraz tématu (library/tema/<qid>/obrazy.json, serie.own_pictures): řetězec ho dá do návrhů
    jako hlavní obraz a stránku složí z jeho vrstev (chain._stranky). Stejný model a textura přepíše svůj starší řádek."""
    if not re.fullmatch(r"Q\d+", req.qid):
        raise Model3dError("qid je položka Wikidaty, např. Q81214")
    if not req.nazev.strip():
        raise Model3dError("napište, co obraz ukazuje")
    _meta, info, base = _done(tex, mid, ver, tid, req.hotovo)
    points = json.loads((base / "body.json").read_text(encoding="utf-8"))["points"]
    names = {k: v.strip() for k, v in req.popisky.items() if v.strip()}
    if not names or set(names) - set(points):
        raise Model3dError(f"popisky patří k bodům modelu: {', '.join(points)}")
    path = library_dir / "tema" / req.qid / "obrazy.json"
    rows = json.loads(path.read_text(encoding="utf-8"))["obrazy"] if path.is_file() else []
    row = {"id": f"3d-{mid}", "nazev": req.nazev.strip(), "slozka": base.relative_to(library_dir).as_posix(), "popisky": names, "druh": "zvire",
           "ai": "FLUX 3 Klein (textura), model z dílů v Blenderu", "model": {"model_id": mid, "version": ver},
           "tvor3d": {"model_id": mid, "version": ver, "textura": tid, "hotovo": req.hotovo, "vrstvy": info["vrstvy"]}}
    rows = [r for r in rows if r.get("id") != row["id"]] + [row]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"obrazy": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return row


def register_page(app: FastAPI, tex: Textura3d, library_dir: Path, make_panel_doc, finish) -> None:
    """Stránka do záložky Infografiky z hotové textury; `make_panel_doc` je cesta POST /api/v2/infographics/panels,
    `finish(doc)` uloží dokument bez kreditu na stránce (operátor 5. 11.: zdroje a kredity patří do popisků na webu)."""
    @app.post("/api/v2/models3d/{model_id}/{version}/textura/{textura_id}/stranka", status_code=201)
    def models3d_textura_stranka(model_id: str, version: str, textura_id: str, body: StrankaIn):
        try:
            docs, notes = make_pages(tex, library_dir, model_id, version, textura_id, body, lambda f: finish(make_panel_doc(f)))
        except Model3dError as e:
            raise HTTPException(404 if "neexistuje" in str(e) else 400, str(e)) from e
        return {"dokumenty": [{"id": d["id"], "size": d["size"], "title": d["title"]} for d in docs], "hlaseni": notes}

    @app.post("/api/v2/models3d/{model_id}/{version}/textura/{textura_id}/tema", status_code=201)
    def models3d_textura_tema(model_id: str, version: str, textura_id: str, body: TemaIn):
        try:
            return to_topic(tex, library_dir, model_id, version, textura_id, body)
        except Model3dError as e:
            raise HTTPException(404 if "neexistuje" in str(e) else 400, str(e)) from e


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
