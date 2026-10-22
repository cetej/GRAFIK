"""Load a reference image from b64 / local path / URL into normalized PNG bytes."""
from __future__ import annotations

import base64
import hashlib
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from engine.models import Ref

MAX_REF_EDGE = 2048


class RefError(ValueError):
    pass


def load_ref_png(ref: Ref) -> bytes:
    if ref.b64:
        raw = ref.b64.split(",", 1)[1] if ref.b64.startswith("data:") else ref.b64
        try:
            data = base64.b64decode(raw, validate=True)
        except ValueError as e:
            raise RefError(f"předloha: neplatné base64 ({e})") from e
    elif ref.path:
        p = Path(ref.path)
        if not p.is_file():
            raise RefError(f"předloha: soubor neexistuje: {ref.path}")
        data = p.read_bytes()
    elif ref.url:
        try:
            r = httpx.get(ref.url, timeout=60, follow_redirects=True,
                          headers={"User-Agent": "GRAFIK-Engine/2 (local image service)"})
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise RefError(f"předloha: stažení {ref.url} selhalo: {e}") from e
        data = r.content
    else:
        raise RefError("předloha bez obrázku")
    try:
        img = Image.open(BytesIO(data))
        img.load()
    except Exception as e:  # PIL raises many types for broken input
        raise RefError(f"předloha není čitelný obrázek ({e})") from e
    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    if max(img.size) > MAX_REF_EDGE:
        img.thumbnail((MAX_REF_EDGE, MAX_REF_EDGE), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
