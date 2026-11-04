"""Předělat hotovou ilustraci na jiný poměr stran (GRAFIK#150, vzor NG-ROBOT `studio_formats.py`).

Ořez podle hlavního objektu je zdarma a dělá ho kód z originálu v plném rozlišení. Rozšíření obrazu (celý originál zůstane,
okraje dogeneruje `fal-ai/bria/expand`) je placené a jen s `confirm_cost`. Vzniká nový obrázek, originál se nemění.

Hlavní objekt hledá lokálně spectral residual saliency. Když si není jistý (nic výrazného, nebo výrazná plocha mimo střed),
vrátí `None` místo vymyšleného rámečku (GRAFIK#68, vzor screenshot-to-code); objekt pak určí operátor rámečkem 0–1000.
"""
from __future__ import annotations

import io
import re

import numpy as np
from PIL import Image, ImageFilter

EXPAND_ENDPOINT = "fal-ai/bria/expand"
EXPAND_USD = 0.04           # ceník fal, stejně jako NG-ROBOT media_usage
SUBJECT_MARGIN = 0.04       # okraj kolem objektu, aby ořez nešel těsně po hraně
MAX_CANVAS_SIDE = 3000      # rozšíření: delší strana plátna (fal bere pod 5000)
_CENTER_BAND = (1 / 3, 2 / 3)
_MAX_SALIENT_SHARE = 0.85


class FormatError(ValueError):
    """Chyba zadání, kterou má operátor vidět (400)."""


def ratio(value: str) -> float:
    m = re.fullmatch(r"(\d{1,2}(?:\.\d{1,2})?):(\d{1,2})", value or "")
    if not m or not float(m[1]) or not int(m[2]):
        raise FormatError(f"neznámý formát {value!r}, čekám třeba 16:9")
    return float(m[1]) / int(m[2])


def saliency_map(img: Image.Image, size: int = 128) -> np.ndarray:
    """Spectral residual saliency (Hou & Zhang 2007) v numpy, mapa size×size v rozsahu 0–1."""
    g = np.asarray(img.convert("L").resize((size, size), Image.Resampling.BILINEAR), dtype=np.float64)
    spectrum = np.fft.fft2(g)
    log_amp = np.log(np.abs(spectrum) + 1e-9)
    padded = np.pad(log_amp, 1, mode="edge")
    avg = sum(padded[i:i + size, j:j + size] for i in range(3) for j in range(3)) / 9
    sal = np.abs(np.fft.ifft2(np.exp(log_amp - avg + 1j * np.angle(spectrum)))) ** 2
    out = np.asarray(Image.fromarray((sal / (sal.max() or 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(3)), dtype=np.float64)
    return out / (out.max() or 1)


def find_subject(img: Image.Image) -> list[int] | None:
    """Rámeček hlavního objektu [top, left, bottom, right] v 0–1000, nebo None, když si saliency není jistá."""
    sal = saliency_map(img)
    n = sal.shape[0]
    mask = sal >= max(sal.mean() + 2 * sal.std(), 0.25)
    if not mask.any():
        return None
    ys, xs = np.nonzero(mask)
    x1, x2 = np.percentile(xs, [2, 98])   # pár osamělých bodů na okraji rámeček nenafoukne
    y1, y2 = np.percentile(ys, [2, 98])
    weights = sal[mask]
    cx, cy = float((xs * weights).sum() / weights.sum()) / n, float((ys * weights).sum() / weights.sum()) / n
    box = [round(y1 / n * 1000), round(x1 / n * 1000), round(min(n, y2 + 1) / n * 1000), round(min(n, x2 + 1) / n * 1000)]
    share = (box[2] - box[0]) * (box[3] - box[1]) / 1e6
    lo, hi = _CENTER_BAND
    if not (lo <= cx <= hi and lo <= cy <= hi) or share > _MAX_SALIENT_SHARE:
        return None
    return box


def _slide(center: float, length: int, total: int) -> int:
    return int(max(0, min(total - length, round(center - length / 2))))


def plan(width: int, height: int, target: float, subject: list[int] | None) -> dict:
    """Ořez a rozšíření pro obrázek width×height a poměr `target`; všechny rámečky v 0–1000 jako `subject`.

    `crop` = výřez [top, left, bottom, right] se středem na objektu, `cuts_subject` = objekt i s okrajem se do výřezu nevejde.
    `expand` = plátno [w, h] v pixelech a poloha originálu na něm [x, y]; None, když poměr už sedí.
    """
    if width <= 0 or height <= 0:
        raise FormatError("neplatný rozměr obrázku")
    if subject:
        t, l, b, r = subject
        cx, cy = (l + r) / 2000 * width, (t + b) / 2000 * height
        sw = min(width, (r - l) / 1000 * width + 2 * SUBJECT_MARGIN * width)
        sh = min(height, (b - t) / 1000 * height + 2 * SUBJECT_MARGIN * height)
    else:
        cx, cy, sw, sh = width / 2, height / 2, 0, 0
    src = width / height
    if abs(src - target) / target <= 0.005:
        return {"crop": [0, 0, 1000, 1000], "crop_px": [width, height], "cuts_subject": False, "expand": None}
    if src > target:   # zdroj je širší: ubírá se šířka, rozšiřuje výška
        cw = max(1, round(height * target))
        x = _slide(cx, cw, width)
        crop_px, crop, cuts = [cw, height], [0, round(x / width * 1000), 1000, round((x + cw) / width * 1000)], sw > cw
        canvas, place = [width, round(width / target)], [0, (round(width / target) - height) // 2]
    else:
        ch = max(1, round(width / target))
        y = _slide(cy, ch, height)
        crop_px, crop, cuts = [width, ch], [round(y / height * 1000), 0, round((y + ch) / height * 1000), 1000], sh > ch
        canvas, place = [round(height * target), height], [(round(height * target) - width) // 2, 0]
    scale = min(1.0, MAX_CANVAS_SIDE / max(canvas))
    expand = {"canvas": [max(1, round(canvas[0] * scale)), max(1, round(canvas[1] * scale))],
              "place": [round(place[0] * scale), round(place[1] * scale)],
              "original": [max(1, round(width * scale)), max(1, round(height * scale))]}
    return {"crop": crop, "crop_px": crop_px, "cuts_subject": bool(subject) and cuts, "expand": expand}


def crop(img: Image.Image, box: list[int]) -> Image.Image:
    t, l, b, r = box
    w, h = img.size
    return img.crop((round(l * w / 1000), round(t * h / 1000), round(r * w / 1000), round(b * h / 1000)))


def expand(img: Image.Image, layout: dict, call) -> Image.Image:
    """Rozšíření obrazu: `call(png_bytes, arguments)` vrátí PNG plátna (fal; testy ho podstrčí). Originál se vrátí na místo."""
    small = img.resize(tuple(layout["original"]), Image.Resampling.LANCZOS) if img.size != tuple(layout["original"]) else img
    buf = io.BytesIO()
    small.save(buf, "PNG")
    out_png = call(buf.getvalue(), {"canvas_size": layout["canvas"], "original_image_size": layout["original"],
                                    "original_image_location": layout["place"]})
    with Image.open(io.BytesIO(out_png)) as im:
        out = im.convert("RGB")
    if out.size != tuple(layout["canvas"]):
        out = out.resize(tuple(layout["canvas"]), Image.Resampling.LANCZOS)
    out.paste(small, tuple(layout["place"]))   # původní pixely beze změny, i kdyby je model přepočítal
    return out


def fal_expand(png: bytes, arguments: dict) -> bytes:
    """Placené volání fal-ai/bria/expand (0,04 USD). Volá se jen po confirm_cost."""
    import fal_client
    import httpx

    from engine.keys import get_key
    key = get_key("FAL_KEY", "FAL_API_KEY")
    if not key:
        raise FormatError("fal: chybí FAL_KEY / FAL_API_KEY")
    client = fal_client.SyncClient(key=key, default_timeout=300)
    result = client.subscribe(EXPAND_ENDPOINT, arguments={"image_url": client.upload(png, "image/png"), **arguments})
    image = result.get("image") or (result.get("images") or [{}])[0]
    if not image.get("url"):
        raise FormatError(f"fal {EXPAND_ENDPOINT}: odpověď bez obrázku")
    return httpx.get(image["url"], timeout=120).raise_for_status().content
