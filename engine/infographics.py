"""Infographics (G5): Czech labels, facts and a vector schema over a generated image.

Pattern approved by the operator 2026-10-23 (models/flux3-klein/overlay_quinq3.html): about five
labels with thin leader lines outside the object, three facts, a vector section drawing, one dark
background, a footer with sources and the AI label. Text in the image never comes from the model.

library/infographics/<id>/info.json   the document (what the studio editor edits)
library/infographics/<id>/exports/    PNG / SVG / PDF + a provenance JSON per export
schemas/<slug>.svg                     reusable vector schemas ("Ze šablony schémat")

The studio renders the document to SVG (one renderer, the preview is the export); the Engine
stores it, cleans it and rasterises it with headless Chromium (Playwright) for PNG and PDF.
"""
from __future__ import annotations

import json
import re
import secrets
import shutil
import threading
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

SVG_NS = "http://www.w3.org/2000/svg"
XLINK = "{http://www.w3.org/1999/xlink}href"
FORMATS = ("png", "svg", "pdf")
SIZES = {"1280x990": (1280, 990), "1920x1080": (1920, 1080), "1080x1350": (1080, 1350)}
BACKEND_NAMES = {"flux-local": "FLUX 3 Klein", "nb-pro": "Nano Banana Pro",
                 "fal:fal-ai/nano-banana-pro": "Nano Banana Pro", "fal:fal-ai/flux-2-pro": "FLUX.2 pro",
                 "fal:fal-ai/flux-pro/v1.1": "FLUX 1.1 pro", "fal:fal-ai/flux/krea": "FLUX Krea"}

# embedded raster images only (an SVG data URI could carry its own scripts)
RASTER_DATA = ("data:image/png", "data:image/jpeg", "data:image/webp")
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


class InfoError(ValueError):
    pass


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
    model = BACKEND_NAMES.get(prov.get("backend"), prov.get("model") or prov.get("backend") or "AI")
    by_ref = any(r.get("sent_as") == "image" for r in prov.get("refs", []))
    return f"Ilustrace: {model} (AI){' podle předlohy' if by_ref else ''}, schéma a popisky redakčně."


def new_doc(base: str, title: str, prov: dict | None) -> dict:
    return {
        "id": datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2),
        "base": base, "title": title, "subtitle": "", "template": "dark", "size": "1280x990", "accent": "#dcb062",
        "labels": [], "facts": [], "schema": None, "sources": "", "ai_note": ai_note(prov),
        "reviewed_by": None, "reviewed_at": None,
        "created": datetime.now().isoformat(timespec="seconds"), "updated": datetime.now().isoformat(timespec="seconds"),
    }


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
            return page.pdf(width=f"{width}px", height=f"{height}px", print_background=True,
                            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        finally:
            browser.close()


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

    def create(self, base: str, title: str, prov: dict | None) -> dict:
        doc = new_doc(base, title, prov)
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
        if doc.get("size") not in SIZES:
            raise InfoError(f"neznámý formát {doc.get('size')!r}")
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
        w, h = SIZES[doc["size"]]
        svg = clean_svg(svg, allow_data_images=True)
        # the footer is wrapped into several <text> lines: compare the bare text without tags and spaces
        bare = re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", svg).replace("&amp;", "&"))
        if re.sub(r"\s+", "", doc["ai_note"]) not in bare:
            raise InfoError("v exportu chybí označení AI v patičce")
        data = svg.encode("utf-8") if fmt == "svg" else rasterize(svg, w, h, fmt)
        ex = self._dir(info_id) / "exports"
        ex.mkdir(parents=True, exist_ok=True)
        name = f"{datetime.now():%Y%m%d-%H%M%S}.{fmt}"
        (ex / name).write_bytes(data)
        prov = {"infographic": info_id, "file": name, "format": fmt, "size": doc["size"], "base": doc["base"],
                "base_provenance": base_prov, "title": doc["title"], "labels": doc["labels"], "facts": doc["facts"],
                "sources": doc["sources"], "ai_note": doc["ai_note"], "ai_generated": True,
                "text_by": "redakce (editor GRAFIK)", "reviewed_by": doc.get("reviewed_by"),
                "created": datetime.now().isoformat(timespec="seconds")}
        (ex / f"{name}.json").write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"file": name, "bytes": len(data)}

    def export_path(self, info_id: str, name: str) -> Path | None:
        p = self._dir(info_id) / "exports" / name
        return p if re.fullmatch(r"[\d\-]+\.(png|svg|pdf)", name) and p.exists() else None

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
