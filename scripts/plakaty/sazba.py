# Shared by the large infographics composed by a script: vector text, pictures, leaders and the cut-out of a subject.
# Top-level <g id> = layer in VectorCraft, <g id> inside it = named group (same scheme as scripts/3d/pantheon_plakat.py).
import base64
import io
import json
import sys
import urllib.request
from datetime import datetime
from html import escape
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "shared")]

FONT = "Bahnschrift, 'Roboto Condensed', 'Arial Narrow', sans-serif"


def text(x, y, s, size, fill, weight=400, anchor="start", spacing=0.0, italic=False) -> str:
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    it = ' font-style="italic"' if italic else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}"{ls}{it}>{escape(s)}</text>'


def wrap(s: str, n: int) -> list[str]:
    lines, cur = [], ""
    for w in s.split(" "):
        if cur and len(cur) + 1 + len(w) > n:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + [cur] if cur else lines


def para(x, y, s, size, fill, n, leading=1.28, weight=400, anchor="start") -> str:
    return "".join(text(x, y + i * size * leading, line, size, fill, weight, anchor) for i, line in enumerate(wrap(s, n)))


def group(name: str, body: str) -> str:
    return f'<g id="{escape(name, quote=True)}">{body}</g>'


def image_tag(im: Image.Image, x: float, y: float, w: float, h: float, fmt: str | None = None) -> str:
    fmt = fmt or ("PNG" if im.mode == "RGBA" else "JPEG")
    buf = io.BytesIO()
    if fmt == "JPEG":
        im.convert("RGB").save(buf, fmt, quality=90)
    else:
        im.save(buf, fmt, optimize=True)
    uri = f"data:image/{fmt.lower()};base64," + base64.b64encode(buf.getvalue()).decode()
    return f'<image href="{uri}" x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}"/>'


def fit(im: Image.Image, x: float, y: float, w: float, h: float, edge: int = 2) -> str:
    """Whole picture inside the box, sharp at twice the page size at most."""
    k = min(w / im.width, h / im.height)
    pw, ph = im.width * k, im.height * k
    scaled = im
    if im.width > pw * edge:
        scaled = im.resize((round(pw * edge), round(ph * edge)), Image.LANCZOS)
    return image_tag(scaled, x + (w - pw) / 2, y + (h - ph) / 2, pw, ph)


def cover(im: Image.Image, x: float, y: float, w: float, h: float, focus: tuple[float, float] = (0.5, 0.5), edge: int = 2) -> str:
    """Fills the box, the picture is cropped around `focus`."""
    k = max(w / im.width, h / im.height)
    cw, ch = w / k, h / k
    left = min(max(0, im.width * focus[0] - cw / 2), im.width - cw)
    top = min(max(0, im.height * focus[1] - ch / 2), im.height - ch)
    crop = im.crop((round(left), round(top), round(left + cw), round(top + ch)))
    if crop.width > w * edge:
        crop = crop.resize((round(w * edge), round(h * edge)), Image.LANCZOS)
    return image_tag(crop, x, y, w, h)


def leader(a, b, color, width=1.4, dot=3.4, elbow=True, opacity=1.0) -> str:
    """From the thing (a) to the label (b), straight or with one bend (docs/infografiky-zasady.md)."""
    (ax, ay), (bx, by) = a, b
    pts = [(ax, ay), (bx, by)] if not elbow or abs(ay - by) < 6 or abs(ax - bx) < 6 else [(ax, ay), (ax, by), (bx, by)]
    poly = " ".join(f"{p:.1f},{q:.1f}" for p, q in pts)
    op = f' stroke-opacity="{opacity}"' if opacity < 1 else ""
    return f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="{width}"{op}/><circle cx="{ax:.1f}" cy="{ay:.1f}" r="{dot}" fill="{color}"/>'


def cutout(src: Path, dst: Path, shadow: float = 0.85, erode: int = 0) -> Path:
    """Subject on a plain light backdrop to RGBA, free (rembg u2net on the CPU). The photographed shadow stays as black with alpha."""
    from rembg import new_session, remove

    im = Image.open(src).convert("RGB")
    mask = remove(im, session=new_session("u2net", providers=["CPUExecutionProvider"]), only_mask=True).convert("L")
    if erode:
        mask = mask.filter(ImageFilter.MinFilter(erode * 2 + 1)).filter(ImageFilter.GaussianBlur(0.7))
    a = np.asarray(mask, dtype=np.float32) / 255
    rgb = np.asarray(im, dtype=np.float32) / 255
    lum = rgb.mean(axis=2)
    # the backdrop is a smooth quadratic surface fitted to the pixels that are not subject or shadow
    h, w = lum.shape
    yy, xx = np.mgrid[0:h:8, 0:w:8]
    u, v, z = xx.ravel() / w, yy.ravel() / h, lum[::8, ::8].ravel()
    keep = a[::8, ::8].ravel() < 0.02
    basis = np.stack([np.ones_like(u), u, v, u * u, u * v, v * v], axis=1)
    for _ in range(6):
        coef, *_rest = np.linalg.lstsq(basis[keep], z[keep], rcond=None)
        keep = (a[::8, ::8].ravel() < 0.02) & (z > basis @ coef - 0.012)
    gy, gx = np.mgrid[0:h, 0:w]
    gu, gv = gx / w, gy / h
    level = coef[0] + coef[1] * gu + coef[2] * gv + coef[3] * gu * gu + coef[4] * gu * gv + coef[5] * gv * gv
    sh = np.clip((1 - lum / level - 0.018) / 0.982, 0, 1) * shadow
    sh = np.asarray(Image.fromarray((sh * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(1.2)), dtype=np.float32) / 255
    if erode:   # a halo of the backdrop around the subject would pass for a shadow
        near = np.asarray(mask.filter(ImageFilter.MaxFilter(erode * 2 + 5)), dtype=np.float32) / 255
        sh[(near > 0.5) & (a < 0.5)] *= 0.6
    out = np.zeros(rgb.shape[:2] + (4,), dtype=np.float32)
    out[..., :3] = rgb * (a[..., None] > 0.02)
    out[..., 3] = np.maximum(a, sh * (1 - a))
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((out * 255).astype("uint8"), "RGBA").save(dst)
    return dst


def crop_alpha(im: Image.Image, pad: int = 4) -> tuple[Image.Image, tuple[int, int]]:
    """Trim the transparent margin; returns the trimmed picture and how far its corner moved."""
    box = im.getchannel("A").point(lambda v: 255 if v > 6 else 0).getbbox()
    x0, y0 = max(0, box[0] - pad), max(0, box[1] - pad)
    return im.crop((x0, y0, min(im.width, box[2] + pad), min(im.height, box[3] + pad))), (x0, y0)


def write_poster(svg: str, out: Path, stem: str, w: int, h: int, title: str, knihovna: str | None, ai: bool) -> Path:
    """SVG, PNG, PDF and a fresh copy for the VectorCraft window; the copy is never overwritten, the operator may have edited it."""
    from engine.infographics import for_vectorcraft, rasterize

    out.mkdir(parents=True, exist_ok=True)
    (out / f"{stem}.svg").write_text(svg, encoding="utf-8")
    copy = out / f"{stem}-vectorcraft-{datetime.now():%Y%m%d-%H%M%S}.svg"
    copy.write_text(for_vectorcraft(svg), encoding="utf-8")
    for fmt in ("png", "pdf"):
        (out / f"{stem}.{fmt}").write_bytes(rasterize(svg, w, h, fmt))
    print({p.name: p.stat().st_size for p in sorted(out.iterdir()) if p.is_file()})
    if knihovna:
        body = {"b64": base64.b64encode((out / f"{stem}.png").read_bytes()).decode(), "name": f"{stem}.png", "title": title, "blender_render": not ai, "svg": svg}
        req = urllib.request.Request(knihovna + "/api/v2/library/upload", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            print(r.read().decode("utf-8"))
    return out / f"{stem}.png"
