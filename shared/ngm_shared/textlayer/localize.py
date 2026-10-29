"""Počeštění cizí infografiky vrstvou textu (test T2, plán STOPA 2026-10-29 § 6).

Claude přečte obrázek (texty, rámečky, otočení, barvu, písmo, český překlad a druh obrázku) → text se
z obrazu vymaže (`cv2.inpaint`) → český text se vysází ve velikosti původního → PNG a upravitelné SVG
(každý popisek jako `<text>`, podklad bez textu jako PNG vedle). Text nikdy nekreslí obrazový model.

Opravy proti prototypu T2 (`ZZZ_TEST/algoritmus-obrazku-2026-10-29/skripty/t2b_layer.py`):
- Barvu a rozsah písma měří kód z pixelů; rámeček a barva od Claude jsou jen výchozí bod. Na mapě
  Claude u otočených popisků vrátil o polovinu menší rámeček a šedou místo tmavě zelené, maska podle
  barvy písmo minula a popisky v barvě podkladu zůstaly v obraze.
- Velikost písma se odvozuje z původního textu ve změřeném rámečku hned v prvním průchodu, i u
  otočených popisků (v T2 až ve druhém kole).
- Mapa vrátí poradní upozornění: českou mapu má postavit KARTOGRAF z dat. Nic se neblokuje.

Přečtené texty (`<stem>.texty.json`, rámečky v pixelech originálu) jde opravit a vysázet znovu zdarma:
`localize(..., texts=upravené)`.
"""
from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ngm_shared import claude
from ngm_shared.textlayer import style as st

READ_MODEL = "claude-opus-5-5"
READ_EFFORT = "high"            # T2: přesný text i rámečky; mapa s 63 popisky 0,19 USD, infografika 0,11 USD
READ_USD = 0.20                 # odhad předem (horní mez z T2)
READ_SYSTEM = "You extract text from images for a localization pipeline (to Czech). Answer with JSON only."
READ_TASK = """The image is {w}x{h} px. First decide what the image is: "infographic", "map", "diagram", "chart",
"poster", "photo" or "other" (a map shows geography: coastlines, borders, rivers, places).
Then find every text element (titles, labels, legend entries, captions, credits).
Group words that belong to one line or one multi-line block of the same style into one element.
Return {{"kind": "...", "elements": [ ... ]}} where each element is:
{{"id": n, "en": exact original text, line breaks as \\n, "cs": Czech translation with the same number of lines,
 "box": [x0, y0, x1, y1] pixel box in THIS image around ALL letters of the element (for rotated text the box
 around the whole rotated text), "angle": rotation in degrees counter-clockwise (0 = horizontal),
 "color": text colour hex, "font": "sans" or "serif", "bold": bool, "italic": bool, "caps": bool,
 "align": "left"|"center"|"right"}}
Czech rules: correct diacritics; established Czech exonyms for places (Greenland = Grónsko, Iceland = Island,
Norway = Norsko...); names without a Czech form stay as they are; scientific terms in their standard Czech form.
Skip logos and icon-only marks."""

FONT_DIR = Path("C:/Windows/Fonts")
FONTS = {("serif", False, False): "times.ttf", ("serif", True, False): "timesbd.ttf",
         ("serif", False, True): "timesi.ttf", ("serif", True, True): "timesbi.ttf"}
SANS = "bahnschrift.ttf"        # jedna písmová rodina infografik GRAFIK (docs/infografiky-zasady.md)
CSS_FONT = {"sans": "Bahnschrift, sans-serif", "serif": "'Times New Roman', serif"}
LINE = 1.18                     # řádkování jako podíl velikosti písma
ROTATED_DEG = 3.0               # od kolika stupňů je popisek otočený
MAX_WIDER = 1.15                # český text smí být o 15 % širší než původní, pak se písmo zmenší
MIN_SHRINK = 0.75
RESIDUE_WARN = 0.15             # po mazání zůstalo víc než 15 % písma → upozornění

Ask = Callable[..., claude.Answer]


class LocalizeError(ValueError):
    """Obrázek nebo přečtené texty nejdou zpracovat."""


# ---------------------------------------------------------------------------- čtení

def read_texts(image: Path, *, ask: Ask = claude.ask, model: str = READ_MODEL,
               effort: str = READ_EFFORT) -> tuple[dict, dict]:
    """Claude přečte texty. Vrací (texty s rámečky v pixelech originálu, cena z usage)."""
    blk, (w, h), scale = claude.image_block(image)
    ans = ask([blk, {"type": "text", "text": READ_TASK.format(w=w, h=h)}], READ_SYSTEM, what="čtení textu",
              model=model, effort=effort, max_tokens=32000)
    data = claude.parse_json(ans.text, "čtení textu")
    data["scale"] = scale
    return normalize_texts(data), ans.cost()


def normalize_texts(data: dict) -> dict:
    """Ověří přečtené texty a rámečky převede na pixely originálu (`scale` 1.0)."""
    els = data.get("elements") if isinstance(data, dict) else None
    if not isinstance(els, list):
        raise LocalizeError("texty: chybí seznam elements")
    s = float(data.get("scale") or 1.0)
    out = []
    for i, el in enumerate(els):
        if not isinstance(el, dict) or not str(el.get("cs") or "").strip() or not str(el.get("en") or "").strip():
            continue
        try:
            box = [float(v) / s for v in el["box"]]
        except (KeyError, TypeError, ValueError):
            raise LocalizeError(f"texty: prvek {el.get('id', i)} nemá rámeček [x0, y0, x1, y1]") from None
        if len(box) != 4 or box[2] <= box[0] or box[3] <= box[1]:
            raise LocalizeError(f"texty: prvek {el.get('id', i)} má neplatný rámeček {el['box']}")
        color = str(el.get("color") or "#000000")
        try:
            st.hex_to_rgb(color)
        except ValueError:
            color = "#000000"
        out.append({"id": el.get("id", i + 1), "en": str(el["en"]), "cs": str(el["cs"]), "box": [round(v, 1) for v in box],
                    "angle": float(el.get("angle") or 0), "color": color,
                    "font": "serif" if el.get("font") == "serif" else "sans", "bold": bool(el.get("bold")),
                    "italic": bool(el.get("italic")), "caps": bool(el.get("caps")),
                    "align": el.get("align") if el.get("align") in ("left", "center", "right") else "left"})
    return {"kind": str(data.get("kind") or "other"), "scale": 1.0, "elements": out}


# ---------------------------------------------------------------------------- mazání

def _odd(v: float, lo: int, hi: int) -> int:
    k = int(max(lo, min(hi, v)))
    return k if k % 2 else k + 1


def _background(win: np.ndarray, k: int) -> np.ndarray:
    """Obraz bez tenkých tahů (písma): uzavření smaže tmavé tahy, otevření světlé, po kanálech, takže zmizí
    i šedé písmo na zelené ploše stejného jasu. Hrany ploch (pobřeží, hranice území) zůstanou; medián okolí
    je na rozeklaném pobřeží bral za písmo a mazal kusy země."""
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    return cv2.morphologyEx(cv2.morphologyEx(win, cv2.MORPH_CLOSE, se), cv2.MORPH_OPEN, se).astype(np.float32)


def _mix(px: np.ndarray, bg: np.ndarray, expect: np.ndarray, mix: float, tol: float, slack: float) -> np.ndarray:
    """Pixely, které jsou směsí podkladu a písma barvy `expect` (vyhlazený okraj) aspoň z podílu `mix` a leží
    nejvýš `tol` × kontrast + `slack` mimo úsečku podklad → písmo; barevná značka vedle černého popisku ne."""
    rel, diff = px - bg, expect - bg
    c2 = (diff * diff).sum(axis=2)
    t = (rel * diff).sum(axis=2) / np.maximum(c2, 1.0)
    off = np.linalg.norm(rel - t[..., None] * diff, axis=2)
    return (c2 > 225) & (t > mix) & (t < 1.4) & (off < tol * np.sqrt(c2) + slack)


def _ink(px: np.ndarray, bg: np.ndarray, color: np.ndarray, mix: float, tol: float, slack: float,
         blend: str | None = None) -> np.ndarray:
    """Písmo barvy `color`: plná barva (`normal`), nebo podklad × barva (`multiply`; mapa T2 sází šedé popisky
    násobením, na zelené ploše je písmo tmavě zelené, na žluté tmavě žluté; to byly „popisky v barvě
    podkladu“). Bez `blend` obojí."""
    out = np.zeros(px.shape[:2], bool)
    if blend in (None, "normal"):
        out |= _mix(px, bg, np.broadcast_to(color, px.shape), mix, tol, slack)
    if blend in (None, "multiply"):
        out |= _mix(px, bg, bg * (color / 255.0), mix, tol, slack)
    return out


def _band(shape: tuple, el: dict, origin: tuple, size: float, n_lines: int, lh: float,
          ink: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Otočený popisek leží v pásu podél své osy: písmo mimo pás, za mezerou delší než 0,8 řádku nebo za
    koncem rámečku od Claude (hranice území, sousední popisek na Britských ostrovech v T2) k němu nepatří.
    Vrací (pás, souřadnice podél a napříč popiskem)."""
    x0, y0, x1, y1 = el["box"]
    cx, cy = (x0 + x1) / 2 - origin[0], (y0 + y1) / 2 - origin[1]
    th = math.radians(el["angle"])
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    u = (xx - cx) * math.cos(th) - (yy - cy) * math.sin(th)      # podél textu
    v = (xx - cx) * math.sin(th) + (yy - cy) * math.cos(th)      # napříč
    band = np.abs(v) <= 0.6 * n_lines * 1.2 * size + 0.5 * lh
    hits = np.round(u[band & ink]).astype(int)
    if not len(hits):
        return band, u, v
    reach = 0.5 * ((x1 - x0) * abs(math.cos(th)) + (y1 - y0) * abs(math.sin(th)))
    cap = 1.15 * reach + 0.3 * lh   # rámečky od Claude měly v T2 délku otočených popisků ±10 %
    occupied = set(hits.tolist())
    lo = hi = 0
    if any(abs(h) <= reach for h in occupied):
        lo, hi = int(-reach), int(reach)
    gap = max(2, int(0.8 * lh))
    while lo > -cap and any(lo - d in occupied for d in range(1, gap + 1)):
        lo -= next(d for d in range(1, gap + 1) if lo - d in occupied)
    while hi < cap and any(hi + d in occupied for d in range(1, gap + 1)):
        hi += next(d for d in range(1, gap + 1) if hi + d in occupied)
    return band & (u >= lo - 1) & (u <= hi + 1), u, v


def _measure(img: np.ndarray, el: dict) -> dict:
    """Písmo jednoho popisku z pixelů: maska, barva a rámeček (pixely originálu)."""
    H, W = img.shape[:2]
    x0, y0, x1, y1 = el["box"]
    lines = el["en"].split("\n")
    bw, bh = x1 - x0, y1 - y0
    rotated = abs(el["angle"]) > ROTATED_DEG
    chars = max(len(t) for t in lines)
    if rotated:
        # velikost písma z rámečku otočeného bloku: řádek ~0,5 em na znak, výška řádku 1,2 em
        c, s = abs(math.cos(math.radians(el["angle"]))), abs(math.sin(math.radians(el["angle"])))
        size = max(bw / (0.5 * chars * c + 1.2 * len(lines) * s), bh / (0.5 * chars * s + 1.2 * len(lines) * c))
        lh = max(6.0, 1.2 * size)
        # rámeček od Claude bývá u otočeného textu menší a mimo střed (mapa T2: 58 px místo ~130 px),
        # okno se proto hledá na odhadnutou délku textu
        pad = max(0.6 * max(bw, bh), 0.6 * size * chars)
    else:
        lh = max(6.0, bh / len(lines))
        pad = 3 + 0.12 * lh             # jako prototyp T2: širší okno bralo i tečky měst vedle popisku
    X0, Y0 = int(max(0, x0 - pad)), int(max(0, y0 - pad))
    X1, Y1 = int(min(W, x1 + pad)), int(min(H, y1 + pad))
    win = np.ascontiguousarray(img[Y0:Y1, X0:X1])
    k = _odd(0.35 * lh, 5, 41)          # širší než tah písma
    bg = _background(win, k)
    px = win.astype(np.float32)
    d_bg = np.linalg.norm(px - bg, axis=2)
    inner = np.zeros(d_bg.shape, bool)
    inner[int(y0 - Y0):int(y1 - Y0), int(x0 - X0):int(x1 - X0)] = True
    # barva písma: od Claude, nebo změřená z jádra tahů (horní polovina odchylek od podkladu), podle toho, která
    # vysvětlí víc výrazných pixelů; změřená musí vyhrát o polovinu (v rámečku bývají i ostrůvky a hranice)
    color, measured = np.array(st.hex_to_rgb(el["color"]), np.float32), False
    cand = inner & (d_bg > 40)
    if cand.sum() >= 20:
        seen = np.median(px[cand & (d_bg >= np.percentile(d_bg[cand], 50))], axis=0)
        explained = lambda c: int((cand & _ink(px, bg, c, 0.35, 0.25, 25)).sum())      # noqa: E731
        if explained(seen) > 1.5 * explained(color):
            color, measured = seen, True
    ink = _ink(px, bg, color, 0.35, 0.25, 25)
    blend = "multiply" if (cand & _ink(px, bg, color, 0.35, 0.25, 25, "multiply")).sum() >         1.2 * (cand & _ink(px, bg, color, 0.35, 0.25, 25, "normal")).sum() else "normal"
    # jen shluky písma, které zasahují do rámečku od Claude (jiný popisek stejné barvy v okně zůstane)
    join = _odd(0.35 * lh, 3, 41)
    _, lab = cv2.connectedComponents(cv2.dilate(ink.astype(np.uint8), np.ones((join, join), np.uint8)))
    keep = np.setdiff1d(np.unique(lab[inner & ink]), [0])
    ink &= np.isin(lab, keep)
    box, frame, center = el["box"], None, ((x0 + x1) / 2, (y0 + y1) / 2)
    if rotated:
        band, u, v = _band(ink.shape, el, (X0, Y0), size, len(lines), lh, ink)
        ink &= band
        if ink.sum() >= 30:
            ys, xs = np.nonzero(ink)
            box = [X0 + float(xs.min()), Y0 + float(ys.min()), X0 + float(xs.max()) + 1, Y0 + float(ys.max()) + 1]
            # délka a výška písma v souřadnicích popisku, střed zpět do obrazu
            # (2.–98. percentil: drobné ostrůvky barvy písma v pásu velikost nezvětší)
            (ua, ub), (va, vb) = np.percentile(u[ink], [2, 98]), np.percentile(v[ink], [2, 98])
            frame = (float(ub - ua), float(vb - va))
            um, vm = (ua + ub) / 2, (va + vb) / 2
            th = math.radians(el["angle"])
            center = ((x0 + x1) / 2 + um * math.cos(th) + vm * math.sin(th),
                      (y0 + y1) / 2 - um * math.sin(th) + vm * math.cos(th))
    mask = cv2.dilate(ink.astype(np.uint8) * 255, np.ones((3, 3), np.uint8), iterations=2)
    near = cv2.dilate(ink.astype(np.uint8), np.ones((join, join), np.uint8)) > 0
    return {"window": (X0, Y0, X1, Y1), "mask": mask, "near": near, "ink_px": int(ink.sum()), "box": box,
            "frame": frame, "center": center, "color": st.rgb_to_hex(color), "color_measured": measured, "blend": blend,
            "ink_color": color, "k": k}


def _residue(clean: np.ndarray, m: dict) -> float:
    """Podíl písma, které po mazání zůstalo kolem popisku (0 = čisto): tenké tahy barvy písma ve vymazaném obraze."""
    if not m["ink_px"]:
        return 0.0
    X0, Y0, X1, Y1 = m["window"]
    win = np.ascontiguousarray(clean[Y0:Y1, X0:X1])
    left = _ink(win.astype(np.float32), _background(win, m["k"]), m["ink_color"], 0.5, 0.2, 0) & m["near"]
    return float(left.sum()) / m["ink_px"]


def erase(img: np.ndarray, elements: list[dict]) -> tuple[np.ndarray, list[dict], int]:
    """Vymaže písmo všech popisků. Vrací (obraz bez textu, měření popisků, počet maskovaných pixelů)."""
    mask = np.zeros(img.shape[:2], np.uint8)
    measured = []
    for el in elements:
        m = _measure(img, el)
        X0, Y0, X1, Y1 = m["window"]
        mask[Y0:Y1, X0:X1] |= m["mask"]
        measured.append(m)
    clean = cv2.inpaint(img, mask, 5, cv2.INPAINT_TELEA)
    for m in measured:
        m["residue"] = round(_residue(clean, m), 3)
    return clean, measured, int(mask.astype(bool).sum())


# ---------------------------------------------------------------------------- sazba

def _font(el: dict, px: float) -> ImageFont.FreeTypeFont:
    if el["font"] == "serif":
        name = FONTS[("serif", el["bold"], el["italic"])]
        return ImageFont.truetype(str(FONT_DIR / name), max(6, int(round(px))))
    f = ImageFont.truetype(str(FONT_DIR / SANS), max(6, int(round(px))))
    if el["bold"]:
        f.set_variation_by_name("Bold")
    return f


def _extent(el: dict, px: float, lines: list[str]) -> tuple[float, float, float]:
    """(šířka, výška) otočeného bloku textu a šířka nejdelšího řádku."""
    f = _font(el, px)
    w = max(f.getlength(line) for line in lines)
    h = px * LINE * len(lines)
    r = math.radians(el["angle"])
    return abs(w * math.cos(r)) + abs(h * math.sin(r)), abs(w * math.sin(r)) + abs(h * math.cos(r)), w


def font_size(el: dict, box: list[float], frame: tuple[float, float] | None = None) -> tuple[float, bool]:
    """Velikost písma: největší, při které se do rámečku vejde PŮVODNÍ text (i otočený, hned v prvním průchodu);
    u otočeného popisku navíc do změřené délky a výšky písma podél jeho osy (`frame`). Český text o víc než
    15 % širší se zmenší (nejvýš na 75 %). Vrací (velikost v px, zda se český text musel zmenšit až na mez)."""
    src = el["en"].split("\n")

    def in_box(px: float) -> bool:
        ew, eh, _ = _extent(el, px, src)
        return ew <= (box[2] - box[0]) * 1.04 and eh <= (box[3] - box[1]) * 1.25

    def in_frame(px: float) -> bool:
        # délka nejdelšího řádku; výška jen hrubě (slovo bez dotahů má písmo vysoké ~0,7 em, malá písmena 0,45)
        return (_extent({**el, "angle": 0.0}, px, src)[0] <= frame[0] * 1.04
                and px * ((len(src) - 1) * LINE + 0.45) <= frame[1])

    def largest(fits) -> float:
        lo, hi = 4.0, 400.0
        for _ in range(30):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if fits(mid) else (lo, mid)
        return lo

    # měřené písmo je přesnější než rámeček od Claude, ale ostrůvek barvy písma v pásu ho prodlouží:
    # nejvýš o 15 % nad odhad z rámečku
    px = min(largest(in_frame), 1.15 * largest(in_box)) if frame else largest(in_box)
    src_w = _extent(el, px, src)[2]
    cs_w = _extent(el, px, _cs_lines(el))[2]
    if cs_w > src_w * MAX_WIDER:
        k = src_w * MAX_WIDER / cs_w
        return px * max(MIN_SHRINK, k), k < MIN_SHRINK
    return px, False


def _cs_lines(el: dict) -> list[str]:
    text = el["cs"].upper() if el["caps"] and el["en"] == el["en"].upper() else el["cs"]
    return text.split("\n")


def typeset(base: Image.Image, elements: list[dict], measured: list[dict], base_href: str) -> tuple[Image.Image, str, list]:
    """Český text na podklad bez textu → (PNG, SVG, sazba popisků)."""
    W, H = base.size
    out = base.convert("RGBA")
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
           f'<image href="{html.escape(base_href)}" x="0" y="0" width="{W}" height="{H}"/>']
    report = []
    for el, m in zip(elements, measured):
        box = m["box"]
        x0, y0, x1, y1 = box
        lines = _cs_lines(el)
        px, too_long = font_size(el, el["box"], m["frame"])
        f = _font(el, px)
        tw = max(f.getlength(line) for line in lines)
        lh = px * LINE
        align = el["align"]
        layer = Image.new("RGBA", (int(tw + 8), int(lh * len(lines) + 8)), (0, 0, 0, 0))
        dr = ImageDraw.Draw(layer)
        fill = st.hex_to_rgb(m["color"]) + (255,)
        for i, line in enumerate(lines):
            lw = f.getlength(line)
            x = {"left": 4, "center": 4 + (tw - lw) / 2, "right": 4 + tw - lw}[align]
            dr.text((x, 4 + i * lh), line, font=f, fill=fill)
        ang = el["angle"]
        rotated = abs(ang) > 0.5
        if rotated:
            layer = layer.rotate(ang, expand=True, resample=Image.Resampling.BICUBIC)
        cx, cy = m["center"] if rotated else ((x0 + x1) / 2, (y0 + y1) / 2)
        if align == "left" and not rotated:
            pos = (int(x0 - 4), int(cy - layer.height / 2))
        elif align == "right" and not rotated:
            pos = (int(x1 - layer.width + 4), int(cy - layer.height / 2))
        else:
            pos = (int(cx - layer.width / 2), int(cy - layer.height / 2))
        sheet = Image.new("RGBA", out.size, (0, 0, 0, 0))
        sheet.paste(layer, pos)             # paste ořízne vrstvu, která přesahuje okraj obrázku
        if m["blend"] == "multiply":        # jako originál: podklad × barva písma
            a = np.asarray(sheet)[..., 3:4] / 255.0
            rgb = np.asarray(out)[..., :3] / 255.0
            mixed = rgb * (1 - a) + rgb * (np.array(st.hex_to_rgb(m["color"])) / 255.0) * a
            out = Image.fromarray((mixed * 255).round().astype(np.uint8)).convert("RGBA")
        else:
            out = Image.alpha_composite(out, sheet)
        anchor = "middle" if rotated else {"left": "start", "center": "middle", "right": "end"}[align]
        ax = cx if rotated else {"left": x0, "center": cx, "right": x1}[align]
        y_first = cy - lh * (len(lines) - 1) / 2
        spans = "".join(f'<tspan x="{ax:.0f}" y="{y_first + i * lh:.0f}">{html.escape(line)}</tspan>'
                        for i, line in enumerate(lines))
        style = (' font-style="italic"' if el["italic"] else "") +             (' style="mix-blend-mode:multiply"' if m["blend"] == "multiply" else "")
        svg.append(f'<text font-family="{CSS_FONT[el["font"]]}" font-size="{px:.1f}" '
                   f'font-weight="{"bold" if el["bold"] else "normal"}"{style} fill="{m["color"]}" '
                   f'text-anchor="{anchor}" dominant-baseline="middle" '
                   f'transform="rotate({-ang:.1f} {cx:.0f} {cy:.0f})">{spans}</text>')
        report.append({"id": el["id"], "size_px": round(px, 1), "color": m["color"], "blend": m["blend"],
                       "color_measured": m["color_measured"], "box": [round(v) for v in box],
                       "too_long": too_long, "residue": m["residue"]})
    svg.append("</svg>")
    return out.convert("RGB"), "\n".join(svg), report


# ---------------------------------------------------------------------------- celek

def warnings_for(texts: dict, report: list[dict]) -> list[dict]:
    """Poradní upozornění (nic neblokují): mapa, nesmazané stopy, příliš dlouhý překlad."""
    out = []
    if texts["kind"] == "map":
        out.append({"severity": "střední", "what": "Obrázek je mapa.",
                    "fix": "Českou mapu má postavit KARTOGRAF z dat (přečíst cizí mapu → postavit novou). "
                           "Vrstva textu je jen rychlá náhrada: popisky leží tam, kde byly anglické."})
    by_id = {el["id"]: el for el in texts["elements"]}
    for r in report:
        el = by_id[r["id"]]
        if r["residue"] > RESIDUE_WARN:
            out.append({"severity": "střední", "what": f"Po mazání zůstaly stopy textu „{el['en'][:40]}“ "
                                                       f"({round(100 * r['residue'])} % písma).",
                        "fix": "Zkontrolujte místo v obrázku; případně opravte rámeček v texty.json a vysázejte "
                               "znovu (zdarma)."})
        if r["too_long"]:
            out.append({"severity": "nízká", "what": f"„{el['cs'][:40]}“ je o hodně delší než původní text, "
                                                     f"písmo je zmenšené na {round(100 * MIN_SHRINK)} %.",
                        "fix": "Zkraťte překlad v texty.json a vysázejte znovu (zdarma)."})
    return out


def localize(image: Path, out_dir: Path, *, stem: str = "image-0", texts: dict | None = None,
             ask: Ask = claude.ask, model: str = READ_MODEL, effort: str = READ_EFFORT) -> dict:
    """Počeští obrázek. Bez `texts` čte Claude (placené, ~READ_USD), s `texts` zdarma.

    Zapíše `<stem>.png` (česky), `<stem>.svg` (upravitelné), `<stem>-bez-textu.png` a `<stem>.texty.json`.
    """
    image, out_dir = Path(image), Path(out_dir)
    try:
        with Image.open(image) as im:
            src = im.convert("RGB")
    except OSError as e:
        raise LocalizeError(f"obrázek nejde otevřít: {e}") from e
    cost = None
    if texts is None:
        texts, cost = read_texts(image, ask=ask, model=model, effort=effort)
    else:
        texts = normalize_texts(texts)
    if not texts["elements"]:
        raise LocalizeError("v obrázku není žádný text k počeštění")
    out_dir.mkdir(parents=True, exist_ok=True)
    clean, measured, mask_px = erase(np.array(src), texts["elements"])
    base_name = f"{stem}-bez-textu.png"
    Image.fromarray(clean).save(out_dir / base_name)
    png, svg, report = typeset(Image.fromarray(clean), texts["elements"], measured, base_name)
    png.save(out_dir / f"{stem}.png")
    (out_dir / f"{stem}.svg").write_text(svg, encoding="utf-8")
    (out_dir / f"{stem}.texty.json").write_text(json.dumps(texts, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"png": str(out_dir / f"{stem}.png"), "svg": str(out_dir / f"{stem}.svg"),
            "base": str(out_dir / base_name), "texts": str(out_dir / f"{stem}.texty.json"),
            "kind": texts["kind"], "elements": len(texts["elements"]), "mask_px": mask_px,
            "warnings": warnings_for(texts, report), "layout": report, "cost": cost, "size": list(src.size)}
