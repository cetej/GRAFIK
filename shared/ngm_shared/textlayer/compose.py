"""Složení vektorové vrstvy NG nad AI podkladem ve VectorCraftu.

Podklad (PNG bez textu) se otevře jako dokument; jeho vrstva se přejmenuje na
„AI podklad“ a zamkne. Nad ni přijdou vrstvy „Trasy a značky“ a „Popisky NG“.
Všechno informační je vektor: popisky, odkazové čáry, trasy se šipkou, značky,
legenda, severka, měřítko. Výsledek jde opravit bez nového renderu podkladu.

Pravidla (Resource Guide 04 Maps 2022):
- písmo, verzálky a barva podle druhu prvku (`style.FEATURES`),
- „type halo“ = tah v barvě pozadí POD znaky (str. 14), oblé spoje,
- odkazová čára začíná na hraně textu (s mezerou) a končí v cíli,
- poznámka („zánik ~1450“) leží těsně pod svým názvem, ne volně,
- popisek nad trasou se čte zleva doprava (str. 22: „Name is upside down“),
- měřítko jen na ortogonální mapě (`view: plan`) a jen z referenční vzdálenosti,
- číslice v písmech NeoGothic a Bumstead se sázejí Geographem (jejich 1 vypadá jako I),
- severka: písmeno S nad hrotem šipky.

Výstup `Composition` nese geometrii každého prvku pro deterministické kontroly
(`checks.py`).

Kopie z NG-ROBOT `ng_vector_labels/compose.py`, commit f27580e9534a408e35b153d06376e4d34697b092
(2026-10-29, GRAFIK fáze 3). Opravy z NG-ROBOT přenášej diffem originálu od tohoto commitu:
`git -C NG-ROBOT diff f27580e9 -- ng_vector_labels/compose.py`.
Změny proti originálu: jen importy (`ngm_shared.textlayer`).
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from ngm_shared.textlayer import style as st
from ngm_shared.textlayer.raster import Base
from ngm_shared.textlayer.vc_client import VectorCraft, VectorCraftError

logger = logging.getLogger(__name__)

MARKER_FILL = "#1A2A3A"
_DIGITS = re.compile(r"\d+")


# Silueta letadla shora (nos nahoru), jednotkový poloměr — značka letiště
AIRPLANE = [(0, -1), (0.13, -0.82), (0.13, -0.3), (0.95, 0.12), (0.95, 0.3), (0.13, 0.08), (0.1, 0.62),
            (0.36, 0.82), (0.36, 0.95), (0, 0.86), (-0.36, 0.95), (-0.36, 0.82), (-0.1, 0.62), (-0.13, 0.08),
            (-0.95, 0.3), (-0.95, 0.12), (-0.13, -0.3), (-0.13, -0.82)]


@dataclass
class Element:
    id: str
    type: str                     # header|label|note|marker|route|route_label|legend|north|scale|credit
    kind: str = ""
    text: str = ""
    bbox: tuple = (0.0, 0.0, 0.0, 0.0)   # x, y, w, h v bodech podkladu
    font: tuple = ()
    size: float = 0.0
    color: str = ""
    halo: Optional[str] = None
    halo_pad: float = 0.0
    parent: Optional[str] = None
    leader: Optional[list] = None        # [[x, y], [x, y]] začátek (hrana textu) → cíl
    point: Optional[list] = None         # bod prvku (značka, cíl)
    points: Optional[list] = None        # body trasy (absolutně)
    expect: Optional[str] = None         # water|land
    heading: Optional[str] = None
    digit_font: Optional[str] = None     # písmo, kterým se sázely číslice
    shifted: Optional[list] = None       # posun do bezpečného okraje [dx, dy]
    text_width: Optional[float] = None   # šířka textu na jednom řádku (text po křivce)
    path_len: Optional[float] = None     # délka křivky, po které text běží
    geo: bool = False                    # bod ze zeměpisných souřadnic (georef), ne odhad z obrázku
    footprint: Optional[list] = None     # text po křivce: čtverečky podél písma (bbox oblouku je skoro prázdný)
    vc_ids: list = field(default_factory=list)


@dataclass
class Composition:
    width: float
    height: float
    elements: list
    skipped: list                # [{id, reason}] — co se záměrně nekreslilo (např. měřítko v perspektivě)
    fonts: list                  # výstup text.fonts (status exact/substitute, missingGlyphs)
    server: dict

    def to_dict(self) -> dict:
        d = asdict(self)
        d["elements"] = [asdict(e) if isinstance(e, Element) else e for e in self.elements]
        return d


def _footprint(path: list, width: float, size: float) -> list:
    """Plocha textu po křivce jako řada čtverečků podél prvních `width` bodů dráhy.

    Obdélník kolem oblouku je skoro celý prázdný — kontrola kolizí by podle něj
    hlásila srážky s popisky, které text ve skutečnosti míjí.
    """
    half = 0.75 * size      # účaří leží na dráze, písmo nad ní i dotahy pod ní
    step = max(half, 1.0)
    boxes, run, nxt = [], 0.0, 0.0
    for a, b in zip(path, path[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        while seg > 0 and nxt <= run + seg and nxt <= width:
            t = (nxt - run) / seg
            x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            boxes.append((x - half, y - half, 2 * half, 2 * half))
            nxt += step
        run += seg
        if nxt > width:
            break
    return boxes


def _catmull(points: list) -> list:
    """Body trasy → kotvy s Bézierovými úchyty (hladká křivka přesně přes zadané body)."""
    out = []
    n = len(points)
    for i, (x, y) in enumerate(points):
        p0 = points[max(0, i - 1)]
        p2 = points[min(n - 1, i + 1)]
        tx, ty = (p2[0] - p0[0]) / 6.0, (p2[1] - p0[1]) / 6.0
        a = {"x": x, "y": y}
        if i > 0:
            a["in"] = [x - tx, y - ty]
        if i < n - 1:
            a["out"] = [x + tx, y + ty]
        out.append(a)
    return out


def _bezier_sample(points: list, per_seg: int = 16) -> list:
    """Hustá lomená čára po křivce z `_catmull` (pro délku, směr a popisek)."""
    anchors = _catmull(points)
    out = [[anchors[0]["x"], anchors[0]["y"]]]
    for a, b in zip(anchors, anchors[1:]):
        p0 = (a["x"], a["y"])
        p1 = tuple(a.get("out", p0))
        p3 = (b["x"], b["y"])
        p2 = tuple(b.get("in", p3))
        for k in range(1, per_seg + 1):
            t = k / per_seg
            mt = 1 - t
            out.append([mt ** 3 * p0[i] + 3 * mt * mt * t * p1[i] + 3 * mt * t * t * p2[i] + t ** 3 * p3[i]
                        for i in (0, 1)])
    return out


def _edge_point(bbox: tuple, target: tuple, gap: float) -> list:
    """Bod na hraně obdélníku (+ mezera) ve směru k cíli — odkud vede odkazová čára."""
    x, y, w, h = bbox
    cx, cy = x + w / 2, y + h / 2
    dx, dy = target[0] - cx, target[1] - cy
    if dx == 0 and dy == 0:
        return [cx, cy]
    tx = (w / 2) / abs(dx) if dx else math.inf
    ty = (h / 2) / abs(dy) if dy else math.inf
    t = min(tx, ty)
    ln = math.hypot(dx, dy)
    return [cx + dx * t + dx / ln * gap, cy + dy * t + dy / ln * gap]


def _utf8_spans(text: str, pattern: re.Pattern) -> list:
    """(začátek, konec) shod v bajtech UTF-8 — VectorCraft indexuje rozsahy textu po bajtech."""
    spans = []
    for m in pattern.finditer(text):
        start = len(text[:m.start()].encode("utf-8"))
        spans.append((start, start + len(m.group(0).encode("utf-8"))))
    return spans


class Composer:
    def __init__(self, vc: VectorCraft, base: Base, layout: dict):
        self.vc, self.base, self.lay = vc, base, layout
        self.W, self.H = float(base.width), float(base.height)
        self.s = st.scale_factor(self.W, layout.get("display_width") or st.DEFAULT_DISPLAY_WIDTH)
        self.margin = st.SAFE_MARGIN * min(self.W, self.H)
        self.elements: list[Element] = []
        self.skipped: list[dict] = []
        self.layers: dict = {}
        self.halo_modes: dict = {}           # kolik popisků dostalo žádné / jemné / plné halo (do zprávy)

    # ------------------------------------------------------------- pomůcky
    def abs(self, p) -> list:
        return [p[0] / 100.0 * self.W, p[1] / 100.0 * self.H]

    def bounds(self, oid: int) -> tuple:
        doc = self.vc.tool("inspect_document")
        stack = list(doc["layers"])
        while stack:
            n = stack.pop()
            if n.get("id") == oid:
                b = n["bounds"]
                return (b["x"], b["y"], b["width"], b["height"])
            stack.extend(n.get("children", []))
        raise VectorCraftError(f"Objekt {oid} chybí v dokumentu")

    def use_layer(self, name: str) -> None:
        self.vc.cmd("layer.setCurrent", id=self.layers[name])

    def text(self, content: str, fs: st.FeatureStyle, size: float, color: str, justify: str = "left"):
        """Vytvoří text (verzálky, prostrkání, číslice Geographem); vrací (id, písmo číslic)."""
        if fs.caps:
            content = content.upper()
        oid = self.vc.tool("add_text", text=content, font=fs.font[0], size=size, color=color, x=0, y=size)["id"]
        self.vc.cmd("text.setStyle", id=oid, style=fs.font[1], justify=justify, tracking=fs.tracking)
        if "\n" in content:
            # NG „7.5 on 7.5 leading“ (Resource Guide 04 Maps str. 18): řádkování = velikost písma;
            # výchozí ~1,2× dělalo dvouřádková jména rozvolněná (operátor 2026-10-13)
            self.vc.cmd("text.setStyle", id=oid, leading=size * st.LEADING)
        digit_font = None
        if fs.font[0] in st.DIGIT_UNSAFE_FONTS and _DIGITS.search(content):
            dstyle = "Bold" if fs.font[1] == "Heavy" else "Regular"
            for a, b in _utf8_spans(content, _DIGITS):
                self.vc.cmd("text.setRangeStyle", id=oid, start=a, end=b, font=st.GEO, style=dstyle)
            digit_font = f"{st.GEO} {dstyle}"
        return oid, digit_font

    def halo(self, oid: int, color: str, size: float, mode: str = "solid") -> float:
        """NG type halo: tah v barvě pozadí pod znaky, oblé spoje. Vrací přesah halo (body).

        `mode` (style.halo_mode): `none` bez hala, `soft` širší průsvitný tah
        rozostřený Gaussovým rozostřením (jen tah, ne písmo), `solid` tenký tah.
        """
        if mode == "none":
            return 0.0
        weight = max(1.0, size * st.HALO_WEIGHT * (1.5 if mode == "soft" else 0.8))
        self.vc.cmd("appearance.addStroke", ids=[oid])
        self.vc.cmd("appearance.setItem", ids=[oid], index=0, color=color, weight=weight,
                    **({"opacity": 60} if mode == "soft" else {}))
        self.vc.cmd("stroke.set", ids=[oid], join="round", cap="round")
        self.vc.cmd("appearance.moveItem", ids=[oid], **{"from": "contents", "to": 1})
        if mode == "soft":
            self.vc.cmd("effect.apply", ids=[oid], item=0, effect="blur.gaussian", params={"radius": weight * 0.6})
        return weight / 2

    def move_to(self, oid: int, left: float, top: float, clamp: bool = True):
        """Posune objekt levým horním rohem na (left, top); s `clamp` dovnitř bezpečného okraje."""
        x, y, w, h = self.bounds(oid)
        want = (left, top)
        if clamp:
            left = max(self.margin, min(left, self.W - w - self.margin))
            top = max(self.margin, min(top, self.H - h - self.margin))
        self.vc.tool("transform", ids=[oid], dx=left - x, dy=top - y)
        shift = [left - want[0], top - want[1]]
        return (left, top, w, h), (shift if max(abs(shift[0]), abs(shift[1])) > 1 else None)

    def style_text(self, oid: int, bbox: tuple, kind: str, size: float, override: Optional[str] = None,
                   halo: Optional[str] = None):
        """Barva podle pozadí pod textem + halo podle změřeného pozadí. Vrací (barva, barva halo, přesah)."""
        bg = self.base.bg_color(*bbox)
        color = st.pick_text_color(kind, bg, override)
        self.vc.cmd("text.setStyle", id=oid, fill=color)
        hcol = st.halo_color(color, bg)
        px = self.base.region_pixels(*bbox)
        std = float((px @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)).std()) if len(px) else 0.0
        if not halo and kind in st.WATER_KINDS:
            halo = "none"                     # modrý text se šedým halem nefunguje (operátor 2026-10-13)
        mode = st.halo_mode(color, bg, std, halo or self.lay.get("halo"))
        if mode == "none" and not halo and kind in st.LAND_WATER_KINDS:
            mode = "soft"                     # řeka na pevnině: zesvětlení vždy (operátor 2026-10-20)
        self.halo_modes[mode] = self.halo_modes.get(mode, 0) + 1
        return color, hcol, self.halo(oid, hcol, size, mode)

    def size_of(self, kind: str, override=None) -> float:
        return float(override) * self.s if override else st.feature(kind).size * self.s

    def line(self, pts: list, color: str, width: float, halo: Optional[str] = None, **stroke) -> list:
        ids = []
        if halo:
            hid = self.vc.tool("draw_path", points=pts, stroke=halo, fill="none", strokeWidth=width * 2.6)["id"]
            # lem bez hrotu: hrot roste s tloušťkou čáry a vedle šipky trčel bílý trojúhelník (2026-10-20)
            plain = {k: v for k, v in stroke.items() if k not in ("endArrow", "arrowAlign")}
            if plain:
                self.vc.cmd("stroke.set", ids=[hid], **plain)
            ids.append(hid)
        lid = self.vc.tool("draw_path", points=pts, stroke=color, fill="none", strokeWidth=width)["id"]
        if stroke:
            self.vc.cmd("stroke.set", ids=[lid], **stroke)
        ids.append(lid)
        return ids

    # ------------------------------------------------------------- prvky
    def place_label(self, lab: dict) -> None:
        kind = lab["kind"]
        fs = st.feature(kind)
        size = self.size_of(kind, lab.get("size"))
        px, py = self.abs(lab["at"])
        # `offset` (px při display_width) posune text vedle místa — bod místa zůstává pro kontroly.
        dx, dy = lab.get("offset") or (0, 0)
        x, y = px + dx * self.s, py + dy * self.s
        anchor = lab.get("anchor", "center")
        if lab.get("path"):
            self.place_path_label(lab, fs, size)
            return
        oid, dfont = self.text(lab["text"], fs, size, st.WHITE, justify=anchor)
        if kind == "peak" and "\n" in lab["text"]:
            # Kóta o stupeň menší než název a těsně pod ním: číslice Geographem jsou vyšší než kurzíva
            # Bumsteadu, při stejné velikosti vypadala kóta větší a mezera velká (operátor 2026-10-13)
            start = len(lab["text"].split("\n")[0].encode("utf-8")) + 1
            self.vc.cmd("text.setRangeStyle", id=oid, start=start, end=len(lab["text"].encode("utf-8")),
                        size=size * st.PEAK_ELEV_SCALE)
            self.vc.cmd("text.setStyle", id=oid, leading=size * st.PEAK_LEADING)
        if lab.get("modern_line") and "\n" in lab["text"]:
            # historická mapa: dnešní jméno pod historickým šedě a o stupeň menší („Panormos“ / „(Palermo)“)
            start = len(lab["text"].split("\n")[0].encode("utf-8")) + 1
            self.vc.cmd("text.setRangeStyle", id=oid, start=start, end=len(lab["text"].encode("utf-8")),
                        size=size * st.PEAK_ELEV_SCALE, fill=lab["modern_line"])
        if lab.get("tracking") is not None:          # roztažený název (cílový stát přes většinu území)
            self.vc.cmd("text.setStyle", id=oid, tracking=float(lab["tracking"]))
        _, _, w, h = self.bounds(oid)
        left = x - w / 2 if anchor == "center" else (x - w if anchor == "right" else x)
        bbox, shift = self.move_to(oid, left, y - h / 2)
        color, hcol, pad = self.style_text(oid, bbox, kind, size, lab.get("color"), lab.get("halo"))
        el = Element(lab["id"], "label", kind, lab["text"], bbox, fs.font, size, color, hcol, pad,
                     expect=lab.get("expect") or fs.expect, point=[px, py], digit_font=dfont, shifted=shift,
                     geo="at" in (lab.get("geo") or {}), vc_ids=[oid])
        self.elements.append(el)
        note = self.place_note(el, lab["note"], anchor) if lab.get("note") else None
        if lab.get("leader_to"):
            self.place_leader(el, self.abs(lab["leader_to"]), lab.get("leader_expect", "land"), note)

    def place_note(self, parent: Element, note: str, anchor: str) -> Element:
        fs = st.feature("annotation")
        # poznámka (výšková kóta) menší než název — ne obrácená hierarchie (operátor 2026-10-13)
        size = min(max(fs.size * self.s, parent.size * 0.72), parent.size * 0.85)
        oid, dfont = self.text(note, fs, size, st.WHITE, justify=anchor)
        _, _, w, h = self.bounds(oid)
        px, py, pw, ph = parent.bbox
        left = px + (pw - w) / 2 if anchor == "center" else (px + pw - w if anchor == "right" else px)
        bbox, shift = self.move_to(oid, left, py + ph + 0.1 * parent.size)   # těsně pod názvem (výšková kóta)
        color, hcol, pad = self.style_text(oid, bbox, "annotation", size)
        el = Element(f"{parent.id}__note", "note", "annotation", note, bbox, fs.font, size,
                     color, hcol, pad, parent=parent.id, digit_font=dfont, shifted=shift, vc_ids=[oid])
        self.elements.append(el)
        return el

    def place_leader(self, el: Element, target: list, expect: str, note: Optional[Element] = None) -> None:
        """Odkazová čára od hrany bloku název + poznámka (nikdy z rohu přes text) k cíli."""
        block = _union([el.bbox, note.bbox]) if note else el.bbox
        start = _edge_point(block, target, gap=0.35 * el.size + el.halo_pad)
        color = st.WHITE if st.luminance(st.hex_to_rgb(el.color)) > 0.5 else st.INK
        self.use_layer("Trasy a značky")
        ids = self.line([start, target], color, st.LEADER_WIDTH * self.s, halo=el.halo, cap="round")
        self.use_layer("Popisky NG")
        el.leader = [start, list(target)]
        el.vc_ids += ids
        self.elements.append(Element(f"{el.id}__leader", "leader", parent=el.id, point=list(target),
                                     expect=expect, vc_ids=ids))

    def place_path_label(self, lab: dict, fs: st.FeatureStyle, size: float) -> None:
        """Text po křivce (řeka, pohoří) — křivka zleva doprava, aby text nestál na hlavě."""
        pts = [self.abs(p) for p in lab["path"]]
        if pts[0][0] > pts[-1][0]:
            pts = pts[::-1]
        content = lab["text"].upper() if fs.caps else lab["text"]
        width = self.text_width(content, fs, size)
        path_len = _length(_bezier_sample(pts))
        pid = self.vc.tool("draw_path", points=_catmull(pts), stroke="none", fill="none")["id"]
        oid = self.vc.tool("add_text", text=content, font=fs.font[0], size=size, color=st.WHITE,
                           path=pid, mode="onPath")["id"]
        self.vc.cmd("text.setStyle", id=oid, style=fs.font[1],
                    tracking=float(lab["tracking"]) if lab.get("tracking") is not None else fs.tracking)
        bbox = self.bounds(oid)
        color, hcol, pad = self.style_text(oid, bbox, lab["kind"], size, lab.get("color"), lab.get("halo"))
        self.elements.append(Element(lab["id"], "label", lab["kind"], lab["text"], bbox, fs.font, size, color,
                                     hcol, pad, expect=lab.get("expect") or fs.expect, points=pts,
                                     text_width=width, path_len=path_len,
                                     footprint=_footprint(_bezier_sample(pts), width, size), vc_ids=[oid]))

    def place_marker(self, mk: dict) -> None:
        x, y = self.abs(mk["at"])
        kind = mk.get("kind", "town")
        if kind == "numbered":
            d = st.MARKER_DIAMETER * self.s
            cid = self.vc.tool("draw_shape", shape="ellipse", x=x - d / 2, y=y - d / 2, width=d, height=d,
                               fill=MARKER_FILL, stroke=st.WHITE, strokeWidth=1.2 * self.s)["id"]
            fs = st.feature("marker_number")
            size = d * 0.62
            tid, _ = self.text(str(mk.get("n") or ""), fs, size, st.WHITE, justify="center")
            _, _, w, h = self.bounds(tid)
            self.move_to(tid, x - w / 2, y - h / 2, clamp=False)
            ids, bbox = [cid, tid], (x - d / 2, y - d / 2, d, d)
        elif kind == "peak":
            # vrchol = rovný křížek „+“ (operátor 2026-10-20), ne trojúhelník
            r = st.PEAK_CROSS / 2 * self.s
            ink, w = mk.get("color") or st.INK, st.PEAK_CROSS_LINE * self.s
            ids = (self.line([[x - r, y], [x + r, y]], ink, w, cap="butt")
                   + self.line([[x, y - r], [x, y + r]], ink, w, cap="butt"))
            bbox = (x - r, y - r, 2 * r, 2 * r)
        elif kind == "airport":
            # Letiště: silueta letadla (nos k severovýchodu), tmavá s bílým lemem
            r = st.AIRPORT_SPOT * self.s / 2
            ca, sa = math.cos(math.radians(45)), math.sin(math.radians(45))
            pts = [[x + r * (px * ca - py * sa), y + r * (px * sa + py * ca)] for px, py in AIRPLANE]
            cid = self.vc.tool("draw_path", points=pts, closed=True, fill=mk.get("color") or st.INK,
                               stroke=st.WHITE, strokeWidth=0.7 * self.s)["id"]
            ids, bbox = [cid], (x - r, y - r, 2 * r, 2 * r)
        elif kind == "capital":
            # Hlavní město: NG černá hvězdička (připomínka operátora 2026-10-13)
            r = st.CAPITAL_STAR * self.s / 2
            cid = self.vc.tool("draw_shape", shape="star", cx=x, cy=y, radius1=r, radius2=r * 0.45, points=5,
                               fill=mk.get("color") or st.INK, stroke=st.WHITE, strokeWidth=0.8 * self.s)["id"]
            ids, bbox = [cid], (x - r, y - r, 2 * r, 2 * r)
        else:
            d = st.TOWN_SPOT * float(mk.get("scale") or 1.0) * self.s       # tečka podle velikosti sídla
            cid = self.vc.tool("draw_shape", shape="ellipse", x=x - d / 2, y=y - d / 2, width=d, height=d,
                               fill=mk.get("color") or st.INK, stroke=st.WHITE, strokeWidth=0.8 * self.s)["id"]
            ids, bbox = [cid], (x - d / 2, y - d / 2, d, d)
        self.elements.append(Element(mk["id"], "marker", kind, str(mk.get("n") or ""), bbox,
                                     font=(st.GEO, "Bold") if kind == "numbered" else (),
                                     point=[x, y], expect=mk.get("expect", "land"),
                                     geo="at" in (mk.get("geo") or {}), vc_ids=ids))

    def place_route(self, rt: dict) -> None:
        pts = [self.abs(p) for p in rt["points"]]
        color = rt.get("color") or st.ACCENT
        width = st.ROUTE_WIDTH * self.s
        stroke = {"cap": "round", "join": "round", "endArrow": "Triangle", "arrowAlign": "tip"}
        if rt.get("dashed"):
            stroke["dash"] = [width * 3, width * 2]
        bg = self.base.bg_color(*_bbox_of(pts))
        ids = self.line(_catmull(pts), color, width, halo=st.halo_color(color, bg), **stroke)
        dense = _bezier_sample(pts)
        self.elements.append(Element(rt["id"], "route", "route", rt.get("label") or "", _bbox_of(dense),
                                     color=color, points=dense, heading=rt.get("heading"), vc_ids=ids))
        if rt.get("label"):
            self.place_route_label(rt, dense)

    def text_width(self, content: str, fs: st.FeatureStyle, size: float) -> float:
        """Šířka textu v jednom řádku (dočasný bodový text, hned smazaný)."""
        oid = self.vc.tool("add_text", text=content, font=fs.font[0], size=size, x=0, y=size)["id"]
        self.vc.cmd("text.setStyle", id=oid, style=fs.font[1], tracking=fs.tracking)
        width = self.bounds(oid)[2]
        self.vc.cmd("edit.clear", ids=[oid])
        return width

    def place_route_label(self, rt: dict, dense: list) -> None:
        """Popisek nad trasou, po jejím nejbližším úseku kolem `label_at`, čtený zleva doprava.

        Text po křivce se za jejím koncem tiše usekne — proto se šířka nejdřív změří
        a úsek trasy se rozšiřuje, dokud odsazená křivka (na vnitřní straně oblouku je
        kratší než trasa) nemá aspoň 1,15× šířku textu. Skutečná délka jde do zprávy
        (`path_len`) a kontrola `overflow` ji porovná se šířkou.
        """
        fs = st.feature("annotation")
        size = fs.size * self.s * 1.1
        width = self.text_width(rt["label"], fs, size)
        cum = [0.0]
        for a, b in zip(dense, dense[1:]):
            cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        total = cum[-1]
        if total < width:
            self.skipped.append({"id": rt["id"] + "__label", "reason": "trasa je kratší než její popisek"})
            return
        off = 0.55 * size + st.ROUTE_WIDTH * self.s * 2
        window = width * 1.25
        while True:
            window = min(window, total)
            mid = min(max(total * float(rt.get("label_at", 0.5)), window / 2), total - window / 2)
            seg = [p for p, c in zip(dense, cum) if mid - window / 2 <= c <= mid + window / 2]
            if seg[0][0] > seg[-1][0]:
                seg = seg[::-1]
            shifted = _offset(seg, off)
            path_len = _length(shifted)
            if path_len >= width * 1.15 or window >= total:
                break
            window *= 1.2
        pid = self.vc.tool("draw_path", points=shifted, stroke="none", fill="none")["id"]
        oid = self.vc.tool("add_text", text=rt["label"], font=fs.font[0], size=size, color=st.WHITE,
                           path=pid, mode="onPath")["id"]
        self.vc.cmd("text.setStyle", id=oid, style=fs.font[1])
        bbox = self.bounds(oid)
        color, hcol, pad = self.style_text(oid, bbox, "annotation", size, rt.get("label_color"))
        el = Element(rt["id"] + "__label", "route_label", "annotation", rt["label"], bbox, fs.font,
                     size, color, hcol, pad, parent=rt["id"], text_width=width, path_len=path_len,
                     footprint=_footprint(shifted, width, size), vc_ids=[oid])
        self.elements.append(el)

    def place_header(self, head: dict) -> None:
        x, y = self.abs(head["at"])
        fs = st.feature("title")
        size = self.size_of("title", head.get("size"))
        left = head.get("align") == "left"          # vlevo na prapor: `at` = levý horní roh bloku
        oid, dfont = self.text(head["title"], fs, size, st.WHITE, justify="left" if left else "center")
        _, _, w, h = self.bounds(oid)
        bbox, shift = self.move_to(oid, x if left else x - w / 2, y)
        color, hcol, pad = self.style_text(oid, bbox, "title", size, head.get("color"))
        title = Element("header_title", "header", "title", head["title"], bbox, fs.font, size, color, hcol, pad,
                        digit_font=dfont, shifted=shift, vc_ids=[oid])
        self.elements.append(title)
        if head.get("subtitle"):
            fs2 = st.feature("subtitle")
            size2 = self.size_of("subtitle")
            sid, dfont2 = self.text(head["subtitle"], fs2, size2, st.WHITE, justify="left" if left else "center")
            if "\n" in head["subtitle"]:
                self.vc.cmd("text.setStyle", id=sid, leading=size2 * 1.15)
            _, _, w2, _ = self.bounds(sid)
            bbox2, shift2 = self.move_to(sid, bbox[0] if left else x - w2 / 2, bbox[1] + bbox[3] + 0.3 * size2)
            c2, h2, p2 = self.style_text(sid, bbox2, "subtitle", size2, head.get("color"))
            self.elements.append(Element("header_subtitle", "header", "subtitle", head["subtitle"], bbox2, fs2.font,
                                         size2, c2, h2, p2, parent="header_title", digit_font=dfont2,
                                         shifted=shift2, vc_ids=[sid]))

    def place_legend(self, leg: dict) -> None:
        x, y = self.abs(leg["at"])
        top = y
        ids, parts = [], []
        if leg.get("title"):
            fs = st.feature("legend_title")
            size = fs.size * self.s
            oid, _ = self.text(leg["title"], fs, size, st.WHITE)
            bbox, _ = self.move_to(oid, x, top)
            self.style_text(oid, bbox, "legend_title", size)
            ids.append(oid)
            parts.append(bbox)
            top = bbox[1] + bbox[3] + 0.5 * size
        fs = st.feature("legend_entry")
        size = fs.size * self.s
        d = st.MARKER_DIAMETER * self.s * 0.85
        for e in leg["entries"]:
            cy = top + d / 2
            if e.get("n"):
                self.place_marker({"id": f"legend_{e['n']}", "n": e["n"], "kind": "numbered",
                                   "at": [(x + d / 2) / self.W * 100, cy / self.H * 100]})
                m = self.elements.pop()
                ids += m.vc_ids
                parts.append(m.bbox)
            oid, _ = self.text(e["text"], fs, size, st.WHITE)
            _, _, w, h = self.bounds(oid)
            bbox, _ = self.move_to(oid, x + d * 1.5, cy - h / 2)
            self.style_text(oid, bbox, "legend_entry", size)
            ids.append(oid)
            parts.append(bbox)
            top = max(top + d, bbox[1] + bbox[3]) + 0.45 * size
        text = " | ".join(f"{e.get('n') or ''} {e['text']}".strip() for e in leg["entries"])
        self.elements.append(Element("legend", "legend", "legend", text, _union(parts), fs.font, size, vc_ids=ids))

    def place_north(self, north: dict) -> None:
        x, y = self.abs(north["at"])
        h = 24 * self.s
        w = 9 * self.s
        tip = [x, y - h / 2]
        pts = [tip, [x + w / 2, y + h / 2], [x, y + h / 3], [x - w / 2, y + h / 2]]
        bg = self.base.bg_color(x - w, y - h / 2, 2 * w, h)
        color = st.pick_text_color("north", bg)
        hcol = st.halo_color(color, bg)
        aid = self.vc.tool("draw_path", points=pts, closed=True, fill=color, stroke=hcol,
                           strokeWidth=1.5 * self.s)["id"]
        fs = st.feature("north")
        size = fs.size * self.s
        oid, _ = self.text("S", fs, size, color, justify="center")
        _, _, tw, th = self.bounds(oid)
        bbox, _ = self.move_to(oid, x - tw / 2, tip[1] - th - 0.35 * size, clamp=False)
        self.vc.cmd("text.setStyle", id=oid, fill=color)
        pad = self.halo(oid, hcol, size)
        self.elements.append(Element("north", "north", "north", "S", _union([bbox, _bbox_of(pts)]), fs.font, size,
                                     color, hcol, pad, point=tip, vc_ids=[aid, oid],
                                     points=[[bbox[0], bbox[1] + bbox[3]], tip]))

    def place_scale(self, sc: dict) -> None:
        if self.lay.get("view") != "plan":
            self.skipped.append({"id": "scale", "reason": "perspektivní nebo neurčený pohled — měřítko se mění"})
            return
        ref = sc.get("ref") or {}
        try:
            a, b = self.abs(ref["a"]), self.abs(ref["b"])
            per_km = math.hypot(b[0] - a[0], b[1] - a[1]) / float(ref["km"])
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            self.skipped.append({"id": "scale", "reason": "chybí referenční vzdálenost (ref.a, ref.b, ref.km)"})
            return
        km = float(sc.get("km") or 0) or _nice_km(st.SCALE_MAX_FRAC * self.W / per_km)
        length = km * per_km
        fs = st.feature("scale")
        size = st.scale_text_size(self.lay.get("labels")) * self.s     # nikdy větší než názvy na mapě
        unit_size = size * 0.9                     # NG: čísla Geograph Edit 5 pt, „km“ 4,5 pt
        lw = st.SCALE_LINE * self.s
        tick = st.SCALE_TICK * self.s
        # Čára s dílky jen na koncích, „0“ nad levým dílkem, délka nad pravým, jednotka za ní.
        unit_w = self.text_width(" km", fs, unit_size)
        last_w = self.text_width(f"{km:g}", fs, size)
        x, y = self.abs(sc["at"])
        first_w = self.text_width("0", fs, size)
        x = max(self.margin + first_w / 2 + 1, min(x, self.W - self.margin - length - last_w / 2 - unit_w))
        y = min(max(y, self.margin + tick + 1.6 * size), self.H - self.margin - lw)
        bg = self.base.bg_color(x, y - 1.8 * size, length, 2 * size)
        light = st.luminance(bg) > 0.35
        color = st.SCALE_INK if light else st.SCALE_INK_ON_DARK          # úsečka
        tcol = st.SCALE_TEXT if light else st.SCALE_TEXT_ON_DARK        # čísla a jednotka
        hcol = st.halo_color(tcol, bg)
        # jedna lomená čára (dílek – čára – dílek), bez halo: nesvítí
        ids = self.line([[x, y - tick], [x, y], [x + length, y], [x + length, y - tick]], color, lw,
                        join="miter", cap="butt")
        parts = []
        top = y - tick - 0.25 * size
        for frac, lab in ((0, "0"), (1, f"{km:g}")):
            tx = x + length * frac
            oid, _ = self.text(lab, fs, size, tcol, justify="center")
            w, h = self.bounds(oid)[2], self.bounds(oid)[3]
            bbox, _ = self.move_to(oid, tx - w / 2, top - h, clamp=False)
            self.halo(oid, hcol, size)
            ids.append(oid)
            parts.append(bbox)
        oid, _ = self.text("km", fs, unit_size, tcol)
        uh = self.bounds(oid)[3]
        last = parts[-1]
        bbox, _ = self.move_to(oid, last[0] + last[2] + 0.25 * size, last[1] + last[3] - uh, clamp=False)
        self.halo(oid, hcol, unit_size)
        ids.append(oid)
        parts.append(bbox)
        self.elements.append(Element("scale", "scale", "scale", f"{km:g} km", _union(parts + [(x, y - tick, length,
                                                                                             tick + lw)]),
                                     fs.font, size, tcol, hcol, vc_ids=ids))

    def place_credit(self, cr: dict) -> None:
        fs = st.feature("credit")
        size = fs.size * self.s
        x, y = self.abs(cr["at"])
        oid, _ = self.text(cr["text"], fs, size, st.WHITE)
        _, _, w, h = self.bounds(oid)
        bbox, shift = self.move_to(oid, x - w / 2, y)
        color, hcol, pad = self.style_text(oid, bbox, "credit", size)
        self.elements.append(Element("credit", "credit", "credit", cr["text"], bbox, fs.font, size, color, hcol, pad,
                                     shifted=shift, vc_ids=[oid]))

    def place_scale_note(self, text: str) -> None:
        """Místo měřítka tam, kde se mění (šikmý pohled): NG „Scale varies in this perspective“."""
        fs = st.feature("scale")
        size = fs.size * self.s
        oid, _ = self.text(text, fs, size, st.WHITE)
        _, _, w, h = self.bounds(oid)
        at = self.lay.get("scale_note_at")              # volné místo vybrané auto_labels (vpravo dole, jinak vlevo)
        if at:
            x, y = self.abs(at)
            left, top = (x - w if at[0] > 50 else x), y - h
        else:
            left, top = self.margin, self.H - self.margin - h
        bbox, shift = self.move_to(oid, left, top)
        color, hcol, pad = self.style_text(oid, bbox, "scale", size)
        self.elements.append(Element("scale_note", "credit", "scale", text, bbox, fs.font, size, color, hcol, pad,
                                     shifted=shift, vc_ids=[oid]))

    # ------------------------------------------------------------- celé složení
    def run(self) -> None:
        doc = self.vc.tool("inspect_document")
        base_layer = doc["layers"][0]["id"]
        self.vc.cmd("layer.setProps", id=base_layer, name="AI podklad", locked=True)
        self.layers["Trasy a značky"] = self.vc.cmd("layer.new", name="Trasy a značky", top=True)["id"]
        for rt in self.lay.get("routes") or []:
            self.place_route(rt)
        for mk in self.lay.get("markers") or []:
            self.place_marker(mk)
        self.layers["Popisky NG"] = self.vc.cmd("layer.new", name="Popisky NG", top=True)["id"]
        if self.lay.get("header"):
            self.place_header(self.lay["header"])
        for lab in self.lay.get("labels") or []:
            self.place_label(lab)
        if self.lay.get("legend"):
            self.place_legend(self.lay["legend"])
        if self.lay.get("north"):
            self.place_north(self.lay["north"])
        if self.lay.get("scale"):
            self.place_scale(self.lay["scale"])
        if self.lay.get("credit"):
            self.place_credit(self.lay["credit"])
        if self.lay.get("scale_note"):
            self.place_scale_note(self.lay["scale_note"])


def _bbox_of(pts: list) -> tuple:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def _offset(seg: list, off: float) -> list:
    """Lomená čára posunutá o `off` doleva od směru (při čtení zleva doprava = nad ní)."""
    out = []
    for i, p in enumerate(seg):
        a, b = seg[max(0, i - 1)], seg[min(len(seg) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(dx, dy) or 1.0
        out.append([p[0] + dy / ln * off, p[1] - dx / ln * off])
    return out


def _length(pts: list) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def _union(boxes: list) -> tuple:
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return (x0, y0, x1 - x0, y1 - y0)


def _nice_km(km: float) -> float:
    """Zaokrouhlí délku měřítka na 1, 2 nebo 5 × 10^n km."""
    if km <= 0:
        return 1.0
    exp = 10 ** math.floor(math.log10(km))
    for m in (5, 2, 1):
        if km >= m * exp:
            return m * exp
    return exp


def compose(base_path, layout: dict, out_stem, *, vc: Optional[VectorCraft] = None) -> Composition:
    """Složí vrstvu a uloží `<out_stem>.vectorcraft/.pdf/.svg/.png/.ai`. `layout` musí projít `layout.normalize`."""
    base_path, out_stem = Path(base_path), Path(out_stem)
    base = Base(base_path)
    own = vc is None
    vc = vc or VectorCraft()
    try:
        vc.tool("open_file", path=str(base_path))
        comp = Composer(vc, base, layout)
        comp.run()
        fonts = vc.cmd("text.fonts")
        vc.tool("save_file", path=str(out_stem.with_suffix(".vectorcraft")))
        vc.tool("export", path=str(out_stem.with_suffix(".pdf")))
        vc.tool("export", path=str(out_stem.with_suffix(".svg")), outlineText=True)
        vc.tool("export", path=str(out_stem.with_suffix(".png")))
        vc.cmd("file.saveCopy", path=str(out_stem.with_suffix(".ai")), format="ai")    # pro Illustrator
        # skutečné hranice po složení (halo, přesuny) — kontroly čtou tyhle
        doc = vc.tool("inspect_document")
        live = {}
        stack = list(doc["layers"])
        while stack:
            n = stack.pop()
            if n.get("bounds") and n.get("id") is not None:      # prázdná vrstva má bounds null
                b = n["bounds"]
                live[n["id"]] = (b["x"], b["y"], b["width"], b["height"])
            stack.extend(n.get("children", []))
        for el in comp.elements:
            if el.type in ("label", "note", "header", "route_label", "credit") and el.vc_ids and el.vc_ids[0] in live:
                el.bbox = live[el.vc_ids[0]]
        return Composition(comp.W, comp.H, comp.elements, comp.skipped,
                           fonts if isinstance(fonts, list) else [], dict(vc.server))
    finally:
        if own:
            vc.close()
