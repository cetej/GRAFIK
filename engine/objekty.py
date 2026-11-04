"""Vrstvy objektů v generované ilustraci: najít objekty, vyříznout je, dokreslit pod nimi podklad, pak je mazat,
posouvat a měnit (operátor 2026-11-04, náčrt panelu Vrstvy).

Uložení vedle obrázku: <job_dir>/objekty-<n>/
  objekty.json        seznam objektů, podklad, úlohy
  maska-<id>[-v<k>].png    maska objektu (L, 0/255) z SAM-3
  vrstva-<id>[-v<k>].png   objekt na průhledném pozadí v plné velikosti obrázku
  podklad-maska-<job>.png  plocha, kterou FLUX smí přepsat při dokreslení podkladu

Hledání: Claude (Haiku) pojmenuje objekty a dá rámečky, SAM-3 na fal ke každému rámečku masku (jedno volání na objekt:
víc rámečků v jednom volání vrátí jen jednu masku, sonda 2026-11-04). Podklad i změna objektu jdou přes lokální FLUX
jako úprava s maskou: mimo masku zůstane obraz přesně původní (`engine/paste.py`).

Vrstva má alfu z masky rozšířené o pár px, podklad se přepisuje v o něco širší ploše (`grow`); podklad + všechny
vrstvy na místě se od originálu liší jen v tom úzkém prstenci (kontrola `check`)."""
from __future__ import annotations

import base64
import json
import re
import threading
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Callable

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, ImageFilter
from pydantic import BaseModel, Field, field_validator

from engine.backends import BackendError, claude_text
from engine.models import EditSpec, ImageRequest, Ref, check_box
from engine.translate import TRANSLATE_USD, is_czech

KIND = "objekty"
SAM_ENDPOINT = "fal-ai/sam-3/image"
SAM_USD = 0.005         # za volání, GET api.fal.ai/v1/models/pricing 2026-11-04
FIND_USD = 0.01         # Claude Haiku s obrázkem, stejný odhad jako popis stylu
MAX_OBJECTS = 6
MIN_COVER = 0.001       # menší maska je šum, ne objekt
NAME_RE = re.compile(r"^[a-z0-9]+$")

FIND_INSTRUCTION = (
    "This is a generated illustration. The brief it was made from: {brief}\n\n"
    "List the distinct main objects in the picture that an editor might want to delete, move or change: people, "
    "animals, vehicles, buildings, furniture, tools and other things. Not the background itself (sky, sea, floor, "
    "wall, ground), not shadows, not small details of a larger object. At most {n} objects, ordered from the one "
    "furthest back to the one in front. For each give: \"cs\", a short Czech name (1-3 words, lowercase), \"en\", "
    "a short English noun phrase, and \"box\", the tight bounding box [top, left, bottom, right] on a 0-1000 grid "
    "of the image height and width. Answer with a JSON list and nothing else: "
    '[{{"cs": "...", "en": "...", "box": [0, 0, 0, 0]}}]'
)


class ObjektyError(ValueError):
    pass


# -- čistá práce s obrazem (testy bez sítě) ------------------------------------------------------------------------

def grow(size: tuple[int, int]) -> tuple[int, int, int]:
    """(o kolik px rozšířit plochu podkladu, o kolik alfu vrstvy, změkčení okraje vrstvy) podle delší strany.
    Vrstva je těsně u objektu: širší lem (4× base) nesl při posunu pruh původního pozadí a uřízl skály ostrova
    (měření 2026-11-04). Úzký prstenec mezi alfou vrstvy a plochou podkladu ukazuje dokreslený podklad."""
    base = max(2, round(0.003 * max(size)))
    return 2 * base, base, max(1, base // 2)


def _dilate(mask: Image.Image, px: int) -> Image.Image:
    # MaxFilter s velkým oknem je pomalý: opakovaný 3×3 dá stejný čtverec
    for _ in range(px):
        mask = mask.filter(ImageFilter.MaxFilter(3))
    return mask


def _binary(mask: Image.Image) -> Image.Image:
    return mask.convert("L").point(lambda v: 255 if v > 127 else 0)


def layer_alpha(mask: Image.Image) -> Image.Image:
    _, px, soft = grow(mask.size)
    return _dilate(_binary(mask), px).filter(ImageFilter.GaussianBlur(soft))


def cut_layer(image: Image.Image, mask: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    rgba.putalpha(layer_alpha(mask))
    return rgba


def plate_mask(masks: list[Image.Image], size: tuple[int, int]) -> Image.Image:
    """Plocha, kterou smí FLUX přepsat: sjednocení masek, rozšířené o okraj objektu, ale uvnitř plné alfy vrstvy."""
    union = Image.new("L", size, 0)
    for m in masks:
        union = Image.fromarray(np.maximum(np.asarray(union), np.asarray(_binary(m.resize(size, Image.NEAREST)))))
    px, _, _ = grow(size)
    return _dilate(union, px).filter(ImageFilter.GaussianBlur(1))


def bbox_1000(mask: Image.Image, margin: float = 0.0) -> list[int]:
    """[top, left, bottom, right] na mřížce 0–1000, s okrajem `margin` (podíl strany)."""
    a = np.asarray(mask.convert("L")) > 127
    if not a.any():
        raise ObjektyError("maska je prázdná")
    ys, xs = np.nonzero(a)
    h, w = a.shape
    t, l, b, r = ys.min() / h - margin, xs.min() / w - margin, (ys.max() + 1) / h + margin, (xs.max() + 1) / w + margin
    return [max(0, round(t * 1000)), max(0, round(l * 1000)), min(1000, round(b * 1000)), min(1000, round(r * 1000))]


def box_px(box: list[int], size: tuple[int, int]) -> tuple[int, int, int, int]:
    """[top, left, bottom, right] 0–1000 -> (x_min, y_min, x_max, y_max) v px."""
    w, h = size
    t, l, b, r = box
    return round(l * w / 1000), round(t * h / 1000), round(r * w / 1000), round(b * h / 1000)


def compose(base: Image.Image, layers: list[tuple[Image.Image, tuple[int, int]]]) -> Image.Image:
    """Podklad a viditelné vrstvy (odzadu dopředu) s posunem v px."""
    out = base.convert("RGBA")
    for layer, (dx, dy) in layers:
        frame = Image.new("RGBA", out.size, (0, 0, 0, 0))
        frame.paste(layer, (dx, dy))
        out = Image.alpha_composite(out, frame)
    return out.convert("RGB")


def check(original: Image.Image, composed: Image.Image) -> dict:
    """Složení na místě proti originálu: průměrný rozdíl (0–255) a podíl px, které se liší o víc než 8."""
    a = np.asarray(original.convert("RGB"), dtype=np.int16)
    b = np.asarray(composed.convert("RGB").resize(original.size), dtype=np.int16)
    diff = np.abs(a - b).max(axis=2)
    return {"mean_diff": round(float(diff.mean()), 3), "changed_share": round(float((diff > 8).mean()), 5)}


def _png(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def layers_svg(base: Image.Image, objects: list[tuple[str, str, Image.Image, tuple[int, int]]]) -> str:
    """Podklad a každý objekt ve vlastní <g id> (VectorCraft: horní skupina = vrstva) s vloženým PNG."""
    w, h = base.size

    def image(img: Image.Image, dx: int = 0, dy: int = 0) -> str:
        data = base64.b64encode(_png(img)).decode()
        return f'<image x="{dx}" y="{dy}" width="{img.width}" height="{img.height}" href="data:image/png;base64,{data}"/>'

    groups = "".join(f'<g id="{oid}" data-nazev="{nazev}">{image(img, *off)}</g>' for oid, nazev, img, off in objects)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<g id="Podklad">{image(base.convert("RGB"))}</g><g id="Objekty">{groups}</g></svg>')


def parse_found(text: str) -> list[dict]:
    m = re.search(r"\[.*\]", text, re.S)
    try:
        items = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        items = None
    if not isinstance(items, list):
        raise ObjektyError(f"hledání objektů: odpověď není JSON seznam ({text[:120]!r})")
    out = []
    for it in items[:MAX_OBJECTS]:
        try:
            box = check_box([int(round(float(v))) for v in it["box"]])
        except (KeyError, TypeError, ValueError):
            continue
        cs, en = str(it.get("cs") or "").strip(), str(it.get("en") or "").strip()
        if cs and en:
            out.append({"cs": cs, "en": en, "box": box})
    return out


# -- placená volání (testy je podstrčí) ---------------------------------------------------------------------------

def claude_find(png: bytes, brief: str) -> list[dict]:
    img = Image.open(BytesIO(png)).convert("RGB")
    img.thumbnail((1024, 1024))
    return parse_found(claude_text([
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                     "data": base64.b64encode(_png(img)).decode()}},
        {"type": "text", "text": FIND_INSTRUCTION.format(brief=brief or "(none)", n=MAX_OBJECTS)}], 900, "hledání objektů"))


def pick_mask(masks: list[Image.Image], box: tuple[int, int, int, int]) -> int | None:
    """Který výskyt z hledání podle slova patří k rámečku: největší překryv obalu masky s rámečkem, při nulovém
    překryvu nejbližší střed. Rámeček od Clauda bývá posunutý (racek nad ním, u domku jen střecha; měření 2026-11-04)."""
    x0, y0, x1, y1 = box
    best, best_key = None, None
    for i, m in enumerate(masks):
        a = np.asarray(m) > 127
        if not a.any():
            continue
        ys, xs = np.nonzero(a)
        mx0, my0, mx1, my1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        inter = max(0, min(x1, mx1) - max(x0, mx0)) * max(0, min(y1, my1) - max(y0, my0))
        union = (x1 - x0) * (y1 - y0) + (mx1 - mx0) * (my1 - my0) - inter
        dist = ((x0 + x1 - mx0 - mx1) ** 2 + (y0 + y1 - my0 - my1) ** 2) ** 0.5
        key = (inter / union if union else 0.0, -dist)
        if best_key is None or key > best_key:
            best, best_key = i, key
    return best


def sam_segment(png: bytes, box: tuple[int, int, int, int], text: str | None = None) -> tuple[Image.Image, float | None]:
    """Maska objektu. S `text` hledá SAM-3 objekt podle slova a z výskytů vybere ten u rámečku (px); bez něj obtáhne
    to, co je v rámečku. `prompt` a `apply_mask: false` posílat vždy (docs/capabilities/sam3-point.md)."""
    import fal_client
    import httpx

    from engine.keys import get_key
    key = get_key("FAL_KEY", "FAL_API_KEY")
    if not key:
        raise BackendError("fal: chybí FAL_KEY / FAL_API_KEY")
    client = fal_client.SyncClient(key=key, default_timeout=300)
    x0, y0, x1, y1 = box
    args = {"prompt": text or "", "apply_mask": False, "include_scores": True, "output_format": "png"}
    if text:
        args.update(return_multiple_masks=True, max_masks=8)
    else:
        args["box_prompts"] = [{"x_min": x0, "y_min": y0, "x_max": x1, "y_max": y1}]
    try:
        r = client.subscribe(SAM_ENDPOINT, arguments={"image_url": client.upload(png, "image/png"), **args})
        masks = [Image.open(BytesIO(httpx.get(m["url"], timeout=120).raise_for_status().content)).convert("L")
                 for m in r.get("masks") or []]
    except Exception as e:  # fal_client má vlastní typy chyb
        raise BackendError(f"{SAM_ENDPOINT}: {type(e).__name__}: {e}") from e
    size = Image.open(BytesIO(png)).size
    masks = [m.resize(size, Image.NEAREST) for m in masks]
    i = pick_mask(masks, box)
    if i is None:
        raise BackendError(f"{SAM_ENDPOINT}: {'objekt ' + repr(text) if text else 'v rámečku'} nenašel")
    return masks[i], (r.get("scores") or [None] * len(masks))[i]


# -- knihovna objektů jednoho obrázku -----------------------------------------------------------------------------

class Objekty:
    def __init__(self, settings, store, worker, log_cost: Callable[[dict], None],
                 find: Callable | None = None, segment: Callable | None = None):
        self.s, self.store, self.worker, self.log_cost = settings, store, worker, log_cost
        self.find, self.segment = find or claude_find, segment or sam_segment
        self._lock = threading.RLock()

    def handlers(self) -> dict:
        return {KIND: self.run}

    # soubory
    def image(self, ref: str) -> Path:
        path = self.store.image_path(ref)
        if path is None:
            raise LookupError(f"obrázek {ref} neexistuje")
        return path

    def dir(self, ref: str) -> Path:
        return self.image(ref).parent / f"objekty-{ref.split('/')[1]}"

    def load(self, ref: str) -> dict | None:
        p = self.dir(ref) / "objekty.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def save(self, ref: str, doc: dict) -> None:
        d = self.dir(ref)
        d.mkdir(parents=True, exist_ok=True)
        doc["updated"] = datetime.now().isoformat(timespec="seconds")
        tmp = d / "objekty.json.tmp"
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(d / "objekty.json")

    def _cost(self, ref: str, what: str, usd: float, backend: str) -> None:
        if usd:
            self.log_cost({"job_id": f"objekty-{ref.replace('/', '-')}-{time.time():.3f}", "caller": "studio",
                           "backend": backend, "n": 1, "usd": round(usd, 4), "items": [{"what": what, "usd": round(usd, 4)}],
                           "status": "ok"})

    def _brief(self, ref: str) -> str:
        prov = self.image(ref).with_suffix(".json")
        data = json.loads(prov.read_text(encoding="utf-8")) if prov.exists() else {}
        return data.get("prompt_sent") or data.get("prompt_original") or ""

    def _add_object(self, ref: str, doc: dict, rgb: Image.Image, png: bytes, cs: str, en: str, box: list[int],
                    by_name: bool) -> dict | None:
        """`by_name`: SAM hledá podle anglického názvu (rámeček od Clauda je nepřesný), jinak obtáhne rámeček operátora."""
        mask, score = self.segment(png, box_px(box, rgb.size), en if by_name else None)
        mask = mask.resize(rgb.size, Image.NEAREST).point(lambda v: 255 if v > 127 else 0)
        cover = float((np.asarray(mask) > 127).mean())
        if cover < MIN_COVER:
            return None
        oid = f"o{doc['next_id']}"
        doc["next_id"] += 1
        d = self.dir(ref)
        mask.save(d / f"maska-{oid}.png")
        cut_layer(rgb, mask).save(d / f"vrstva-{oid}.png")
        obj = {"id": oid, "nazev": cs, "en": en, "box": bbox_1000(mask), "plocha": round(cover, 4),
               "skore": score, "viditelny": True, "posun": [0, 0], "verze": [{"vrstva": f"vrstva-{oid}.png",
                                                                             "maska": f"maska-{oid}.png", "pokyn": None}]}
        doc["objects"].append(obj)
        return obj

    @staticmethod
    def find_usd(count: int = MAX_OBJECTS) -> float:
        return round(FIND_USD + SAM_USD * count, 4)

    def najit(self, ref: str) -> dict:
        """Claude pojmenuje objekty, SAM-3 ke každému masku; staré hledání se přepíše jen bez podkladu a změn."""
        path = self.image(ref)
        png = path.read_bytes()
        rgb = Image.open(BytesIO(png)).convert("RGB")
        found = self.find(png, self._brief(ref))
        self._cost(ref, "hledání objektů (Claude)", FIND_USD, "claude:objekty")
        with self._lock:
            old = self.load(ref)
            if old and (old.get("podklad") or any(len(o["verze"]) > 1 for o in old["objects"])):
                raise ObjektyError("obrázek už má vrstvy s podkladem nebo změnami; nové hledání by je zahodilo")
            d = self.dir(ref)
            d.mkdir(parents=True, exist_ok=True)
            doc = {"ref": ref, "size": list(rgb.size), "objects": [], "next_id": 1, "podklad": None, "ulohy": [],
                   "created": datetime.now().isoformat(timespec="seconds")}
            for item in found:
                self._add_object(ref, doc, rgb, png, item["cs"], item["en"], item["box"], True)
                self._cost(ref, f"maska objektu {item['cs']} (SAM-3)", SAM_USD, f"fal:{SAM_ENDPOINT}")
            if not doc["objects"]:
                raise ObjektyError("v obrázku jsem nenašel žádný objekt; přidejte ho rámečkem")
            self.save(ref, doc)
            return doc

    def pridat(self, ref: str, box: list[int], nazev: str) -> dict:
        """Objekt, který hledání minulo: operátor ho obtáhne rámečkem. Starý podklad pod ním objekt pořád má."""
        png = self.image(ref).read_bytes()
        rgb = Image.open(BytesIO(png)).convert("RGB")
        with self._lock:
            doc = self.load(ref) or {"ref": ref, "size": list(rgb.size), "objects": [], "next_id": 1, "podklad": None,
                                     "ulohy": [], "created": datetime.now().isoformat(timespec="seconds")}
            self.dir(ref).mkdir(parents=True, exist_ok=True)
            obj = self._add_object(ref, doc, rgb, png, nazev, nazev, box, False)
            self._cost(ref, f"maska objektu {nazev} (SAM-3)", SAM_USD, f"fal:{SAM_ENDPOINT}")
            if obj is None:
                raise ObjektyError("v rámečku se nenašel žádný objekt")
            if doc.get("podklad"):
                doc["podklad"]["zastaraly"] = True
            self.save(ref, doc)
            return doc

    def upravit(self, ref: str, oid: str, viditelny: bool | None, posun: list[int] | None) -> dict:
        with self._lock:
            doc = self._doc(ref)
            obj = self._obj(doc, oid)
            if viditelny is not None:
                obj["viditelny"] = viditelny
            if posun is not None:
                obj["posun"] = [int(posun[0]), int(posun[1])]
            self.save(ref, doc)
            return doc

    def _doc(self, ref: str) -> dict:
        doc = self.load(ref)
        if doc is None:
            raise LookupError("obrázek ještě nemá vrstvy; nejdřív Najít objekty")
        return doc

    @staticmethod
    def _obj(doc: dict, oid: str) -> dict:
        for o in doc["objects"]:
            if o["id"] == oid:
                return o
        raise LookupError(f"objekt {oid} neexistuje")

    # úlohy ve frontě: podklad a změna objektu jdou přes lokální FLUX pod zámkem GPU
    def enqueue(self, ref: str, op: str, **extra) -> str:
        with self._lock:
            doc = self._doc(ref)
            job_id = self.store.add_task(KIND, "studio", "flux-local", {"op": op, "ref": ref, **extra})
            doc["ulohy"].append({"job": job_id, "op": op, **extra})
            self.save(ref, doc)
        return job_id

    def zmena_usd(self, instruction: str) -> float:
        return round(SAM_USD + (TRANSLATE_USD if is_czech(instruction) else 0.0), 4)

    def run(self, job_id: str, r: dict) -> dict:
        ref = r["ref"]
        parent = self.image(ref)
        rgb = Image.open(parent).convert("RGB")
        doc = self._doc(ref)
        d = self.dir(ref)
        if r["op"] == "podklad":
            # Po jednom objektu odpředu dozadu, každý s vlastním rámečkem: jeden rámeček přes všechny objekty FLUX
            # nepochopil a maják nechal stát (měření 2026-11-04). Mezikroky mají vlastní složku `<job>-<k>`.
            objects = list(reversed(doc["objects"]))
            source, res, steps = parent, None, []
            for k, o in enumerate(objects, 1):
                pm = plate_mask([Image.open(d / o["verze"][0]["maska"])], rgb.size)
                mask_path = d / f"podklad-maska-{job_id}-{o['id']}.png"
                pm.save(mask_path)
                edit = EditSpec(action="remove", bbox=bbox_1000(pm, margin=0.02), instruction=f"the {o['en']}",
                                mask=str(mask_path))
                step_id = job_id if k == len(objects) else f"{job_id}-{k}"
                res = self.worker.process(step_id, self._request(ref, source, rgb, edit, "off"), time.time())
                source = Path(res["files"][0])
                steps.append(str(source))
            with self._lock:
                doc = self._doc(ref)
                doc["podklad"] = {"file": str(source), "job": job_id, "objekty": [o["id"] for o in objects[::-1]],
                                  "kroky": steps, "zastaraly": False}
                self.save(ref, doc)
            return {**res, "objekty": ref}
        if r["op"] == "zmena":
            obj = self._obj(doc, r["object"])
            current = Image.open(d / obj["verze"][-1]["maska"])
            area = bbox_1000(current, margin=0.06)
            edit = EditSpec(action="recolor", bbox=area, instruction=f"the {obj['en']}: {r['instruction']}")
            res = self.worker.process(job_id, self._request(ref, parent, rgb, edit, "auto"), time.time())
            out_png = Path(res["files"][0]).read_bytes()
            out = Image.open(BytesIO(out_png)).convert("RGB").resize(rgb.size, Image.LANCZOS)
            mask, score = self.segment(_png(out), box_px(area, rgb.size))
            self._cost(ref, f"maska změněného objektu {obj['nazev']} (SAM-3)", SAM_USD, f"fal:{SAM_ENDPOINT}")
            mask = mask.resize(rgb.size, Image.NEAREST).point(lambda v: 255 if v > 127 else 0)
            with self._lock:
                doc = self._doc(ref)
                obj = self._obj(doc, r["object"])
                k = len(obj["verze"]) + 1
                mask.save(d / f"maska-{obj['id']}-v{k}.png")
                cut_layer(out, mask).save(d / f"vrstva-{obj['id']}-v{k}.png")
                obj["verze"].append({"vrstva": f"vrstva-{obj['id']}-v{k}.png", "maska": f"maska-{obj['id']}-v{k}.png",
                                     "pokyn": r["instruction"], "job": job_id, "skore": score})
                obj["viditelny"] = True
                self.save(ref, doc)
            return {**res, "objekty": ref}
        raise ObjektyError(f"neznámá operace {r['op']!r}")

    @staticmethod
    def _request(ref: str, parent: Path, rgb: Image.Image, edit: EditSpec, translate: str) -> ImageRequest:
        w, h = rgb.size
        return ImageRequest(prompt=edit.instruction, backend="flux-local", size=f"{w // 16 * 16}x{h // 16 * 16}",
                            parent=ref, edit=edit, translate=translate, caller="studio-objekty",
                            refs=[Ref(path=str(parent), role="scene", source=f"verze {ref}")])

    # složení
    def layers(self, ref: str, doc: dict, only_visible: bool = True) -> list[tuple[dict, Image.Image]]:
        d = self.dir(ref)
        return [(o, Image.open(d / o["verze"][-1]["vrstva"]).convert("RGBA"))
                for o in doc["objects"] if o["viditelny"] or not only_visible]

    def base(self, ref: str, doc: dict) -> Image.Image:
        p = (doc.get("podklad") or {}).get("file")
        return Image.open(p if p else self.image(ref)).convert("RGB").resize(tuple(doc["size"]), Image.LANCZOS)

    def composed(self, ref: str) -> tuple[Image.Image, str, dict]:
        doc = self._doc(ref)
        base = self.base(ref, doc)
        layers = self.layers(ref, doc)
        img = compose(base, [(im, tuple(o["posun"])) for o, im in layers])
        svg = layers_svg(base, [(o["id"], o["nazev"], im, tuple(o["posun"])) for o, im in layers])
        return img, svg, doc

    def kontrola(self, ref: str) -> dict:
        """Podklad + všechny vrstvy na místě proti originálu: rozdíl má být kolem nuly."""
        doc = self._doc(ref)
        base = self.base(ref, doc)
        img = compose(base, [(im, (0, 0)) for _, im in self.layers(ref, doc, only_visible=False)])
        return check(Image.open(self.image(ref)), img)

    def public(self, ref: str, doc: dict | None) -> dict:
        if doc is None:
            return {"ref": ref, "objects": [], "podklad": None, "ulohy": [], "find_usd": self.find_usd()}
        jobs = []
        for u in doc["ulohy"][-10:]:
            job = self.store.get(u["job"]) or {}
            jobs.append({**u, "status": job.get("status"), "error": job.get("error")})
        base = f"/api/v2/jobs/{ref.replace('/', '/images/')}/objekty/soubor"
        objects = [{**o, "vrstva_url": f"{base}/{o['verze'][-1]['vrstva']}"} for o in doc["objects"]]
        podklad = doc.get("podklad")
        return {**doc, "objects": objects, "ulohy": jobs, "find_usd": self.find_usd(), "add_usd": SAM_USD,
                "podklad": {**podklad, "url": f"/api/v2/jobs/{Path(podklad['file']).parent.name}/images/0"} if podklad else None}


# -- API ----------------------------------------------------------------------------------------------------------

class FindIn(BaseModel):
    confirm_cost: bool = False


class AddIn(BaseModel):
    box: list[int]                  # [top, left, bottom, right] 0–1000
    nazev: str = Field(min_length=1, max_length=60)
    confirm_cost: bool = False

    @field_validator("box")
    @classmethod
    def _box(cls, v):
        return check_box(v)


class ObjectIn(BaseModel):
    viditelny: bool | None = None
    posun: list[int] | None = None  # [dx, dy] v px obrázku

    @field_validator("posun")
    @classmethod
    def _posun(cls, v):
        if v is not None and len(v) != 2:
            raise ValueError("posun = [dx, dy]")
        return v


class ChangeIn(BaseModel):
    instruction: str = Field(min_length=1, max_length=400)
    confirm_cost: bool = False


def register(app: FastAPI, ob: Objekty, store_upload: Callable[[bytes, str, str, dict], str]) -> None:
    """`store_upload(png, svg, title, origin)` uloží hotový obrázek s vrstvami do Knihovny a vrátí job id."""
    base = "/api/v2/jobs/{job_id}/images/{n}/objekty"

    def guard(fn):
        try:
            return fn()
        except LookupError as e:
            raise HTTPException(404, str(e)) from e
        except ObjektyError as e:
            raise HTTPException(400, str(e)) from e
        except BackendError as e:
            raise HTTPException(502, str(e)) from e

    def paid(usd: float, confirm: bool, what: str):
        if usd > 0 and not confirm:
            return JSONResponse(status_code=402, content={
                "detail": f"{what} je placené — nic nespuštěno. Pošlete znovu s confirm_cost=true.", "estimate_usd": usd})
        return None

    @app.get(base)
    def objekty_get(job_id: str, n: int):
        ref = f"{job_id}/{n}"
        return guard(lambda: ob.public(ref, ob.load(ref)))

    @app.post(base, status_code=201)
    def objekty_find(job_id: str, n: int, body: FindIn):
        """Najít objekty a hned zařadit dokreslení podkladu (lokální FLUX, 0 USD)."""
        ref = f"{job_id}/{n}"
        stop = paid(ob.find_usd(), body.confirm_cost, "Hledání objektů")
        if stop:
            return stop
        doc = guard(lambda: ob.najit(ref))
        ob.enqueue(ref, "podklad")
        return ob.public(ref, ob.load(ref) or doc)

    @app.post(base + "/pridat", status_code=201)
    def objekty_add(job_id: str, n: int, body: AddIn):
        ref = f"{job_id}/{n}"
        stop = paid(SAM_USD, body.confirm_cost, "Maska objektu")
        if stop:
            return stop
        return guard(lambda: ob.public(ref, ob.pridat(ref, body.box, body.nazev.strip())))

    @app.post(base + "/podklad", status_code=202)
    def objekty_plate(job_id: str, n: int):
        ref = f"{job_id}/{n}"
        return {"job_id": guard(lambda: ob.enqueue(ref, "podklad"))}

    @app.patch(base + "/{oid}")
    def objekty_edit(job_id: str, n: int, oid: str, body: ObjectIn):
        ref = f"{job_id}/{n}"
        return guard(lambda: ob.public(ref, ob.upravit(ref, oid, body.viditelny, body.posun)))

    @app.post(base + "/{oid}/zmenit", status_code=202)
    def objekty_change(job_id: str, n: int, oid: str, body: ChangeIn):
        ref = f"{job_id}/{n}"
        guard(lambda: ob._obj(ob._doc(ref), oid))
        stop = paid(ob.zmena_usd(body.instruction), body.confirm_cost, "Změna objektu")
        if stop:
            return stop
        return {"job_id": guard(lambda: ob.enqueue(ref, "zmena", object=oid, instruction=body.instruction.strip()))}

    @app.get(base + "/kontrola")
    def objekty_check(job_id: str, n: int):
        return guard(lambda: ob.kontrola(f"{job_id}/{n}"))

    @app.get(base + "/soubor/{name}")
    def objekty_file(job_id: str, n: int, name: str):
        if not re.fullmatch(r"(vrstva|maska)-o\d+(-v\d+)?\.png", name):
            raise HTTPException(404, "soubor neexistuje")
        p = guard(lambda: ob.dir(f"{job_id}/{n}")) / name
        if not p.exists():
            raise HTTPException(404, "soubor neexistuje")
        return FileResponse(p, media_type="image/png")

    @app.post(base + "/hotovo", status_code=201)
    def objekty_done(job_id: str, n: int):
        """Složený obrázek jako nová verze v Knihovně; vrstvy jdou s ním (VectorCraft, POHYB). Originál zůstane."""
        ref = f"{job_id}/{n}"
        img, svg, doc = guard(lambda: ob.composed(ref))
        if not doc.get("podklad"):
            raise HTTPException(409, "Podklad ještě není dokreslený, smazaný nebo posunutý objekt by nechal díru.")
        hidden = [o["nazev"] for o in doc["objects"] if not o["viditelny"]]
        moved = [o["nazev"] for o in doc["objects"] if o["viditelny"] and any(o["posun"])]
        changed = [o["nazev"] for o in doc["objects"] if len(o["verze"]) > 1]
        what = "; ".join(x for x in (f"bez: {', '.join(hidden)}" if hidden else "", f"posunuto: {', '.join(moved)}" if moved else "",
                                     f"změněno: {', '.join(changed)}" if changed else "") if x) or "ve vrstvách"
        new_id = store_upload(_png(img), svg, f"{ref} · {what}", {
            "objekty_of": ref, "objekty": [{k: o[k] for k in ("id", "nazev", "viditelny", "posun")} | {"verze": len(o["verze"])}
                                           for o in doc["objects"]], "podklad_job": doc["podklad"]["job"]})
        return {"ref": f"{new_id}/0"}
