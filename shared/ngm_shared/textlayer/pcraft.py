"""Mazání popisků PhotoCraftem a sazba písmem NG (počeštění map a infografik na fotce nebo reliéfu).

`cv2.inpaint` na stínovaném reliéfu rozmazal terén, přerušil trasy a zničil barevné pruhy (mapa Everestu,
DECISIONS 2026-10-30). PhotoCraft (`paint.remove`, doplnění textury z okolí, bez AI, lokálně a bez okna) terén
doplní věrně. Kód k tomu: tenké syté čáry a značky se po mazání vrátí z originálu, světlý text na barevném
pruhu se nemaže, ale přemaluje barvou pruhu a pruh se prodlouží podle překladu.

Rámeček od Claude kolem otočeného textu neurčí výšku písma spolehlivě, proto ji určí vodorovné popisky téhož
obrázku a prostrkání dopočítá změřená délka. Křivku textu dá barva jeho pixelů v originálu.
"""
from __future__ import annotations

import glob
import html
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ngm_shared.textlayer import style as st

DEFAULT_CRAFT_HOME = "C:/Users/stock/Tools/Craft"
RESOURCES = Path(os.environ.get("NGM_FONTS", "C:/Users/stock/Documents/000_NGM/RESOURCES/Basic Fonts"))
FONT_DIRS = [Path("C:/Windows/Fonts"), Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Windows/Fonts",
             RESOURCES / "Document fonts/Document fonts", RESOURCES / "NGS map fonts/NatGeo Bumstead",
             RESOURCES / "NGS map fonts/NatGeo Peele"]


def _ng_font(name: str) -> Path:
    """Písma NG jsou nainstalovaná v systému; RESOURCES je záloha."""
    return next((d / name for d in FONT_DIRS if (d / name).is_file()), FONT_DIRS[0] / name)


# popisek „tučně“ v NG je Medium; Bold jen na barevném pruhu
FONT_FILES = {
    ("sans", False): _ng_font("GeographEdit-Regular.otf"),
    ("sans", True): _ng_font("GeographEdit-Medium.otf"),
    ("serif", False): _ng_font("NatGeoBumstead.otf"),
    ("serif", True): _ng_font("NatGeoBumstead-Heavy.otf"),
}
PLATE_FONT = _ng_font("GeographEdit-Bold.otf")
ROMAN_FONT = _ng_font("NatGeoPeele.otf")       # svislá patková (Bumstead je šikmý); státy na tištěné mapě
SVG_FONT = {"sans": f"'{st.GEO}', sans-serif", "serif": f"'{st.BUM}', serif"}
TIMEOUT_S = 300
MAX_PARAMS = 28_000             # znaků na jedno spuštění (příkazová řádka Windows má ~32 000)
FLAT_SHARE = 0.72               # podíl hladkých pixelů, od kterého je obrázek plochý
LINE_MIN_PX = 38                # sytý útvar delší než tohle je čára, písmena jsou menší (šířka do 1500 px)
LINE_MAX_HALF = 5               # nejvyšší poloviční tloušťka čáry; plocha mapy je tlustší a musí jít smazat
MIN_SHRINK = 0.75
PLATE_TEXT = 0.62                # písmo na pruhu jako podíl jeho výšky
SPACED_BELOW = 0.7              # verzálky užší než tohle vůči rámečku jsou v originálu prostrkané


class PhotoCraftError(RuntimeError):
    """PhotoCraft neběží nebo nevrátil výsledek."""


def find_cli() -> Path | None:
    direct = os.environ.get("PHOTOCRAFT_CLI")
    if direct and Path(direct).is_file():
        return Path(direct)
    home = Path(os.environ.get("CRAFT_HOME") or DEFAULT_CRAFT_HOME)
    path = home / "photocraft" / "photocraft-cli.exe"
    if path.is_file():
        return path
    cand = sorted(glob.glob(str(home / "next" / "cand" / "photocraft-*" / "photocraft-cli.exe")))
    return Path(cand[-1]) if cand else None


def ready() -> bool:
    return find_cli() is not None and PLATE_FONT.is_file() and all(p.is_file() for p in FONT_FILES.values())


def textured(img: np.ndarray) -> bool:
    """Má obraz texturu (reliéf, fotka)? Plochá mapa ji nemá a `cv2.inpaint` je na ní čistší než doplnění z okolí."""
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    return float((np.abs(cv2.Laplacian(gray, cv2.CV_32F)) < 2).mean()) < FLAT_SHARE


def _batches(strokes: list[dict]) -> list[list[dict]]:
    out, cur, size = [], [], 0
    for s in strokes:
        n = len(json.dumps(s))
        if cur and size + n > MAX_PARAMS:
            out.append(cur)
            cur, size = [], 0
        cur.append(s)
        size += n
    return out + [cur] if cur else out


def remove(img: np.ndarray, strokes: list[dict]) -> np.ndarray:
    """`paint.remove` nad kopií obrázku; originál se nemění."""
    cli = find_cli()
    if cli is None:
        raise PhotoCraftError("PhotoCraft není nainstalovaný (CRAFT_HOME nebo PHOTOCRAFT_CLI)")
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "src.png", Path(tmp) / "out.png"
        Image.fromarray(img).save(src)
        # Remove bere vzorky z obrazu: všechny tahy naráz, po dávkách by doplňoval ještě nesmazaný text.
        # Dávky jen, když by se tahy nevešly na příkazovou řádku.
        for part in _batches(strokes):
            params = json.dumps({"strokes": part, "closeLoops": False})
            try:
                r = subprocess.run([str(cli), "run", str(src), "--cmd", "paint.remove", "--params", params,
                                    "--out", str(out)],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_S)
            except (OSError, subprocess.TimeoutExpired) as e:
                raise PhotoCraftError(f"PhotoCraft neběží: {e}") from e
            if r.returncode != 0 or not out.is_file():
                raise PhotoCraftError(f"PhotoCraft selhal ({r.returncode}): {r.stderr[:300]}")
            out.replace(src)
        with Image.open(src) as im:
            return np.array(im.convert("RGB"))


# ---------------------------------------------------------------------------- geometrie

def _lines(el: dict) -> list[str]:
    text = el["cs"].upper() if el["caps"] and el["en"] == el["en"].upper() else el["cs"]
    return text.split("\n")


def _rot_size(elements: list[dict], width: int) -> float:
    """Velikost písma otočených popisků: medián výšky jednořádkových vodorovných popisků obrázku."""
    heights = [el["box"][3] - el["box"][1] for el in elements if not el["angle"] and "\n" not in el["en"]]
    return float(np.median(heights)) if heights else 14 * width / 769


def _axis(el: dict) -> tuple[float, float, float, float]:
    th = math.radians(el["angle"])
    return math.cos(th), -math.sin(th), math.sin(th), math.cos(th)


def _length(el: dict) -> float:
    """Délka textu podél osy z rámečku kolem otočeného textu (w = L cos + H sin, h = L sin + H cos)."""
    x0, y0, x1, y1 = el["box"]
    w, h = x1 - x0, y1 - y0
    if not el["angle"]:
        return w
    th = math.radians(abs(el["angle"]))
    c, s = math.cos(th), math.sin(th)
    det = c * c - s * s
    return math.hypot(w, h) * 0.95 if abs(det) < 0.6 else abs((w * c - h * s) / det)


def _curve(el: dict, hsv: np.ndarray) -> tuple | None:
    """Křivka barevného otočeného textu: parabola v souřadnicích popisku z pixelů jeho barvy, jinak None."""
    if not el["angle"]:
        return None
    r, g, b = st.hex_to_rgb(el["color"])
    target = cv2.cvtColor(np.uint8([[[r, g, b]]]), cv2.COLOR_RGB2HSV)[0, 0]
    if target[1] < 50:
        return None
    x0, y0, x1, y1 = [int(v) for v in el["box"]]
    sub = hsv[max(y0, 0):y1, max(x0, 0):x1]
    ys, xs = np.nonzero((np.abs(sub[..., 0].astype(int) - int(target[0])) < 14) & (sub[..., 1] > 40))
    if len(xs) < 40:
        return None
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ux, uy, vx, vy = _axis(el)
    dx, dy = xs + max(x0, 0) - cx, ys + max(y0, 0) - cy
    u, v = dx * ux + dy * uy, dx * vx + dy * vy
    a, b_, c = np.polyfit(u, v, 2)
    u0, u1 = float(u.min()), float(u.max())
    if abs(a) * ((u1 - u0) / 2) ** 2 < 0.04 * (u1 - u0):   # skoro rovný text je rovný
        return None
    return (float(a), float(b_), float(c), u0, u1, cx, cy)


def _curve_point(fit: tuple, el: dict, u: float) -> tuple[float, float]:
    a, b, c, _, _, cx, cy = fit
    ux, uy, vx, vy = _axis(el)
    v = a * u * u + b * u + c
    return cx + u * ux + v * vx, cy + u * uy + v * vy


def _protected(img: np.ndarray, hsv: np.ndarray, elements: list[dict]) -> np.ndarray:
    """Co po mazání zůstane z originálu: tenké dlouhé syté čáry (trasy) a plné čtverečky (značky) mimo popisky."""
    H, W = img.shape[:2]
    sat = (hsv[..., 1] > 55).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(sat, connectivity=8)
    half = cv2.distanceTransform(sat, cv2.DIST_L2, 3)
    out = np.zeros((H, W), np.uint8)
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if max(w, h) > LINE_MIN_PX * max(1.0, W / 1500):      # velká písmena skenu by se jinak vrátila z originálu
            keep = half[lab == i].max() <= LINE_MAX_HALF
        else:
            mx, my = x + w / 2, y + h / 2
            in_label = any(e["box"][0] <= mx <= e["box"][2] and e["box"][1] <= my <= e["box"][3] for e in elements)
            keep = 7 <= w <= 16 and 7 <= h <= 16 and area > 0.85 * w * h and 0.75 < w / h < 1.33 and not in_label
        if keep:
            out[lab == i] = 1
    return cv2.dilate(out, np.ones((3, 3), np.uint8))


def _bar_rows(hsv: np.ndarray, x0: int, x1: int, y0: int, y1: int) -> tuple[int, int]:
    """Skutečná výška barevného pruhu: řádky kolem rámečku, kde je pruh sytý (rámeček od Claude je jen text)."""
    filled = (hsv[:, max(x0, 0):x1, 1] > 100).mean(axis=1) > 0.3
    top, bot = y0, y1
    while top > 0 and filled[top - 1]:
        top -= 1
    while bot < len(filled) and filled[bot]:
        bot += 1
    return top, bot


# ---------------------------------------------------------------------------- mazání

def _dark_left(img: np.ndarray, clean: np.ndarray, el: dict) -> float:
    """Podíl tmavého písma, které po mazání v rámečku zůstalo (0 = čisto); světlé popisky se takhle nezměří."""
    if sum(st.hex_to_rgb(el["color"])) > 240:
        return 0.0
    x0, y0, x1, y1 = [max(int(v), 0) for v in el["box"]]
    before = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY) < 100
    after = cv2.cvtColor(clean[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY) < 100
    return round(float((before & after).sum()) / max(1, int(before.sum())), 3)


def erase(img: np.ndarray, elements: list[dict]) -> tuple[np.ndarray, list[dict]]:
    """Vymaže popisky. Vrací (obraz bez textu, sazbu popisků: délka, rozteč, velikost, křivka, pruh)."""
    H, W = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    protect = _protected(img, hsv, elements)
    rot_px = _rot_size(elements, W)
    strokes, plates, layout = [], [], []
    for el in elements:
        x0, y0, x1, y1 = [int(v) for v in el["box"]]
        L = _length(el)
        n_src = el["en"].count("\n") + 1
        pitch = rot_px * 1.55 if el["angle"] else (y1 - y0) / n_src
        cx, cy = (el["box"][0] + el["box"][2]) / 2, (el["box"][1] + el["box"][3]) / 2
        info = {"L": L, "pitch": pitch, "center": (cx, cy), "rot_px": rot_px, "curve": None, "plate": None}
        layout.append(info)
        roi = hsv[max(y0, 0):y1, max(x0, 0):x1]
        rgb = st.hex_to_rgb(el["color"])
        if min(rgb) > 200 and roi.size and (roi[..., 1] > 100).mean() > 0.25:
            plates.append((el, info, np.median(img[max(y0, 0):y1, max(x0, 0):x1][roi[..., 1] > 100], axis=0)))
            continue
        ux, uy, vx, vy = _axis(el)
        fit = _curve(el, hsv)
        if fit:
            info["curve"] = fit
            pts = [_curve_point(fit, el, u) for u in np.linspace(fit[3] - 6, fit[4] + 6, 40)]
            strokes.append({"points": [[round(a, 1), round(b, 1)] for a, b in pts], "size": int(pitch * 1.05),
                            "hardness": 100, "spacing": 10})
            continue
        length = L * 1.12 if el["angle"] else L
        size = max(5, int(pitch * 1.15))
        for i in range(n_src):
            off = (i - (n_src - 1) / 2) * pitch
            r = min(size / 2, length / 2 - 1)
            pts = [[round(cx + t * ux + off * vx, 1), round(cy + t * uy + off * vy, 1)]
                   for t in (-length / 2 + r, length / 2 - r)]
            strokes.append({"points": pts, "size": size, "hardness": 100, "spacing": 10})
    clean = remove(img, strokes) if strokes else img.copy()
    clean[protect > 0] = img[protect > 0]
    for el, info in zip(elements, layout):
        info["residue"] = _dark_left(img, clean, el)
    for el, info, col in plates:
        x0, y0, x1, y1 = [int(v) for v in el["box"]]
        y0, y1 = _bar_rows(hsv, x0, x1, y0, y1)
        font = ImageFont.truetype(str(PLATE_FONT), max(6, int(round((y1 - y0) * PLATE_TEXT))))
        text = _lines(el)[0]
        bar_w = max(x1 - x0 + 7, int(font.getlength(text)) + 10)
        grow = bar_w - (x1 - x0 + 7)
        # pruh roste od strany, kde navazuje na trasu
        left, right = protect[y0:y1, max(0, x0 - 12):x0].sum(), protect[y0:y1, x1:min(W, x1 + 12)].sum()
        nx0 = max(0, x0 - 2 if left >= right else x0 - 2 - grow)
        clean[y0:y1, nx0:nx0 + bar_w] = col
        info["plate"] = [nx0, y0, nx0 + bar_w, y1]
    for info in layout:
        info["protect"] = protect
    return clean, layout


# ---------------------------------------------------------------------------- sazba

def _font(el: dict, px: float, ss: int, bold: bool | None = None) -> ImageFont.FreeTypeFont:
    if el.get("upright") and el["font"] == "serif" and not el["italic"]:
        return ImageFont.truetype(str(ROMAN_FONT), max(6, int(round(px * ss))))
    # kurzíva NG je Bumstead (šikmý sám o sobě); Geograph Edit kurzívu nemá
    family = "serif" if el["italic"] or el.get("spaced") else el["font"]
    return ImageFont.truetype(str(FONT_FILES[family, el["bold"] if bold is None else bold]), max(6, int(round(px * ss))))


def _is_spaced(el: dict, L: float, pitch: float) -> bool:
    """Prostrkané verzálky (L H O T S E): původní text by v rámečku zabral jen část šířky."""
    if "spaced" in el:
        return bool(el["spaced"])
    if el["angle"] or not el["caps"]:
        return False
    font = ImageFont.truetype(str(FONT_FILES["sans", False]), max(6, int(round(pitch * 0.82))))
    return max(font.getlength(t) for t in el["en"].split("\n")) < SPACED_BELOW * L


def _glyph(layer: Image.Image, ch: str, font, fill: str, x: float, y: float, dirx: float, diry: float) -> None:
    tile = Image.new("RGBA", (int(font.size * 2.4), int(font.size * 2.4)), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((tile.width / 2, tile.height / 2), ch, font=font, fill=fill, anchor="mm")
    rot = tile.rotate(math.degrees(math.atan2(-diry, dirx)), resample=Image.Resampling.BICUBIC)
    left, top = int(x - rot.width / 2), int(y - rot.height / 2)
    # písmeno u okraje obrázku se ořízne; posunuté na okraj by se vrstvilo přes sousední
    layer.alpha_composite(rot, (max(0, left), max(0, top)), (max(0, -left), max(0, -top)))


def _clear_shift(protect: np.ndarray, x0: float, y0: float, x1: float, y1: float) -> int:
    """Nejmenší vodorovný posun, po kterém text neleží na trase ani značce."""
    W = protect.shape[1]
    for d in range(0, 61, 2):
        for sgn in (-1, 1):
            a, b = int(x0 + sgn * d), int(x1 + sgn * d)
            if a >= 2 and b <= W - 2 and protect[max(0, int(y0)):int(y1), a:b].sum() == 0:
                return sgn * d
    return 0


def typeset(base: Image.Image, elements: list[dict], layout: list[dict], base_href: str) -> tuple[Image.Image, str, list]:
    """Český text na podklad bez textu → (PNG, SVG, sazba popisků). Písmo NG, barva od Claude."""
    W, H = base.size
    ss = 4 if W * H < 5_000_000 else 2
    big = Image.new("RGBA", (W * ss, H * ss), (0, 0, 0, 0))
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
           f'<image href="{html.escape(base_href)}" x="0" y="0" width="{W}" height="{H}"/>']
    report = []

    def svg_text(el, x, y, px, content, ang=0.0, spacing=0.0, anchor="middle", fill=None):
        spaced = f' letter-spacing="{spacing:.2f}"' if spacing else ""
        svg.append(f'<text font-family="{SVG_FONT[el["font"]]}" font-size="{px:.1f}" '
                   f'font-weight="{"bold" if el["bold"] else "normal"}" fill="{fill or el["color"]}" '
                   f'text-anchor="{anchor}" dominant-baseline="middle"{spaced} '
                   f'transform="rotate({-ang:.1f} {x:.1f} {y:.1f})" x="{x:.1f}" y="{y:.1f}">{html.escape(content)}</text>')

    for n, (el, info) in enumerate(zip(elements, layout)):
        rows, L, pitch = _lines(el), info["L"], info["pitch"]
        cx, cy = info["center"]
        ux, uy, vx, vy = _axis(el)
        too_long = False
        if el.get("path"):
            px = float(el.get("size_px") or info["rot_px"] * 1.15)
            f = _font(el, px, ss)
            pts = np.array(el["path"], np.float32) * ss
            seg = np.hypot(*np.diff(pts, axis=0).T)
            arc = np.concatenate([[0.0], np.cumsum(seg)])
            adv = [f.getlength(c) for c in rows[0]]
            track = min(max(0.0, (arc[-1] - sum(adv)) / max(1, len(adv) - 1)), f.size * 1.6)
            t = (arc[-1] - sum(adv) - track * (len(adv) - 1)) / 2
            for ch, w in zip(rows[0], adv):
                s = t + w / 2
                i = min(int(np.searchsorted(arc, s, side="right")) - 1, len(seg) - 1)
                i = max(i, 0)
                d = (pts[i + 1] - pts[i]) / max(seg[i], 1e-6)
                x, y = pts[i] + d * (s - arc[i])
                _glyph(big, ch, f, el["color"], float(x), float(y), float(d[0]), float(d[1]))
                t += w + track
            path = "M" + " L".join(f"{a:.1f} {b:.1f}" for a, b in el["path"])
            svg.append(f'<path id="krivka-{n}" d="{path}" fill="none"/>'
                       f'<text font-family="{SVG_FONT[el["font"]]}" font-size="{px:.1f}" fill="{el["color"]}" '
                       f'letter-spacing="{track / ss:.2f}" dominant-baseline="middle">'
                       f'<textPath href="#krivka-{n}">{html.escape(rows[0])}</textPath></text>')
        elif info["plate"]:
            x0, y0, x1, y1 = info["plate"]
            px = (y1 - y0) * PLATE_TEXT
            f = ImageFont.truetype(str(PLATE_FONT), max(6, int(round(px * ss))))
            ImageDraw.Draw(big).text(((x0 + x1) / 2 * ss, (y0 + y1) / 2 * ss), rows[0], font=f, fill=el["color"], anchor="mm")
            svg_text({**el, "font": "sans", "bold": True}, (x0 + x1) / 2, (y0 + y1) / 2, px, rows[0])
        elif info["curve"]:
            fit = info["curve"]
            px = info["rot_px"] * 1.15
            f = _font(el, px, ss)
            adv = [f.getlength(c) for c in rows[0]]
            track = max(0.0, ((fit[4] - fit[3]) * ss - sum(adv)) / max(1, len(rows[0]) - 1))
            t = fit[3] * ss
            for ch, w in zip(rows[0], adv):
                u = (t + w / 2) / ss
                x, y = _curve_point(fit, el, u)
                slope = 2 * fit[0] * u + fit[1]
                _glyph(big, ch, f, el["color"], x * ss, y * ss, ux + slope * vx, uy + slope * vy)
                t += w + track
            pts = [_curve_point(fit, el, u) for u in np.linspace(fit[3], fit[4], 24)]
            path = "M" + " L".join(f"{a:.1f} {b:.1f}" for a, b in pts)
            svg.append(f'<path id="krivka-{n}" d="{path}" fill="none"/>'
                       f'<text font-family="{SVG_FONT[el["font"]]}" font-size="{px:.1f}" fill="{el["color"]}" '
                       f'letter-spacing="{track / ss:.2f}" dominant-baseline="middle">'
                       f'<textPath href="#krivka-{n}">{html.escape(rows[0])}</textPath></text>')
        elif el["angle"]:
            px = info["rot_px"]
            f = _font(el, px, ss)
            for i, row in enumerate(rows):
                off = (i - (len(rows) - 1) / 2) * pitch
                adv = [f.getlength(c) for c in row]
                track = 0.0
                if el["caps"] and len(rows) == 1 and len(row) > 1:      # prostrkané jako originál, nejvýš 1,1 em
                    track = min(max(0.0, (L * ss - sum(adv)) / (len(row) - 1)), f.size * 1.1)
                total = sum(adv) + track * (len(row) - 1)
                t = -total / 2
                lx, ly = cx + off * vx, cy + off * vy
                for ch, w in zip(row, adv):
                    _glyph(big, ch, f, el["color"], lx * ss + (t + w / 2) * ux, ly * ss + (t + w / 2) * uy, ux, uy)
                    t += w + track
                svg_text(el, lx, ly, px, row, el["angle"], track / ss)
        elif _is_spaced(el, L, pitch):
            el = {**el, "spaced": True}
            px = float(el.get("size_px") or info["rot_px"] * 1.15)
            f = _font(el, px, ss)
            track = min(max(0.0, (L * ss - max(sum(f.getlength(c) for c in r) for r in rows)) / max(1, max(map(len, rows)) - 1)),
                        f.size * 1.1)
            for i, row in enumerate(rows):
                y = cy + (i - (len(rows) - 1) / 2) * pitch
                adv = [f.getlength(c) for c in row]
                t = -(sum(adv) + track * (len(row) - 1)) / 2
                for ch, w in zip(row, adv):
                    _glyph(big, ch, f, el["color"], cx * ss + t + w / 2, y * ss, 1.0, 0.0)
                    t += w + track
                svg_text(el, cx, y, px, row, 0.0, track / ss)
        else:
            px = float(el.get("size_px") or pitch * (0.82 if len(el["en"].split("\n")) > 1 else 0.95))
            f = _font(el, px, ss)
            w0 = max(f.getlength(t) for t in rows) / ss
            if w0 > L * 1.28:      # delší překlad se zmenší, jen když by přetekl o hodně
                k = L * 1.28 / w0
                too_long = k < MIN_SHRINK
                px *= max(k, MIN_SHRINK)
                f = _font(el, px, ss)
            for i, row in enumerate(rows):
                y = cy + (i - (len(rows) - 1) / 2) * pitch
                lw = f.getlength(row) / ss
                shift = {"center": 0.0, "right": (L - lw) / 2, "left": (lw - L) / 2}[el["align"]]
                shift += _clear_shift(info["protect"], cx + shift - lw / 2 - 2, y - px / 2, cx + shift + lw / 2 + 2, y + px / 2)
                x = cx + shift
                # blok jméno + výška: bold jen jméno, čísla obyčejným řezem jako v originálu
                light = len(rows) > 1 and el["bold"] and any(c.isdigit() for c in row)
                ImageDraw.Draw(big).text((x * ss, y * ss), row, font=_font(el, px, ss, False) if light else f,
                                         fill=el["color"], anchor="mm")
                svg_text({**el, "bold": False} if light else el, x, y, px, row)
        report.append({"id": el["id"], "size_px": round(px, 1), "color": el["color"], "blend": "normal",
                       "color_measured": False, "box": [round(v) for v in el["box"]], "too_long": too_long, "residue": info.get("residue", 0.0)})
    svg.append("</svg>")
    out = base.convert("RGBA")
    out.alpha_composite(big.resize((W, H), Image.Resampling.LANCZOS))
    return out.convert("RGB"), "\n".join(svg), report
