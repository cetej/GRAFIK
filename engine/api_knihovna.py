"""Characters, places and props of the shared library (KNIHOVNA, phase 4) as image references.

`GET /api/v2/knihovna` lists the items with their images, the main one first (`ngm_shared.knihovna.images`,
the same order as KLAPKA). `GET /api/v2/knihovna/<kind>/<slug>/<file>` serves an image (`?w=` thumbnail,
cached in run/, nothing is written to KNIHOVNA). A request points at an image with
`Ref.knihovna = "<kind>/<slug>"` (the main image) or `"<kind>/<slug>/<file>"`; `resolve()` turns it into
the file's path and its origin, and the provenance keeps the full `<kind>/<slug>/<file>`.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from PIL import Image

from ngm_shared import knihovna

KINDS = ("character", "environment", "prop")
# The role an image goes in as unless the studio changes it; a prop's white 3D views carry its shape.
ROLE = {"character": "subject", "environment": "scene", "prop": "subject"}
MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def resolve(base: Path, value: str) -> dict:
    """`<kind>/<slug>[/<file>]` -> {"knihovna": "<kind>/<slug>/<file>", "path": Path, "puvod": dict}.

    KnihovnaError for a malformed value, LookupError when the item or the image is not there. Only an
    image `images()` lists can be named, so a file outside the item cannot."""
    kind, _, rest = value.strip().partition("/")
    slug, _, file = rest.partition("/")
    if kind not in KINDS:
        raise knihovna.KnihovnaError(
            f"předloha z knihovny {value!r}: druh musí být character, environment nebo prop")
    images = knihovna.images(kind, slug, base)
    img = next((i for i in images if i["file"] == file), None) if file else (images[0] if images else None)
    if img is None:
        raise LookupError(f"{kind}/{slug}: obrázek {file} v knihovně není" if file
                          else f"{kind}/{slug} v knihovně není nebo nemá obrázek")
    try:
        puvod = knihovna.read_puvod(img["path"]) or {}
    except ValueError:              # a hand-edited <file>.puvod.json that is not JSON
        puvod = {}
    return {"knihovna": f"{kind}/{slug}/{img['file']}", "path": img["path"], "puvod": puvod}


def _about(kind: str, card: dict) -> str:
    return str((card.get("description") if kind == "prop" else card.get("anchors")) or "").strip()


def register(app: FastAPI, settings) -> None:
    @app.get("/api/v2/knihovna")
    def knihovna_items(kind: str | None = None):
        if kind is not None and kind not in KINDS:
            raise HTTPException(400, f"druh {kind!r}: character, environment nebo prop")
        items, problems = [], []
        for k in (kind,) if kind else KINDS:
            for slug in knihovna.slugs(k, settings.knihovna_dir):
                try:
                    card = knihovna.read(k, slug, settings.knihovna_dir)
                    images = knihovna.images(k, slug, settings.knihovna_dir)
                except knihovna.KnihovnaError as e:     # one broken card does not hide the others
                    problems.append(str(e))
                    continue
                if card is None:                        # removed in the meantime
                    continue
                # a new board changes the item as much as an edited card (the studio sorts by this)
                stamps = [p.stat().st_mtime for p in [knihovna.card_path(k, slug, settings.knihovna_dir)]
                          + [i["path"] for i in images] if p.exists()]
                items.append({
                    "kind": k, "slug": slug, "name": str(card.get("name") or slug), "about": _about(k, card),
                    "updated": datetime.fromtimestamp(max(stamps, default=0)).isoformat(timespec="seconds"),
                    "images": [{"file": i["file"], "label": i["label"], "primary": i["primary"],
                                "role": "geometry" if i["file"].startswith("model/views/") else ROLE[k],
                                "knihovna": f"{k}/{slug}/{i['file']}",
                                "url": f"/api/v2/knihovna/{k}/{slug}/{i['file']}"} for i in images]})
        return {"items": items, "problems": problems}

    @app.get("/api/v2/knihovna/{kind}/{slug}/{file:path}")
    def knihovna_image(kind: str, slug: str, file: str, w: int | None = None):
        try:
            path = resolve(settings.knihovna_dir, f"{kind}/{slug}/{file}")["path"]
        except knihovna.KnihovnaError as e:
            raise HTTPException(400, str(e)) from e
        except LookupError as e:
            raise HTTPException(404, str(e)) from e
        if not w:
            return FileResponse(path, media_type=MEDIA[path.suffix.lower()])
        w = max(64, min(w, 1024))
        st = path.stat()
        key = hashlib.sha1(f"{path}|{st.st_mtime_ns}|{st.st_size}|{w}".encode()).hexdigest()[:20]
        thumb = settings.run_dir / "knihovna-thumbs" / f"{key}.jpg"
        if not thumb.exists():
            thumb.parent.mkdir(parents=True, exist_ok=True)
            img = Image.open(path).convert("RGB")
            img.thumbnail((w, w * 4))
            tmp = thumb.with_suffix(".tmp")
            img.save(tmp, "JPEG", quality=85)
            tmp.replace(thumb)
        return FileResponse(thumb, media_type="image/jpeg")
