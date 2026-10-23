"""Reference library ("Schránka předloh"): every reference image the operator
collects — Wikimedia Commons, Pinterest, the web, own files — stored once with
its origin, author and licence. Requests point at it with `Ref.ref_id`.

refs/library/<id>/image.png + meta.json. A licence is a note, it never blocks use
as a reference (NG-ROBOT decision 2026-09-02); images from Pinterest have
licence "neznámá — jen předloha".
"""
from __future__ import annotations

import json
import re
import secrets
import threading
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image

from engine.refs import MAX_REF_EDGE, sha256

UA = {"User-Agent": "GRAFIK-Engine/2 (https://github.com/cetej/GRAFIK)"}
ORIGINS = ("commons", "pinterest", "web", "upload")
PINTEREST_LICENSE = "neznámá — jen předloha"


class RefLibError(ValueError):
    pass


def normalize_png(data: bytes) -> tuple[bytes, tuple[int, int]]:
    try:
        img = Image.open(BytesIO(data))
        img.load()
    except Exception as e:  # PIL raises many types for broken input
        raise RefLibError(f"není to čitelný obrázek ({e})") from e
    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    if max(img.size) > MAX_REF_EDGE:
        img.thumbnail((MAX_REF_EDGE, MAX_REF_EDGE), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), img.size


def origin_of(url: str | None) -> str:
    host = urlparse(url or "").netloc
    if "pinimg.com" in host or "pinterest." in host:
        return "pinterest"
    if "wikimedia.org" in host:
        return "commons"
    return "web" if url else "upload"


def fetch(url: str) -> bytes:
    """Download an image; a Pinterest pin page is resolved to its og:image."""
    try:
        r = httpx.get(url, headers=UA, timeout=60, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise RefLibError(f"stažení {url} selhalo: {e}") from e
    if r.headers.get("content-type", "").startswith("text/html"):
        m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', r.text) \
            or re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', r.text)
        if not m:
            raise RefLibError("stránka neobsahuje obrázek (og:image); pošlete přímo adresu obrázku")
        return fetch(m.group(1).replace("&amp;", "&"))
    return r.content


class RefLibrary:
    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.Lock()

    def _meta_path(self, ref_id: str) -> Path:
        if not re.fullmatch(r"[\w\-]+", ref_id):
            raise RefLibError("neplatné id předlohy")
        return self.root / ref_id / "meta.json"

    def get(self, ref_id: str) -> dict | None:
        p = self._meta_path(ref_id)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def image_path(self, ref_id: str) -> Path | None:
        return self.root / ref_id / "image.png" if self.get(ref_id) else None

    def list(self, origin: str | None = None) -> list[dict]:
        if not self.root.exists():
            return []
        items = [json.loads(p.read_text(encoding="utf-8")) for p in self.root.glob("*/meta.json")]
        if origin:
            items = [i for i in items if i["origin"] == origin]
        return sorted(items, key=lambda i: i["added"], reverse=True)

    def add(self, data: bytes, *, origin: str, title: str = "", source_url: str | None = None,
            page_url: str | None = None, author: str | None = None, license: str | None = None,
            license_url: str | None = None) -> dict:
        if origin not in ORIGINS:
            raise RefLibError(f"neznámý původ {origin!r}")
        png, (w, h) = normalize_png(data)
        digest = sha256(png)
        with self._lock:
            for existing in self.list():
                if existing["sha256"] == digest:
                    return existing
            ref_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)
            (self.root / ref_id).mkdir(parents=True)
            (self.root / ref_id / "image.png").write_bytes(png)
            meta = {
                "id": ref_id, "origin": origin, "title": title or (page_url or source_url or "předloha"),
                "source_url": source_url, "page_url": page_url, "author": author,
                "license": license or (PINTEREST_LICENSE if origin == "pinterest" else None),
                "license_url": license_url, "sha256": digest, "width": w, "height": h,
                "added": datetime.now().isoformat(timespec="seconds"), "seen": False,
            }
            self._meta_path(ref_id).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            return meta

    def add_url(self, url: str, **meta) -> dict:
        origin = meta.pop("origin", None) or origin_of(meta.get("page_url") or url)
        return self.add(fetch(url), origin=origin, source_url=url, **meta)

    def mark_seen(self, ref_id: str) -> dict:
        meta = self.get(ref_id)
        if meta is None:
            raise RefLibError("předloha neexistuje")
        meta["seen"] = True
        self._meta_path(ref_id).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta
