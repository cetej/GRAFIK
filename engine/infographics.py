"""Infographics (G5): Czech labels, facts and a vector schema over a generated image.

Pattern approved by the operator 2026-10-23 (models/flux3-klein/overlay_quinq3.html): about five
labels with thin leader lines outside the object, three facts, a vector section drawing, one dark
background, a footer with sources and the AI label. Text in the image never comes from the model.

library/infographics/<id>/info.json   the document (what the studio editor edits)
library/infographics/<id>/exports/    PNG / SVG / PDF + a provenance JSON per export (*-rucni-*: from a manual edit)
library/infographics/<id>/vectorcraft/ copies opened in the VectorCraft window, the operator's edits live here
schemas/<slug>.svg                     reusable vector schemas ("Ze šablony schémat")

The studio renders the document to SVG (one renderer, the preview is the export); the Engine
stores it, cleans it and rasterises it with headless Chromium (Playwright) for PNG and PDF.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from PIL import Image

from ngm_shared.heavy_lock import LOCK_PATH
from ngm_shared.textlayer.vc_client import VectorCraft

SVG_NS = "http://www.w3.org/2000/svg"
XLINK = "{http://www.w3.org/1999/xlink}href"
FORMATS = ("png", "svg", "pdf")
MANUAL_SOURCES = (".svg", ".svgz", ".vectorcraft", ".ai")   # what VectorCraft saves a document as (an exported PNG is not one)
MANUAL_LOCK_WAIT_S = 120.0   # the request waits for a running job, a FLUX image takes 40-85 s
SIZES ={"1280x990": (1280, 990), "1920x1080": (1920, 1080), "1080x1350": (1080, 1350)}
LAYOUTS = ("klasika", "pruh")   # docs/infografiky-zasady.md
BACKEND_NAMES = {"flux-local": "FLUX 3 Klein", "nb-pro": "Nano Banana Pro",
                 "fal:fal-ai/nano-banana-pro": "Nano Banana Pro", "fal:fal-ai/flux-2-pro": "FLUX.2 pro",
                 "fal:fal-ai/flux-pro/v1.1": "FLUX 1.1 pro", "fal:fal-ai/flux/krea": "FLUX Krea"}

# embedded raster images only (an SVG data URI could carry its own scripts)
RASTER_DATA = ("data:image/png", "data:image/jpeg", "data:image/webp")
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


class InfoError(ValueError):
    pass


class VectorCraftEdited(Exception):
    """A manual edit exists: the operator decides whether to open it or a new copy of the document."""

    def __init__(self, file: str):
        super().__init__(file)
        self.file = file


def clean_svg(svg: str, allow_data_images: bool = False) -> str:
    """Drop scripts, foreignObject, on* handlers and external links from an SVG (schema upload,
    export). Embedded raster images (data:image/...) only where the caller allows them."""
    try:
        root = ET.fromstring(svg.strip())
    except ET.ParseError as e:
        raise InfoError(f"SVG nejde přečíst ({e})") from e
    if root.tag not in (f"{{{SVG_NS}}}svg", "svg"):
        raise InfoError("to není SVG")
    for parent in list(root.iter()):
        for child in list(parent):
            tag = child.tag.rsplit("}", 1)[-1]
            if tag in ("script", "foreignObject", "iframe"):
                parent.remove(child)
    for el in root.iter():
        for k in list(el.attrib):
            v = el.attrib[k].strip()
            if k.lower().startswith("on"):
                del el.attrib[k]
            elif k in ("href", XLINK) and not (v.startswith("#") or (allow_data_images and v.startswith(RASTER_DATA))):
                del el.attrib[k]
    return ET.tostring(root, encoding="unicode")


def ai_note(prov: dict | None) -> str:
    """Footer line required by the FLUX licence § 2e and the operator's rule: AI image, human text."""
    if not prov:
        return "Ilustrace: AI, schéma a popisky redakčně."
    if prov.get("render"):
        return f"Model a render: {prov['render']}, bez AI; schéma a popisky redakčně."
    model = BACKEND_NAMES.get(prov.get("backend"), prov.get("model") or prov.get("backend") or "AI")
    by_ref = any(r.get("sent_as") == "image" for r in prov.get("refs", []))
    return f"Ilustrace: {model} (AI){' podle předlohy' if by_ref else ''}, schéma a popisky redakčně."


def canvas_size(size: str | None) -> tuple[int, int] | None:
    """A preset or a picture's own format, "WxH"."""
    m = re.fullmatch(r"([1-9]\d{2,3})x([1-9]\d{2,3})", size or "")
    return (int(m[1]), int(m[2])) if m else None


def fitting_size(iw: int, ih: int) -> str:
    """A canvas that keeps the whole picture: the renderer fills the canvas and crops what does not fit (a 2:3
    poster in 16:9, operator 2026-11-01). A preset within 3 % of the shape, else the picture's own, 1080 to 1920 wide."""
    for name, (w, h) in SIZES.items():
        if abs(iw / ih - w / h) <= 0.03 * w / h:
            return name
    w = max(1080, min(iw, 1920))
    size = f"{w}x{round(w * ih / iw)}"
    return size if canvas_size(size) else "1920x1080"


def new_doc(base: str, title: str, prov: dict | None, size: str = "1920x1080") -> dict:
    return {
        "id": datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2),
        "base": base, "title": title, "subtitle": "", "template": "dark", "layout": "pruh", "size": size,
        "accent": "#dcb062",
        "labels": [], "facts": [], "schema": None, "sources": "", "ai_note": ai_note(prov),
        "reviewed_by": None, "reviewed_at": None,
        "created": datetime.now().isoformat(timespec="seconds"), "updated": datetime.now().isoformat(timespec="seconds"),
    }


def for_vectorcraft(svg: str) -> str:
    """Copy of a cleaned SVG for the window app. VectorCraft ignores font-stretch and reads the weight only
    from a family name, so Bahnschrift semi-condensed must be named in full on every text (measured
    2026-10-31 on the kvinquerema: without it the type runs 15 % wider than the preview, DECISIONS)."""
    root = ET.fromstring(svg)

    def walk(el: ET.Element, family: str, stretch: str, weight: str) -> None:
        family, stretch, weight = el.get("font-family", family), el.get("font-stretch", stretch), el.get("font-weight", weight)
        if el.tag.rsplit("}", 1)[-1] in ("text", "tspan") and family.startswith("Bahnschrift") and stretch == "semi-condensed":
            el.set("font-family", "Bahnschrift Bold SemiCondensed" if weight == "700" else "Bahnschrift SemiCondensed")
        for child in el:
            walk(child, family, stretch, weight)

    walk(root, "", "", "")
    return ET.tostring(root, encoding="unicode")


def open_in_window(app: Path, path: Path) -> None:
    """Detached (like NG-ROBOT ngvector/open): the window outlives an Engine restart."""
    flags = subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0
    subprocess.Popen([str(app), str(path)], creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def rasterize(svg: str, width: int, height: int, fmt: str) -> bytes:
    """PNG or PDF from an SVG via headless Chromium; same engine as the studio preview."""
    from playwright.sync_api import sync_playwright
    html = f'<!doctype html><html><body style="margin:0;background:#fff">{svg}</body></html>'
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_content(html, wait_until="load")
            if fmt == "png":
                return page.screenshot(clip={"x": 0, "y": 0, "width": width, "height": height})
            # page_ranges: an inline svg overflows the page by its baseline gap, Chromium then adds a blank second page
            return page.pdf(width=f"{width}px", height=f"{height}px", print_background=True, page_ranges="1",
                            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        finally:
            browser.close()


def vc_state(d: Path) -> tuple[list[dict], list[Path]]:
    """Copies Engine wrote into folder d ({file, sha256}), and files that are not what Engine wrote: saved over in
    VectorCraft or saved next to them (Save As). Those are manual edits, newest first."""
    state = d / "copies.json"
    copies = json.loads(state.read_text(encoding="utf-8")) if state.exists() else []
    known = {c["file"]: c["sha256"] for c in copies}
    files = [f for f in d.iterdir() if f.is_file() and f != state] if d.exists() else []
    edited = [f for f in files if known.get(f.name) != _sha256(f)]
    return copies, sorted(edited, key=lambda f: f.stat().st_mtime, reverse=True)


def vc_copy(d: Path, make, mode: str | None = None) -> dict:
    """The file to open in the window app. Nothing here ever overwrites a file: a manual edit stays as it is, new
    content gets a new copy, unchanged content reopens its untouched copy. make() gives the bytes of the copy."""
    if mode not in (None, "edited", "new"):
        raise InfoError(f"neznámý způsob otevření {mode!r}")
    copies, edited = vc_state(d)
    if mode == "edited":
        if not edited:
            raise InfoError("ruční úprava neexistuje")
        return {"path": edited[0], "file": edited[0].name, "created": False}
    if edited and mode is None:
        raise VectorCraftEdited(edited[0].name)
    data = make()
    sha = hashlib.sha256(data).hexdigest()
    for c in reversed(copies):
        if c["sha256"] == sha and (d / c["file"]).exists() and d / c["file"] not in edited:
            return {"path": d / c["file"], "file": c["file"], "created": False}
    d.mkdir(parents=True, exist_ok=True)
    name = f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}.svg"
    (d / name).write_bytes(data)
    (d / "copies.json").write_text(json.dumps([*copies, {"file": name, "sha256": sha}], indent=2), encoding="utf-8")
    return {"path": d / name, "file": name, "created": True}


def _clean_with_note(svg: str, doc: dict) -> str:
    svg = clean_svg(svg, allow_data_images=True)
    # the footer is wrapped into several <text> lines: compare the bare text without tags and spaces
    bare = re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", svg).replace("&amp;", "&"))
    if re.sub(r"\s+", "", doc["ai_note"]) not in bare:
        raise InfoError("v exportu chybí označení AI v patičce")
    return svg


def _canvas_texts(tree: dict) -> list[str]:
    """Texts the exported PNG shows, back to front (wrapped lines stay in reading order). Hidden text and text
    off the first artboard do not count: VectorCraft's SVG export keeps the latter, measured 2026-10-31."""
    a = tree["artboards"][0]

    def on_canvas(b: dict) -> bool:
        return (b["x"] >= a["x"] - 1 and b["y"] >= a["y"] - 1 and b["x"] + b["width"] <= a["x"] + a["width"] + 1
                and b["y"] + b["height"] <= a["y"] + a["height"] + 1)

    def walk(items: list[dict]):
        for it in reversed(items):
            if it.get("visible", True):
                if it.get("kind") == "Type" and on_canvas(it["bounds"]):
                    yield it["text"]
                yield from walk(it.get("children", []))

    return list(walk(tree["layers"]))


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class InfographicStore:
    def __init__(self, root: Path, schemas_dir: Path):
        self.root = root
        self.schemas_dir = schemas_dir
        self._lock = threading.Lock()

    def _dir(self, info_id: str) -> Path:
        if not re.fullmatch(r"[\w\-]+", info_id or ""):
            raise InfoError("neplatné id infografiky")
        return self.root / info_id

    def get(self, info_id: str) -> dict | None:
        p = self._dir(info_id) / "info.json"
        if not p.exists():
            return None
        doc = json.loads(p.read_text(encoding="utf-8"))
        ex = self._dir(info_id) / "exports"
        doc["exports"] = sorted((f.name for f in ex.iterdir() if f.suffix[1:] in FORMATS), reverse=True) if ex.exists() else []
        return doc

    def list(self) -> list[dict]:
        if not self.root.exists():
            return []
        docs = [self.get(p.parent.name) for p in self.root.glob("*/info.json")]
        return sorted((d for d in docs if d), key=lambda d: d["updated"], reverse=True)

    def create(self, base: str, title: str, prov: dict | None, size: str = "1920x1080") -> dict:
        doc = new_doc(base, title, prov, size)
        return self.save(doc["id"], doc, new=True)

    def save(self, info_id: str, data: dict, new: bool = False) -> dict:
        d = self._dir(info_id)
        old = self.get(info_id)
        if old is None and not new:
            raise InfoError("infografika neexistuje")
        doc = {**(old or {}), **{k: v for k, v in data.items() if k not in ("id", "exports", "created", "ai_note")}}
        doc["id"] = info_id
        doc["ai_note"] = (old or data)["ai_note"]  # from the base image's provenance, never edited away
        doc["created"] = (old or data)["created"]
        if canvas_size(doc.get("size")) is None:
            raise InfoError(f"neznámý formát {doc.get('size')!r}")
        doc.setdefault("layout", "klasika")   # documents from before the bar layout keep their look
        if doc["layout"] not in LAYOUTS:
            raise InfoError(f"neznámé rozvržení {doc['layout']!r}")
        if doc.get("schema") and doc["schema"].get("svg"):
            # a schema may hold a raster picture too (e.g. a cross-section render next to the main image)
            doc["schema"] = {**doc["schema"], "svg": clean_svg(doc["schema"]["svg"], allow_data_images=True)}
        doc["updated"] = datetime.now().isoformat(timespec="seconds")
        doc.pop("exports", None)
        with self._lock:
            d.mkdir(parents=True, exist_ok=True)
            (d / "info.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.get(info_id)

    def delete(self, info_id: str) -> str:
        d = self._dir(info_id)
        if not d.exists():
            raise InfoError("infografika neexistuje")
        dest = self.root / ".trash" / f"{datetime.now():%Y%m%d-%H%M%S}-{info_id}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(d), str(dest))
        return str(dest)

    def export(self, info_id: str, svg: str, fmt: str, base_prov: dict | None) -> dict:
        doc = self.get(info_id)
        if doc is None:
            raise InfoError("infografika neexistuje")
        if fmt not in FORMATS:
            raise InfoError(f"formát {fmt!r}: jen {', '.join(FORMATS)}")
        w, h = canvas_size(doc["size"])
        svg = _clean_with_note(svg, doc)
        data = svg.encode("utf-8") if fmt == "svg" else rasterize(svg, w, h, fmt)
        ex = self._dir(info_id) / "exports"
        ex.mkdir(parents=True, exist_ok=True)
        name = f"{datetime.now():%Y%m%d-%H%M%S}.{fmt}"
        (ex / name).write_bytes(data)
        prov = {"infographic": info_id, "file": name, "format": fmt, "size": doc["size"], "base": doc["base"],
                "base_provenance": base_prov, "title": doc["title"], "labels": doc["labels"], "facts": doc["facts"],
                "sources": doc["sources"], "ai_note": doc["ai_note"], "ai_generated": not (base_prov or {}).get("render"),
                "text_by": "redakce (editor GRAFIK)", "reviewed_by": doc.get("reviewed_by"),
                "created": datetime.now().isoformat(timespec="seconds")}
        (ex / f"{name}.json").write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"file": name, "bytes": len(data)}

    def export_path(self, info_id: str, name: str) -> Path | None:
        p = self._dir(info_id) / "exports" / name
        return p if re.fullmatch(r"[\w\-]+\.(png|svg|pdf)", name) and p.exists() else None

    # -- copies for the VectorCraft window ----------------------------------
    def _vc_state(self, info_id: str) -> tuple[Path, list[dict], list[Path]]:
        d = self._dir(info_id) / "vectorcraft"
        return (d, *vc_state(d))

    def vectorcraft_edits(self, info_id: str) -> list[dict]:
        taken = {}
        for p in sorted((self._dir(info_id) / "exports").glob("*-rucni-*.png.json")):
            taken[json.loads(p.read_text(encoding="utf-8"))["manual_edit"]["sha256"]] = p.name.removesuffix(".json")
        return [{"file": f.name, "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
                 "can_export": f.suffix.lower() in MANUAL_SOURCES, "exported": taken.get(_sha256(f))}
                for f in self._vc_state(info_id)[2]]

    def vectorcraft_export(self, info_id: str, file: str | None, base_prov: dict | None, lock_path: Path = LOCK_PATH) -> dict:
        """Takes over a manual edit: new PNG, PDF and SVG among the exports, made by VectorCraft itself so they
        look like the window. The source is only opened, never saved, and every export gets new files. The texts
        come from the file, not from the document: the editor's labels and its review do not describe the edit."""
        doc = self.get(info_id)
        if doc is None:
            raise InfoError("infografika neexistuje")
        edited = [f for f in self._vc_state(info_id)[2] if f.suffix.lower() in MANUAL_SOURCES]
        if not edited:
            raise InfoError("ruční úprava neexistuje: nejdřív ji ve VectorCraftu uložte (Ctrl+S)")
        src = edited[0] if file is None else next((f for f in edited if f.name == file), None)
        if src is None:
            raise InfoError(f"{file} není ruční úprava této infografiky")
        sha = _sha256(src)
        with tempfile.TemporaryDirectory(prefix="grafik-rucni-") as tmp:
            out = Path(tmp)
            with VectorCraft(lock_owner="grafik-infografiky", caller=f"infografika {info_id}",
                             lock_wait_s=MANUAL_LOCK_WAIT_S, lock_path=lock_path) as vc:
                opened = vc.tool("open_file", path=str(src))
                if opened.get("missingLinks"):
                    raise InfoError(f"v úpravě chybí propojené soubory: {', '.join(map(str, opened['missingLinks']))}")
                texts = _canvas_texts(vc.tool("inspect_document"))
                if re.sub(r"\s+", "", doc["ai_note"]) not in re.sub(r"\s+", "", "".join(texts)):
                    raise InfoError(f"V ruční úpravě chybí na plátně označení AI v patičce. Musí zůstat viditelná věta „{doc['ai_note']}“. Nic se neuložilo.")
                vc.tool("export", path=str(out / "e.png"))
                vc.tool("export", path=str(out / "e.pdf"))
                vc.tool("export", path=str(out / "e.svg"), outlineText=True)   # same look without the fonts, as NG-ROBOT
            if _sha256(src) != sha:
                raise InfoError(f"{src.name} se během převzetí změnil, zkuste to znovu")
            for fmt in FORMATS:
                if not (out / f"e.{fmt}").is_file() or (out / f"e.{fmt}").stat().st_size == 0:
                    raise InfoError(f"VectorCraft nevytvořil {fmt.upper()}")
            with Image.open(out / "e.png") as im:
                size = f"{im.width}x{im.height}"
            svg = clean_svg((out / "e.svg").read_text(encoding="utf-8"), allow_data_images=True)
            ex = self._dir(info_id) / "exports"
            ex.mkdir(parents=True, exist_ok=True)
            stem = f"{datetime.now():%Y%m%d-%H%M%S}-rucni-{secrets.token_hex(2)}"
            (ex / f"{stem}.svg").write_text(svg, encoding="utf-8")
            for fmt in ("pdf", "png"):
                shutil.move(str(out / f"e.{fmt}"), ex / f"{stem}.{fmt}")
        now = datetime.now().isoformat(timespec="seconds")
        files = []
        for fmt in FORMATS:
            name = f"{stem}.{fmt}"
            prov = {"infographic": info_id, "file": name, "format": fmt, "size": size, "base": doc["base"],
                    "base_provenance": base_prov, "title": doc["title"], "sources": doc["sources"],
                    "ai_note": doc["ai_note"], "ai_note_checked": True, "ai_generated": not (base_prov or {}).get("render"),
                    "text_by": "redakce (ruční úprava ve VectorCraftu)",
                    "texts": texts,
                    "manual_edit": {"file": src.name, "sha256": sha,
                                    "modified": datetime.fromtimestamp(src.stat().st_mtime).isoformat(timespec="seconds"),
                                    "vectorcraft": vc.server.get("version"), "warnings": opened.get("warnings", [])},
                    "reviewed_by": None, "document_reviewed_by": doc.get("reviewed_by"), "created": now}
            (ex / f"{name}.json").write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
            files.append({"file": name, "format": fmt, "bytes": (ex / name).stat().st_size})
        return {"source": src.name, "files": files, "warnings": opened.get("warnings", [])}

    def vectorcraft_file(self, info_id: str, svg: str, mode: str | None = None) -> dict:
        doc = self.get(info_id)
        if doc is None:
            raise InfoError("infografika neexistuje")
        with self._lock:
            return vc_copy(self._dir(info_id) / "vectorcraft",
                           lambda: for_vectorcraft(_clean_with_note(svg, doc)).encode("utf-8"), mode)

    # -- schema templates -------------------------------------------------
    def schemas(self) -> list[dict]:
        if not self.schemas_dir.exists():
            return []
        return [{"slug": p.stem, "title": _schema_title(p), "svg": p.read_text(encoding="utf-8")}
                for p in sorted(self.schemas_dir.glob("*.svg"))]

    def save_schema(self, title: str, svg: str) -> dict:
        from engine.styles import slugify
        slug = slugify(title)
        clean = clean_svg(svg)
        root = ET.fromstring(clean)
        t = ET.Element(f"{{{SVG_NS}}}title")
        t.text = title
        for old in root.findall(f"{{{SVG_NS}}}title"):
            root.remove(old)
        root.insert(0, t)
        self.schemas_dir.mkdir(parents=True, exist_ok=True)
        (self.schemas_dir / f"{slug}.svg").write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
        return {"slug": slug, "title": title, "svg": ET.tostring(root, encoding="unicode")}


def _schema_title(p: Path) -> str:
    m = re.search(r"<title>(.*?)</title>", p.read_text(encoding="utf-8"), re.S)
    return m.group(1).strip() if m else p.stem
