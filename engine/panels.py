"""Dokument s panely (krok 3c): volný formát, víc obrazů, popisky na bodech modelu.

library/infographics/<id>/info.json        dokument se `schema_version: 2` a `panels`
library/infographics/<id>/panely/<panel>/  kopie renderu: obraz.png, body.json, vrstva-*.png; orez/ jsou z nich odvozené obrázky

Starý dokument bez `schema_version` kreslí Studio (`InfoSvg`) a nic se na něm nemění. Panelový kreslí Engine, protože ho musí
umět i bez prohlížeče: řetězec z tématu, přeformátování (3d), varianta (3e). Náhled je stejná funkce jako export, liší se jen tím,
že obrázky odkazuje místo vložení. Horní <g id> = vrstva VectorCraftu, <g id> uvnitř = pojmenovaná skupina: Grafika drží každý
objekt zvlášť, Texty každý popisek zvlášť. Vzor je `scripts/3d/pantheon_plakat.py`, zásady `docs/infografiky-zasady.md`.

Obraz se v panelu nikdy neořízne (zmenší se celý). Popisek míří na název z `body.json`, nebo na bod [x, y, z] v metrech, který
se promítne přes `origin` a `basis`, takže sedí na model i po přeskládání. `poradi` je důležitost panelu.
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import shutil
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from engine.infographics import InfoError, canvas_size, clean_svg

SCHEMA = 2
URCENI = ("web", "tisk")     # tisková příloha se čte z papíru, kontrola mobilu pro ni neplatí (operátor 2. 11.)
KINDS = ("obraz", "fakta", "text", "osa", "kresba")
THEMES = {"dark": {"bg": "#1d2532", "ink": "#f1ede4", "muted": "#a7b1bf", "foot": "#8b95a4", "lead": "#ffffff", "halo": "#000000", "zar": "#3b4c68"},
          "light": {"bg": "#f2f3f5", "ink": "#1d1f23", "muted": "#5d636b", "foot": "#6b7079", "lead": "#1d1f23", "halo": "#ffffff"},
          "ruda": {"bg": "#3a0c10", "ink": "#f6ebdf", "muted": "#d9b8a8", "foot": "#bd9a8e", "lead": "#ffffff", "halo": None, "stin": True}}
TEXT_SHADOW = ('<defs><filter id="stin-textu" x="-20%" y="-40%" width="140%" height="180%">'
               '<feDropShadow dx="0" dy="0" stdDeviation="4" flood-color="#000000" flood-opacity="0.75"/>'
               '<feDropShadow dx="1" dy="1.4" stdDeviation="1.2" flood-color="#000000" flood-opacity="0.85"/></filter></defs>')
FONT = "Bahnschrift, 'Roboto Condensed', 'Arial Narrow', sans-serif"
ALPHA_SOLID = 60            # obraz je obsazený od téhle průhlednosti, stín pod ním ne
MAX_EMPTY = 0.2             # největší prázdný obdélník pod titulkem, podíl plochy (motor s prázdným pruhem měl 36 %)
MIN_CONTRAST_THIN = 2.0     # kontrast tenké části obrazu proti stránce: mříž nemá plochu, vidět ji jen barva (tmavá kupole na tmavé stránce to nesplnila)
MIN_CONTRAST_MASS = 1.2     # velkou plochu nese její obrys, stačí méně (hnědý oblek na modré)
THIN_FILL = 0.2             # pod tímhle podílem plných pixelů je část tenká
FAINT_BANDS = 8
LINE_WIDTH = 0.47           # průměrná šířka znaku Bahnschrift semi-condensed v em, změřeno na patičce plakátu
# kopie prahů z studio/src/Infographics.tsx a docs/infografiky-zasady.md
MAX_LABELS = 10
MAX_LABEL_CHARS = 40
LEADER_MEDIAN_MAX = 0.06
LEADER_MAX = 0.12
PHONE_W, PHONE_MIN_PX = 360, 12        # stránka na telefonu, docs/infografiky-zasady.md, oddíl Web a mobil
PHONE_TITLE_PX, PHONE_HEADING_PX, PHONE_SOURCE_PX = 24, 18, 9
# písmo a mezery podle role, v jednotkách k = šířka / `jednotek`; dokument bez `pismo` je starý a kreslí se jako dřív
PLAKAT = {"jednotek": 1600, "titulek": 88, "titulek_x": 50, "titulek_y": 118, "podtitulek": 31, "podtitulek_od": 44, "podtitulek_krok": 38, "nadpis": 25, "cislo": 36, "vedouci": 26,
          "veta": 21, "popisek": 23, "pod": 22, "pod_maly": 20, "znacka": 18, "zdroj": 17, "zdroj_krok": 22, "zdroj_dole": 30, "okraj": 50, "osa_sloupec": 118, "zalomit": False, "vodidlo_median": LEADER_MEDIAN_MAX, "vodidlo_max": LEADER_MAX, "popisek_znaku": MAX_LABEL_CHARS}
# nový dokument: podíly šířky z tabulky v docs/infografiky-zasady.md. Při 546 jednotkách je 21 = 1/26 šířky, takže řádkování psané v k drží poměr k písmu
# popisek s vysvětlením je hlavní nositel textu; dlouhé vodítko na telefonu nevadí (přijatá Studna, 2. 11.), popisek u věci je větší než krátká čára
MOBIL = {**PLAKAT, "jednotek": 546, "titulek": 36.4, "titulek_x": 20, "titulek_y": 50, "podtitulek": 21, "podtitulek_od": 36, "podtitulek_krok": 26, "nadpis": 27.3, "cislo": 27.3, "vedouci": 22.75,
         "veta": 19.6, "popisek": 27.3, "pod": 21, "pod_maly": 19, "znacka": 19, "zdroj": 13.65, "zdroj_krok": 17, "zdroj_dole": 14, "okraj": 20, "osa_sloupec": None, "zalomit": True,
         "vodidlo_median": 0.4, "vodidlo_max": 0.8, "popisek_znaku": 70}
TITLE_WIDTH = 0.52          # šířka velkého tučného znaku v em i s prostrkáním, změřeno na ukázce Tesly
PANEL_ID = re.compile(r"[a-z0-9_]{1,40}")
FILE_NAME = re.compile(r"[\w\-]+\.(png|jpg|json)")
SVG_NS = "http://www.w3.org/2000/svg"


def is_panel_doc(doc: dict | None) -> bool:
    return bool(doc) and doc.get("schema_version") == SCHEMA


def fonts(doc: dict) -> dict:
    """Dokument si velikosti nese s sebou: změna tabulky hotovou stránku nezmění."""
    return {**PLAKAT, **(doc["pismo"] if isinstance(doc.get("pismo"), dict) else {})}


def heading_lines(text_: str, width: float, f: dict, k: float) -> list[str]:
    """Nadpis panelu: nová stránka ho zalomí do šířky panelu, stará ho kreslí na jeden řádek."""
    title = text_.upper()
    return wrap(title, int(width / (f["nadpis"] * k * TITLE_WIDTH))) or [title] if f["zalomit"] else [title]


def title_lines(doc: dict, f: dict, k: float, W: int) -> list[str]:
    title = doc["title"].upper()
    if not f["zalomit"]:
        return [title]
    size = (doc.get("nadpis") or {}).get("size", f["titulek"] * k)
    return wrap(title, int((W - 2 * f["okraj"] * k) / (size * TITLE_WIDTH))) or [title]


def _number(where: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InfoError(f"{where}: čekám číslo, ne {value!r}")
    return float(value)


def _numbers(where: str, value, count: int) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise InfoError(f"{where}: čekám {count} čísla")
    return [_number(where, v) for v in value]


def _lines(value) -> list[str]:
    return [str(v) for v in value] if isinstance(value, (list, tuple)) else ([str(value)] if value else [])


def _label(where: str, raw: dict) -> dict:
    if not isinstance(raw, dict) or not str(raw.get("text") or "").strip():
        raise InfoError(f"{where}: popisek potřebuje text")
    anchor = raw.get("kotva")
    if not isinstance(anchor, str) or not anchor:
        anchor = _numbers(f"{where}: kotva", anchor, 3)
    if raw.get("align", "left") not in ("left", "right"):
        raise InfoError(f"{where}: align je left nebo right")
    out = {"text": str(raw["text"]), "small": _lines(raw.get("small")), "kotva": anchor, "pos": _numbers(f"{where}: pos", raw.get("pos"), 2), "align": raw.get("align", "left")}
    if raw.get("size") is not None:
        out["size"] = _number(f"{where}: size", raw["size"])
    return out


def _mark(where: str, raw: dict) -> dict:
    if not isinstance(raw, dict) or not str(raw.get("text") or "").strip():
        raise InfoError(f"{where}: značka potřebuje text")
    anchor = raw.get("kotva")
    return {"text": str(raw["text"]), "kotva": anchor if isinstance(anchor, str) and anchor else _numbers(f"{where}: značka", anchor, 3)}


def _items(where: str, raw) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise InfoError(f"{where}: panel potřebuje položky")
    out = []
    for item in raw:
        if not isinstance(item, dict) or not (item.get("value") or item.get("text")):
            raise InfoError(f"{where}: položka potřebuje value nebo text")
        clean = {"value": str(item.get("value") or ""), "text": str(item.get("text") or "")}
        if item.get("x") is not None:
            clean["x"] = _number(where, item["x"])
        out.append(clean)
    return out


def _overlay(where: str, raw: dict) -> dict:
    kind = raw.get("typ") if isinstance(raw, dict) else None
    if kind == "krivka":
        return {"typ": kind, "body": str(raw.get("body") or ""), "carkovana": bool(raw.get("carkovana", True))}
    if kind == "usecka":
        return {"typ": kind, "od": raw.get("od"), "do": raw.get("do")}
    raise InfoError(f"{where}: překryv je krivka nebo usecka")


def _svg_fragment(fragment: str) -> str:
    """Kresba je cizí text jako každé schéma: projde stejným čištěním a vrátí se bez obalu."""
    root = ET.fromstring(clean_svg(f'<svg xmlns="{SVG_NS}">{fragment}</svg>'))
    return "".join(ET.tostring(child, encoding="unicode") for child in root).replace(f' xmlns:ns0="{SVG_NS}"', "").replace("ns0:", "")


def validate(doc: dict) -> list[dict]:
    """Panely, jen se známými poli. Co nejde nakreslit, je InfoError se jménem panelu."""
    size = canvas_size(doc.get("size"))
    if size is None:
        raise InfoError(f"neznámý formát {doc.get('size')!r}")
    W, H = size
    if doc.get("pismo") not in (None, "plakat") and (not isinstance(doc["pismo"], dict) or set(doc["pismo"]) - set(PLAKAT)):
        raise InfoError("pismo je „plakat“, nebo velikosti podle role jako panels.MOBIL")
    raw_panels = doc.get("panels")
    if not isinstance(raw_panels, list) or not raw_panels:
        raise InfoError("dokument nemá žádné panely")
    panels, seen = [], set()
    for i, raw in enumerate(raw_panels):
        pid = str(raw.get("id") or "") if isinstance(raw, dict) else ""
        if not PANEL_ID.fullmatch(pid):
            raise InfoError(f"panel {i + 1}: id {pid!r} musí být malá písmena bez diakritiky, číslice a podtržítka")
        if pid in seen:
            raise InfoError(f"panel {pid}: id se opakuje")
        seen.add(pid)
        if raw.get("typ") not in KINDS:
            raise InfoError(f"panel {pid}: typ je {', '.join(KINDS)}")
        rect = _numbers(f"panel {pid}: rect", raw.get("rect"), 4)
        if rect[2] <= 0 or rect[3] <= 0 or rect[0] < 0 or rect[1] < 0 or rect[0] + rect[2] > W + 0.5 or rect[1] + rect[3] > H + 0.5:
            raise InfoError(f"panel {pid}: rect {rect} je mimo plátno {W} × {H}")
        panel = {"id": pid, "typ": raw["typ"], "rect": rect, "poradi": int(_number(f"panel {pid}: poradi", raw.get("poradi", i + 1))), "nazev": str(raw.get("nazev") or pid), "fakta": _lines(raw.get("fakta")), "otazka": str(raw.get("otazka") or "")}
        if raw.get("k") is not None:
            panel["k"] = _number(f"panel {pid}: k", raw["k"])   # měřítko písma panelu po přeformátování (engine/reformat.py)
        if raw.get("titulek"):
            title = raw["titulek"] if isinstance(raw["titulek"], dict) else {"text": str(raw["titulek"])}
            panel["titulek"] = {"text": str(title.get("text") or ""), **{k: _number(f"panel {pid}: titulek", title[k]) for k in ("x", "y") if title.get(k) is not None}}
        if panel["typ"] == "obraz":
            panel["labels"] = [_label(f"panel {pid}", label) for label in raw.get("labels") or []]
            if isinstance(raw.get("zar"), dict):
                panel["zar"] = {key: _number(f"panel {pid}: zar", raw["zar"].get(key)) for key in ("x", "y", "r")}
            if raw.get("pruhledny"):
                panel["pruhledny"] = True
            layers = raw.get("vrstvy") or {}
            if not isinstance(layers, dict) or any(not PANEL_ID.fullmatch(str(k)) for k in layers):
                raise InfoError(f"panel {pid}: vrstvy jsou {{klíč souboru: název}}")
            panel["vrstvy"] = {str(k): str(v) for k, v in layers.items()}
            panel["prekryvy"] = [_overlay(f"panel {pid}", o) for o in raw.get("prekryvy") or []]
            panel["znacky"] = [_mark(f"panel {pid}", m) for m in raw.get("znacky") or []]
            if raw.get("pod"):
                panel["pod"] = {"text": str(raw["pod"].get("text") or ""), "small": str(raw["pod"].get("small") or "")}
            if raw.get("zdroj"):
                panel["zdroj"] = raw["zdroj"]
        elif panel["typ"] == "kresba":
            panel["kresba"] = _svg_fragment(str(raw.get("kresba") or ""))
            panel["texty"] = _svg_fragment(str(raw.get("texty") or ""))
            panel["viewbox"] = _numbers(f"panel {pid}: viewbox", raw.get("viewbox", rect), 4)
        else:
            panel["items"] = _items(f"panel {pid}", raw.get("items"))
            for key in ("size", "small_size", "krok", "sirka"):
                if raw.get(key) is not None:
                    panel[key] = _number(f"panel {pid}: {key}", raw[key])
            if panel["typ"] == "fakta" and raw.get("smer", "radek") not in ("radek", "sloupec"):
                raise InfoError(f"panel {pid}: smer je radek nebo sloupec")
            if panel["typ"] == "fakta":
                panel["smer"] = raw.get("smer", "radek")
            if panel["typ"] == "osa" and raw.get("pod_sebou"):
                panel["pod_sebou"] = True
        panels.append(panel)
    return panels


def wrap(text_: str, chars: int) -> list[str]:
    lines, cur = [], ""
    for word in text_.split():
        if cur and len(cur) + 1 + len(word) > chars:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return lines + [cur] if cur else lines


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _text(x, y, s, size, fill, weight=400, anchor="start", halo=None, spacing=0.0) -> str:
    extra = f' stroke="{halo}" stroke-width="{size * 0.16:.1f}" stroke-linejoin="round" paint-order="stroke"' if halo else ""
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size:.1f}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}"{ls}{extra}>{html.escape(s, quote=False)}</text>'


def footer(doc: dict, f: dict, k: float, W: int, H: int) -> tuple[list[str], float]:
    """Řádky patičky a účaří prvního z nich. Nová stránka nese jen povinné označení AI, zdroje jdou pod článek (operátor 2. 11.)."""
    note = doc.get("na_strance", "") if f["zalomit"] else f"{'Zdroj: ' + doc['sources'] + ' ' if doc.get('sources') else ''}{doc['ai_note']}"
    lines = wrap(note, round((W - 2 * f["okraj"] * k) / (f["zdroj"] * k * LINE_WIDTH)))
    return lines, doc.get("paticka_y") or H - f["zdroj_dole"] * k - (len(lines) - 1) * f["zdroj_krok"] * k


def axis_gap(panel: dict, f: dict, k: float, size: float) -> float:
    """Sloupec letopočtů na ose: starý dokument má pevný, nový podle nejdelší hodnoty."""
    return panel.get("sirka", f["osa_sloupec"] * k if f["osa_sloupec"] else max(len(i["value"]) for i in panel["items"]) * size * LINE_WIDTH * 1.1)


def panel_dir(root: Path, panel_id: str) -> Path:
    return root / "panely" / panel_id


def body_of(root: Path, panel: dict) -> dict:
    return json.loads((panel_dir(root, panel["id"]) / "body.json").read_text(encoding="utf-8"))


def placement(panel: dict, info: dict) -> dict:
    """Celý obraz do rámce panelu, na střed, bez ořezu."""
    x, y, w, h = panel["rect"]
    res_w, res_h = info["res"]
    k = min(w / res_w, h / res_h)
    return {"x": x + (w - res_w * k) / 2, "y": y + (h - res_h * k) / 2, "k": k, "info": info}


def to_page(place: dict, where, panel_id: str = "") -> tuple[float, float]:
    info = place["info"]
    if isinstance(where, str):
        if where not in info["points"]:
            raise InfoError(f"panel {panel_id}: bod {where!r} v body.json není")
        u, v = info["points"][where]
    else:
        ox, oy = info["origin"]
        b = info["basis"]
        u = ox + b["x"][0] * where[0] + b["y"][0] * where[1] + b["z"][0] * where[2]
        v = oy + b["x"][1] * where[0] + b["y"][1] * where[1] + b["z"][1] * where[2]
    return place["x"] + u * place["k"], place["y"] + v * place["k"]


def leader_points(label: dict, place: dict, size: float, panel_id: str = "") -> list[tuple[float, float]]:
    """Od kotvy k textu: rovně, když je to skoro svisle nebo vodorovně, jinak jednou zalomené, svisle od věci a vodorovně k textu."""
    ax, ay = to_page(place, label["kotva"], panel_id)
    px, py = label["pos"]
    end = px - 8 if label["align"] == "left" else px + 8
    ly = py + size * 0.72
    return [(ax, ay), (end, ly)] if abs(ay - ly) < 8 or abs(ax - end) < 8 else [(ax, ay), (ax, ly), (end, ly)]


class Sheet:
    """Kde na stránce je volno: mřížka obsazených buněk s rychlým dotazem na obdélník. Obraz obsazuje jen tam, kde není průhledný."""
    CELL = 6

    def __init__(self, W: int, H: int):
        self.W, self.H = W, H
        self.grid = np.zeros((H // self.CELL + 2, W // self.CELL + 2), dtype=np.int32)
        self.solid = self.grid
        self.sums = None

    def add_box(self, box: tuple) -> None:
        x, y, w, h = (int(v) // self.CELL for v in box)
        self.grid[max(0, y):y + h + 2, max(0, x):x + w + 2] = 1
        self.sums = None

    def over_object(self, poly: list[tuple]) -> int:
        """Kolik bodů vodítka vede přes obraz mimo jeho konec: čára přes cizí část obrazu mate."""
        hits = 0
        for a, b in panels._segments(poly):
            for i in range(25):
                x, y = a[0] + (b[0] - a[0]) * i / 24, a[1] + (b[1] - a[1]) * i / 24
                row, col = int(y) // self.CELL, int(x) // self.CELL
                hits += int(0 <= row < self.solid.shape[0] and 0 <= col < self.solid.shape[1] and self.solid[row, col])
        return hits

    def add_picture(self, rect: tuple, alpha: Image.Image | None) -> None:
        x, y, w, h = rect
        cols, rows = max(1, int(w) // self.CELL), max(1, int(h) // self.CELL)
        if alpha is None:
            mask = np.ones((rows, cols), dtype=np.int32)
        else:
            solid = alpha.point(lambda v: 255 if v > ALPHA_SOLID else 0)       # tenké části (mříž, výboj) se průměrem neztratí
            mask = (np.asarray(solid.resize((cols, rows), Image.BOX), dtype=np.int32) > 8).astype(np.int32)
        top, left = max(0, int(y) // self.CELL), max(0, int(x) // self.CELL)
        rows, cols = min(rows, self.grid.shape[0] - top), min(cols, self.grid.shape[1] - left)
        self.grid[top:top + rows, left:left + cols] |= mask[:rows, :cols]
        self.solid = self.grid.copy()
        self.sums = None

    def free(self, box: tuple) -> bool:
        if self.sums is None:
            sums = np.zeros((self.grid.shape[0] + 1, self.grid.shape[1] + 1), dtype=np.int64)
            sums[1:, 1:] = self.grid.cumsum(0).cumsum(1)
            self.sums = sums.tolist()       # skladba se ptá stotisíckrát, seznam je tu rychlejší než pole
        x, y, w, h = box
        if x < 0 or y < 0 or x + w > self.W or y + h > self.H:
            return False
        x0, y0, x1, y1 = int(x) // self.CELL, int(y) // self.CELL, int(x + w) // self.CELL + 1, int(y + h) // self.CELL + 1
        s = self.sums
        return s[y1][x1] - s[y0][x1] - s[y1][x0] + s[y0][x0] == 0

    def largest_empty(self, top: float, bottom: float, margin: float) -> float:
        """Největší prázdný obdélník v ploše pod titulkem jako podíl té plochy. Vidí prázdný pruh i prázdnou třetinu stránky."""
        r0, r1 = int(top) // self.CELL + 1, int(bottom) // self.CELL
        c0, c1 = int(margin) // self.CELL, int(self.W - margin) // self.CELL
        rows = self.grid[r0:r1, c0:c1].tolist()
        if not rows or not rows[0]:
            return 0.0
        heights = [0] * (c1 - c0)
        best = 0
        for row in rows:
            heights = [0 if cell else h + 1 for cell, h in zip(row, heights)]
            stack: list[tuple[int, int]] = []
            for col, h in enumerate([*heights, 0]):
                start = col
                while stack and stack[-1][1] >= h:
                    start, tall = stack.pop()
                    best = max(best, tall * (col - start))
                stack.append((start, h))
        return best / ((r1 - r0) * (c1 - c0))


class Renderer:
    """SVG dokumentu. `href(panel, soubor)` dá odkaz pro náhled ve Studiu; bez něj se obrázky vloží a SVG jde do exportu."""

    def __init__(self, doc: dict, root: Path, href=None):
        self.doc, self.root, self.href = doc, root, href
        self.W, self.H = canvas_size(doc["size"])
        self.f = fonts(doc)
        self.k = doc.get("meritko") or self.W / self.f["jednotek"]
        self.t = THEMES.get(doc.get("template"), THEMES["dark"])
        self.accent = doc.get("accent") or "#dcb062"
        self.ids: set[str] = set()

    def gid(self, name: str) -> str:
        """Skupina ve VectorCraftu: stejný název dvakrát by v jedné vrstvě nešel rozlišit."""
        unique, n = name, 2
        while unique in self.ids:
            unique, n = f"{name} {n}", n + 1
        self.ids.add(unique)
        return _esc(unique)

    def image(self, panel: dict, file: str, x: float, y: float, w: float, h: float) -> str:
        path = panel_dir(self.root, panel["id"]) / "orez" / file
        if self.href:
            href = self.href(panel["id"], file)
        else:
            kind = "jpeg" if path.suffix == ".jpg" else "png"
            href = f"data:image/{kind};base64," + base64.b64encode(path.read_bytes()).decode()
        return f'<image href="{href}" x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}"/>'

    def _flat(self, panel: dict, place: dict) -> str:
        """Jeden kus, sloučený na barvu stránky."""
        d = panel_dir(self.root, panel["id"])
        out = d / "orez" / f"plocha-{self.t['bg'][1:]}.jpg"
        with Image.open(d / "obraz.png") as im:
            size = im.size
            if not out.exists():
                out.parent.mkdir(exist_ok=True)
                rgba = im.convert("RGBA")
                back = Image.new("RGBA", rgba.size, tuple(int(self.t["bg"][i:i + 2], 16) for i in (1, 3, 5)) + (255,))
                tmp = out.with_suffix(".tmp.jpg")
                Image.alpha_composite(back, rgba).convert("RGB").save(tmp, "JPEG", quality=92)
                os.replace(tmp, out)
        return self.image(panel, out.name, place["x"], place["y"], size[0] * place["k"], size[1] * place["k"])

    def _see_through(self, panel: dict, place: dict) -> str:
        """Obraz s průhledností, volitelně na světle za objektem: tmavý model by na tmavé stránce zmizel a rámeček by byl vidět."""
        d = panel_dir(self.root, panel["id"])
        out = d / "orez" / "pruhledny.png"
        if not out.exists():
            out.parent.mkdir(exist_ok=True)
            shutil.copy2(d / "obraz.png", out)
        with Image.open(out) as im:
            size = im.size
        picture = self.image(panel, out.name, place["x"], place["y"], size[0] * place["k"], size[1] * place["k"])
        glow = panel.get("zar")
        if not glow:
            return picture
        gid = f"zar-{panel['id']}"
        light = self.t.get("zar", self.t["bg"])
        return (f'<defs><radialGradient id="{gid}" gradientUnits="userSpaceOnUse" cx="{glow["x"]:.1f}" cy="{glow["y"]:.1f}" r="{glow["r"]:.1f}"><stop offset="0" stop-color="{light}"/><stop offset="1" stop-color="{light}" stop-opacity="0"/></radialGradient></defs>'
                f'<rect width="{self.W}" height="{self.H}" fill="url(#{gid})"/>' + picture)

    def _layer(self, panel: dict, place: dict, key: str, title: str) -> str:
        """Objekt oříznutý sám na sebe, ve VectorCraftu jde vybrat, posunout nebo skrýt zvlášť. Kde se dva objekty dotýkají, jsou oba
        na hraně poloprůhledné a prosvítala by stránka, proto se průhlednost hrany trochu zvedne."""
        d = panel_dir(self.root, panel["id"])
        target, box_file = d / "orez" / f"{key}.png", d / "orez" / f"{key}.json"
        if not target.exists() or not box_file.exists():
            target.parent.mkdir(exist_ok=True)
            with Image.open(d / f"vrstva-{key}.png") as source:
                im = source.convert("RGBA")
            box = im.getchannel("A").getbbox()
            if box is None:
                box_file.write_text("null", encoding="utf-8")
                return ""
            im = im.crop(box)
            r, g, b, a = im.split()
            tmp = target.with_suffix(".tmp.png")
            Image.merge("RGBA", (r, g, b, a.point(lambda v: 255 - (255 - v) * (255 - v) // 255))).save(tmp, "PNG", optimize=True)
            os.replace(tmp, target)
            box_file.write_text(json.dumps(box), encoding="utf-8")
        box = json.loads(box_file.read_text(encoding="utf-8"))
        if box is None:
            return ""
        k = place["k"]
        tag = self.image(panel, target.name, place["x"] + box[0] * k, place["y"] + box[1] * k, (box[2] - box[0]) * k, (box[3] - box[1]) * k)
        return f'<g id="{self.gid(title)}">{tag}</g>'

    def _overlays(self, panel: dict, place: dict) -> str:
        line, under = "#fff6de", "#0f141e"
        out = ""
        for o in panel["prekryvy"]:
            if o["typ"] == "krivka":
                k, ox, oy = place["k"], place["x"], place["y"]
                d = "M" + " L".join(f"{ox + u * k:.1f} {oy + v * k:.1f}" for u, v in place["info"][o["body"]]) + " Z"
                dash = ' stroke-dasharray="14 12"' if o["carkovana"] else ""
                out += f'<path d="{d}" fill="none" stroke="{under}" stroke-opacity=".65" stroke-width="5.4"{dash}/><path d="{d}" fill="none" stroke="{line}" stroke-width="2.6"{dash}/>'
            else:
                (ax, ay), (bx, by) = to_page(place, o["od"], panel["id"]), to_page(place, o["do"], panel["id"])
                out += (f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="{under}" stroke-opacity=".6" stroke-width="4"/>'
                        f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="{line}" stroke-width="1.8"/>')
                out += "".join(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.2" fill="{line}"/>' for px, py in ((ax, ay), (bx, by)))
        return f'<g id="{self.gid(f"Překryv {panel["nazev"]}")}">{out}</g>' if out else ""

    def _marks(self, panel: dict, place: dict) -> tuple[str, str]:
        """Číslo přímo v obraze tam, kde by se popisky s vodítky nevešly. Co číslo znamená, říká jiný panel."""
        if not panel["znacky"]:
            return "", ""
        r, size = 13 * self.k, self.f["znacka"] * self.k
        dots, digits = "", ""
        for mark in panel["znacky"]:
            x, y = to_page(place, mark["kotva"], panel["id"])
            dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{self.accent}" stroke="{self.t["bg"]}" stroke-width="{1.6 * self.k:.1f}"/>'
            digits += _text(x, y + size * 0.36, mark["text"], size, self.t["bg"], 700, "middle")
        return f'<g id="{self.gid(f"Značky {panel["nazev"]}")}">{dots}</g>', f'<g id="{self.gid(f"Čísla {panel["nazev"]}")}">{digits}</g>'

    def _labels(self, panel: dict, place: dict) -> tuple[str, str]:
        leads, words = [], []
        for label in panel["labels"]:
            size = label.get("size", self.f["popisek"] * self.k)
            pts = leader_points(label, place, size, panel["id"])
            ax, ay = pts[0]
            poly = " ".join(f"{a:.1f},{b:.1f}" for a, b in pts)
            if self.f["zalomit"]:       # nová stránka: barva popisku drží vodítko s ním, popisek leží vedle věci a lem nepotřebuje
                leads.append(f'<g id="{self.gid(f"Vodítko {label["text"]}")}"><polyline points="{poly}" fill="none" stroke="{self.accent}" stroke-width="{1.2 * self.k:.2f}"/>'
                             f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="{3.8 * self.k:.1f}" fill="{self.accent}"/></g>')
            else:
                leads.append(f'<g id="{self.gid(f"Vodítko {label["text"]}")}"><polyline points="{poly}" fill="none" stroke="{self.t["lead"]}" stroke-opacity=".8" stroke-width="{1.3 * self.k:.2f}"/>'
                             f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="{3.6 * self.k:.1f}" fill="{self.t["lead"]}"/></g>')
            px, py = label["pos"]
            anchor = "start" if label["align"] == "left" else "end"
            halo = None if self.f["zalomit"] else self.t["halo"]
            line = _text(px, py + size * 0.9, label["text"], size, self.accent, 700, anchor, halo)
            for i, small in enumerate(label["small"]):
                line += _text(px, py + size * (1.95 + 1.1 * i), small, size * 0.86, self.t["ink"], 400, anchor, halo)
            shadow = ' filter="url(#stin-textu)"' if self.t.get("stin") else ""
            words.append(f'<g id="{self.gid(label["text"])}"{shadow}>{line}</g>')
        lead_group = f'<g id="{self.gid(f"Vodítka {panel["nazev"]}")}">{"".join(leads)}</g>' if leads else ""
        word_group = f'<g id="{self.gid(f"Popisky {panel["nazev"]}")}">{"".join(words)}</g>' if words else ""
        return lead_group, word_group

    def _heading(self, panel: dict) -> str:
        title = panel.get("titulek")
        if not title or not title["text"]:
            return ""
        x, y = title.get("x", panel["rect"][0]), title.get("y", panel["rect"][1] - 12 * self.k)
        size = self.f["nadpis"] * self.k
        rows = heading_lines(title["text"], panel["rect"][2], self.f, self.k)
        words = "".join(_text(x, y - (len(rows) - 1 - i) * size * 1.08, row, size, self.accent, 700, spacing=1.2) for i, row in enumerate(rows))
        return f'<g id="{self.gid(f"Nadpis {title["text"]}")}">{words}</g>'

    def _picture(self, panel: dict) -> tuple[str, str]:
        place = placement(panel, body_of(self.root, panel))
        pictures = "".join(self._layer(panel, place, key, title) for key, title in panel["vrstvy"].items()) if panel["vrstvy"] else self._see_through(panel, place) if panel.get("pruhledny") else self._flat(panel, place)
        lead, words = self._labels(panel, place)
        dots, digits = self._marks(panel, place)
        below = ""
        if panel.get("pod"):
            x, y, _w, h = panel["rect"]
            if panel["pod"]["text"]:
                below = _text(x, y + h + 30 * self.k, panel["pod"]["text"], self.f["pod"] * self.k, self.accent, 700)  # pod obrazem, jako vzorky betonu u Pantheonu
            if panel["pod"]["small"]:
                below += _text(x, y + h + (56 if below else 30) * self.k, panel["pod"]["small"], self.f["pod_maly"] * self.k, self.t["ink"])
            below = f'<g id="{self.gid(f"Popisek {panel["nazev"]}")}">{below}</g>'
        return f'<g id="{self.gid(panel["nazev"])}">{pictures}</g>{self._overlays(panel, place)}{lead}{dots}', self._heading(panel) + words + digits + below

    def _facts(self, panel: dict) -> tuple[str, str]:
        x0, y0, w, _h = panel["rect"]
        size, small = panel.get("size", self.f["cislo"] * self.k), panel.get("small_size", self.f["veta"] * self.k)
        items = panel["items"]
        words = []
        if panel["smer"] == "radek":
            step = w / len(items)
            for i, item in enumerate(items):
                x = item.get("x", x0 + i * step)
                lines = "".join(_text(x, y0 + size * 0.9 + 32 * self.k + j * 25 * self.k, line, small, self.t["ink"]) for j, line in enumerate(wrap(item["text"], int(panel.get("sirka", max(10, step / (small * LINE_WIDTH)))))))
                words.append(f'<g id="{self.gid(f"Číslo {item["value"]}")}">{_text(x, y0 + size * 0.9, item["value"], size, self.accent, 700)}{lines}</g>')
        else:
            step = panel.get("krok", size * 1.5)
            offset = max(len(item["value"]) for item in items) * size * LINE_WIDTH + 12 * self.k     # čísla a slova ve dvou sloupcích, na prapor
            for i, item in enumerate(items):
                y = y0 + size + i * step
                value = _text(x0, y, item["value"], size, self.accent, 700)
                words.append(f'<g id="{self.gid(f"Číslo {item["value"]}")}">{value}{_text(x0 + offset, y, item["text"], small, self.t["ink"])}</g>')
        return "", self._heading(panel) + f'<g id="{self.gid(panel["nazev"])}">{"".join(words)}</g>'

    def _prose(self, panel: dict) -> tuple[str, str]:
        x0, y0, w, _h = panel["rect"]
        size, small = panel.get("size", self.f["vedouci"] * self.k), panel.get("small_size", self.f["veta"] * self.k)
        chars = int(panel.get("sirka", w / (small * LINE_WIDTH)))
        y, words = y0 + size, []
        for item in panel["items"]:
            lines = wrap(item["text"], chars)
            body = "".join(_text(x0, y + (28 + j * 25) * self.k, line, small, self.t["ink"]) for j, line in enumerate(lines))
            words.append(f'<g id="{self.gid(item["value"] or item["text"][:30])}">{_text(x0, y, item["value"], size, self.accent, 700)}{body}</g>')
            y += panel.get("krok", (46 + 25 * len(lines)) * self.k)
        return "", self._heading(panel) + f'<g id="{self.gid(panel["nazev"])}">{"".join(words)}</g>'

    def _timeline(self, panel: dict) -> tuple[str, str]:
        """Svislá osa: tečka, letopočet tučně, vedle něj věta."""
        x0, y0, w, _h = panel["rect"]
        size, small = panel.get("size", self.f["vedouci"] * self.k), panel.get("small_size", self.f["veta"] * self.k)
        stacked = panel.get("pod_sebou")
        gap = 0.0 if stacked else axis_gap(panel, self.f, self.k, size)
        chars = int((w - gap - 24 * self.k) / (small * LINE_WIDTH))
        y, dots, words = y0 + size, [], []
        for item in panel["items"]:
            lines = wrap(item["text"], chars)
            dots.append((x0 + 6 * self.k, y - size * 0.36))
            value = _text(x0 + 24 * self.k, y, item["value"], size, self.accent, 700)
            first = 28 * self.k if stacked else 0.0
            body = "".join(_text(x0 + gap + 24 * self.k, y + first + j * 25 * self.k, line, small, self.t["ink"]) for j, line in enumerate(lines))
            words.append(f'<g id="{self.gid(item["value"])}">{value}{body}</g>')
            y += panel.get("krok", (22 + 25 * max(1, len(lines))) * self.k)
        axis = f'<line x1="{dots[0][0]:.1f}" y1="{dots[0][1]:.1f}" x2="{dots[-1][0]:.1f}" y2="{dots[-1][1]:.1f}" stroke="{self.t["muted"]}" stroke-width="{1.4 * self.k:.2f}"/>'
        axis += "".join(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="{5 * self.k:.1f}" fill="{self.accent}"/>' for a, b in dots)
        return f'<g id="{self.gid(f"Osa {panel["nazev"]}")}">{axis}</g>', self._heading(panel) + f'<g id="{self.gid(panel["nazev"])}">{"".join(words)}</g>'

    def _drawing(self, panel: dict) -> tuple[str, str]:
        x, y, w, h = panel["rect"]
        vb = " ".join(f"{v:g}" for v in panel["viewbox"])
        box = f'x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" viewBox="{vb}"'
        drawing = f'<g id="{self.gid(panel["nazev"])}"><svg {box}>{panel["kresba"]}</svg></g>'
        words = f'<g id="{self.gid(f"Popisky {panel["nazev"]}")}"><svg {box}>{panel["texty"]}</svg></g>' if panel["texty"] else ""
        return drawing, self._heading(panel) + words

    def svg(self) -> str:
        doc, W, H, k = self.doc, self.W, self.H, self.k
        gfx = [f'<g id="Pozadí"><rect width="{W}" height="{H}" fill="{self.t["bg"]}"/></g>']
        txt = []
        head = doc.get("nadpis") or {}
        f = self.f
        hk = head.get("k", k)
        size = head.get("size", f["titulek"] * hk)
        x, y = head.get("x", f["titulek_x"] * hk), head.get("y", f["titulek_y"] * hk)
        rows = title_lines(doc, f, hk, W)
        title = "".join(_text(x, y + i * size * 1.08, line, size, self.accent, 700, spacing=2) for i, line in enumerate(rows))
        below = y + (len(rows) - 1) * size * 1.08
        for i, line in enumerate((doc.get("subtitle") or "").split("\n")):
            if line:
                title += _text(x, below + (f["podtitulek_od"] + f["podtitulek_krok"] * i) * hk, line, f["podtitulek"] * hk, self.t["ink"] if f["zalomit"] else self.t["muted"])
        txt.append(f'<g id="{self.gid("Nadpis")}">{title}</g>')
        draw = {"obraz": self._picture, "fakta": self._facts, "text": self._prose, "osa": self._timeline, "kresba": self._drawing}
        for panel in doc["panels"]:
            self.k = panel.get("k", k)
            graphics, words = draw[panel["typ"]](panel)
            gfx.append(graphics)
            txt.append(words)
        self.k = k
        lines, top = footer(doc, f, k, W, H)
        txt.append(f'<g id="{self.gid("Patička")}">{"".join(_text(f["okraj"] * k, top + i * f["zdroj_krok"] * k, line, f["zdroj"] * k, self.t["foot"]) for i, line in enumerate(lines))}</g>')
        return (f'<svg xmlns="{SVG_NS}" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}" font-stretch="semi-condensed">{TEXT_SHADOW if self.t.get("stin") else ""}'
                f'<g id="Grafika">{"".join(gfx)}</g><g id="Texty">{"".join(txt)}</g></svg>')


def render_svg(doc: dict, root: Path, href=None) -> str:
    return Renderer(doc, root, href).svg()


def _cross(a, b, c, d) -> bool:
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def _segments(poly):
    return list(zip(poly, poly[1:]))


def _strikes(poly, box) -> bool:
    """Vodítko vede přes text jako přeškrtnutí."""
    x, y, w, h = box
    return any(x < a[0] + (b[0] - a[0]) * i / 24 < x + w and y < a[1] + (b[1] - a[1]) * i / 24 < y + h for a, b in _segments(poly) for i in range(25))


def _text_box(label: dict, size: float) -> tuple[float, float, float, float]:
    width = max([len(label["text"]) * size * LINE_WIDTH * 1.08] + [len(s) * size * 0.86 * LINE_WIDTH for s in label["small"]])
    height = size * (1.2 + 1.1 * len(label["small"]))
    x, y = label["pos"]
    return (x if label["align"] == "left" else x - width, y, width, height)


def checks(doc: dict, root: Path) -> list[dict]:
    """Stejné prahy jako editor, přes všechny panely. Upozorní, nic nezastaví: úsudek zůstává na člověku (docs/infografiky-zasady.md)."""
    W, H = canvas_size(doc["size"])
    f = fonts(doc)
    page = doc.get("meritko") or W / f["jednotek"]
    out, lengths = [], []
    long_lines, crossings, outside, missing, unseen = 0, 0, [], [], []
    labels = 0
    sizes = []
    boxes = []
    struck = []
    pictures = [p for p in doc["panels"] if p["typ"] == "obraz"]
    hero = min(pictures, key=lambda p: p["poradi"]) if pictures else None
    model_of = lambda p: (p.get("zdroj") or {}).get("model_id")
    repeats = [p["nazev"] for p in pictures if p is not hero and model_of(p) and model_of(p) == model_of(hero) and not p.get("otazka")]
    for panel in doc["panels"]:
        k = panel.get("k", page)
        if panel["typ"] != "obraz" and panel.get("items"):
            sizes.append(panel.get("small_size", f["veta"] * k))
        sizes += _picture_sizes(panel, f, k) + _drawing_sizes(panel)
        if panel["typ"] != "obraz":
            continue
        info = body_of(root, panel)
        place = placement(panel, info)
        missing += [f"{panel['id']}: značka {m['text']}" for m in panel.get("znacky", []) if isinstance(m["kotva"], str) and m["kotva"] not in info["points"]]
        polys = []
        for label in panel["labels"]:
            labels += 1
            size = label.get("size", f["popisek"] * k)
            if isinstance(label["kotva"], str):
                if label["kotva"] not in info["points"]:
                    missing.append(f"{panel['id']}: {label['text']}")
                    continue
                if label["kotva"] not in info.get("viditelne", [label["kotva"]]):
                    unseen.append(label["text"])
            poly = leader_points(label, place, size, panel["id"])
            polys.append(poly)
            lengths.append(sum(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 for a, b in _segments(poly)) / W)
            if len(label["text"]) + sum(len(s) for s in label["small"]) > f["popisek_znaku"]:
                long_lines += 1
            x, y, w, h = _text_box(label, size)
            if x < 0 or y < 0 or x + w > W or y + h > H:
                outside.append(label["text"])
            boxes.append((label["text"], x, y, w, h))
            sizes.append(size * 0.86 if label["small"] else size)
        own_boxes = [_text_box(label, label.get("size", f["popisek"] * k)) for label in panel["labels"]]
        struck += [panel["labels"][i]["text"] for i, poly in enumerate(polys) for box in own_boxes if _strikes(poly, box)] if len(polys) == len(panel["labels"]) else []
        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                crossings += any(_cross(a, b, c, d) for a, b in _segments(polys[i]) for c, d in _segments(polys[j]))
    out.append({"ok": True, "text": f"{len(doc['panels'])} panelů, {labels} popisků"})
    if lengths:
        median = sorted(lengths)[len(lengths) // 2]
        out.append({"ok": median <= f["vodidlo_median"], "text": f"vodítka: medián {median * 100:.1f} % šířky"})
        far = [x for x in lengths if x > f["vodidlo_max"]]
        out.append({"ok": not far, "text": f"{len(far)} vodítek delších než {f['vodidlo_max'] * 100:.0f} % šířky" if far else "žádné vodítko není dlouhé"})
    out.append({"ok": crossings == 0, "text": f"{crossings}× se vodítka kříží" if crossings else "vodítka se nekříží"})
    out.append({"ok": not struck, "text": f"vodítko přeškrtává text: {', '.join(dict.fromkeys(struck))}" if struck else "vodítka nepřeškrtávají text"})
    if repeats:
        out.append({"ok": False, "text": f"opakují hlavní model a neříkají proč: {', '.join(repeats)}. Co ukážou víc než hlavní obraz?"})
    out.append({"ok": not long_lines, "text": f"{long_lines} popisků delších než {f['popisek_znaku']} znaků" if long_lines else "popisky krátké"})
    if doc.get("urceni", "web") == "web":
        out += _phone_checks(doc, f, page, W, H, sizes)
    else:
        out.append({"ok": True, "text": "tisková příloha: mobil se nekontroluje"})
    out += _collisions(doc, f, page, W, H, root)
    if f["zalomit"] and doc["panels"]:
        share = empty_share(doc, root)
        out.append({"ok": share <= MAX_EMPTY, "text": f"prázdná plocha {share * 100:.0f} % pod titulkem" + (": zvětšit obraz, nebo změnit formát" if share > MAX_EMPTY else "")})
        faint = [f"{part} část: {p['nazev']}" for p in pictures if p.get("pruhledny") for part in faint_parts(p, root, THEMES.get(doc.get("template"), THEMES["dark"])["bg"])]
        out.append({"ok": not faint, "text": f"splývá s pozadím: {', '.join(faint)}" if faint else "obraz se od pozadí odlišuje"})
    overlaps = [f"{a[0]} × {b[0]}" for i, a in enumerate(boxes) for b in boxes[i + 1:] if a[1] < b[1] + b[3] and b[1] < a[1] + a[3] and a[2] < b[2] + b[4] and b[2] < a[2] + a[4]]
    out.append({"ok": not overlaps, "text": f"překrývají se popisky: {', '.join(overlaps)}" if overlaps else "popisky se nepřekrývají"})
    if outside:
        out.append({"ok": False, "text": f"mimo plátno: {', '.join(outside)}"})
    if missing:
        out.append({"ok": False, "text": f"popisky míří na neznámý bod: {', '.join(missing)}"})
    if unseen:
        out.append({"ok": False, "text": f"bod v obraze není vidět: {', '.join(unseen)}"})
    out.append({"ok": bool((doc.get("sources") or "").strip()), "text": "zdroj vyplněn" if (doc.get("sources") or "").strip() else "chybí zdroj"})
    out.append({"ok": True, "text": "text jen z dokumentu, ne z modelu"})
    out.append({"ok": bool(doc.get("reviewed_by")), "text": f"zkontroloval(a) {doc['reviewed_by']}" if doc.get("reviewed_by") else "před zveřejněním zkontroluje člověk"})
    return out


def head_bottom(doc: dict, f: dict, k: float, W: int) -> float:
    """Kde končí titulek a věta pod ním."""
    head = doc.get("nadpis") or {}
    below = head.get("y", f["titulek_y"] * k) + (len(title_lines(doc, f, k, W)) - 1) * head.get("size", f["titulek"] * k) * 1.08
    lines = (doc.get("subtitle") or "").splitlines()
    return below + (f["podtitulek_od"] + f["podtitulek_krok"] * (len(lines) - 1)) * k + 14 * k if lines else below + 22 * k


def empty_share(doc: dict, root: Path) -> float:
    """Největší prázdná plocha pod titulkem nové stránky, podíl. Obraz obsazuje jen tam, kde není průhledný."""
    W, H = canvas_size(doc["size"])
    f = fonts(doc)
    k = doc.get("meritko") or W / f["jednotek"]
    sheet = Sheet(W, H)
    for panel in doc["panels"]:
        if panel["typ"] == "obraz":
            with Image.open(panel_dir(root, panel["id"]) / "obraz.png") as im:
                alpha = im.getchannel("A").copy() if "A" in im.getbands() else None
            sheet.add_picture(tuple(panel["rect"]), alpha)
            for label in panel["labels"]:
                sheet.add_box(_text_box(label, label.get("size", f["popisek"] * k)))
        elif panel.get("items"):
            sheet.add_box((panel["rect"][0], panel["rect"][1], panel["rect"][2], text_height(panel, f, k)))
        else:
            sheet.add_box(tuple(panel["rect"]))
    lines, foot = footer(doc, f, k, W, H)
    bottom = foot - f["zdroj"] * k - 6 * k if lines else H - f["okraj"] * k
    return sheet.largest_empty(head_bottom(doc, f, k, W), bottom, f["okraj"] * k)


def _luminance(rgb):
    v = np.asarray(rgb, dtype=np.float32) / 255
    v = np.where(v <= 0.03928, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * v[..., 0] + 0.7152 * v[..., 1] + 0.0722 * v[..., 2]


def faint_parts(panel: dict, root: Path, page_color: str) -> list[str]:
    """Které části průhledného obrazu splývají se stránkou: horní, střední, dolní. Měří se po pásech jen objekt, stín ne."""
    with Image.open(panel_dir(root, panel["id"]) / "obraz.png") as im:
        if "A" not in im.getbands():
            return []
        rgba = np.asarray(im.convert("RGBA").resize((max(1, im.width // 2), max(1, im.height // 2)), Image.NEAREST))
    solid = rgba[..., 3] > 200
    rows = np.nonzero(solid.any(axis=1))[0]
    cols = np.nonzero(solid.any(axis=0))[0]
    if not len(rows):
        return []
    light = _luminance(rgba[..., :3])
    page = float(_luminance(np.array([[int(page_color[i:i + 2], 16) for i in (1, 3, 5)]], dtype=np.float32))[0])
    ratio = (np.maximum(light, page) + 0.05) / (np.minimum(light, page) + 0.05)
    edges = np.linspace(rows[0], rows[-1] + 1, FAINT_BANDS + 1).astype(int)
    faint = []
    for i, (a, b) in enumerate(zip(edges, edges[1:])):
        mask = solid[a:b, cols[0]:cols[-1] + 1]
        if not mask.any():
            continue
        limit = MIN_CONTRAST_THIN if mask.mean() < THIN_FILL else MIN_CONTRAST_MASS
        if float(np.percentile(ratio[a:b, cols[0]:cols[-1] + 1][mask], 80)) < limit:
            faint.append(("horní", "střední", "dolní")[3 * i // FAINT_BANDS])
    return list(dict.fromkeys(faint))


def _picture_sizes(panel: dict, f: dict, k: float) -> list[float]:
    """Text u obrazu kromě popisků, ty měří `checks` samy."""
    sizes = [f["znacka"] * k] if panel.get("znacky") else []
    pod = panel.get("pod") or {}
    return sizes + ([f["pod"] * k] if pod.get("text") else []) + ([f["pod_maly"] * k] if pod.get("small") else [])


def _drawing_sizes(panel: dict) -> list[float]:
    """Písmo v kresbě zmenšené na rámeček panelu. Kresba bez font-size se změřit nedá."""
    if panel["typ"] != "kresba":
        return []
    scale = panel["rect"][2] / panel["viewbox"][2]
    return [float(v) * scale for v in re.findall(r'font-size="([\d.]+)', panel["texty"] + panel["kresba"])]


def words_of(doc: dict) -> int:
    """Slova, která čtenář čte. Patička se nepočítá, je to povinný údaj."""
    parts = [doc.get("title"), doc.get("subtitle")]
    for panel in doc["panels"]:
        parts += [(panel.get("titulek") or {}).get("text"), (panel.get("pod") or {}).get("text"), (panel.get("pod") or {}).get("small")]
        parts += [w for label in panel.get("labels", []) for w in [label["text"], *label["small"]]]
        parts += [w for item in panel.get("items", []) for w in (item["value"], item["text"])]
        parts += re.findall(r">([^<]+)<", panel.get("texty", ""))
    return sum(len(str(p).split()) for p in parts if p)


def word_budget(W: int, H: int) -> int:
    """docs/infografiky-zasady.md: na 4:5 kolem 80 slov, na 2:3 kolem 120, širší formát jen několik popisků."""
    return max(30, round(80 + (H / W - 1.25) * 160))


def _phone_checks(doc: dict, f: dict, k: float, W: int, H: int, sizes: list[float]) -> list[dict]:
    head = doc.get("nadpis") or {}
    headings = [f["nadpis"] * k for p in doc["panels"] if (p.get("titulek") or {}).get("text")]
    rows = [("titulek", head.get("size", f["titulek"] * k), PHONE_TITLE_PX), ("nejmenší text", min(sizes, default=W), PHONE_MIN_PX),
            ("nadpis panelu", min(headings, default=W), PHONE_HEADING_PX), ("zdroj", f["zdroj"] * k, PHONE_SOURCE_PX)]
    low = [f"{name} {size * PHONE_W / W:.1f} px, chce aspoň {need}" for name, size, need in rows if round(size * PHONE_W / W, 1) < need]
    words, budget = words_of(doc), word_budget(W, H)
    full = words > budget * 1.25     # „kolem“: tabulka je odhad
    return [{"ok": not low, "text": f"na mobilu (šířka {PHONE_W} px): {', '.join(low)}. Větší písmo, méně textu, nebo víc menších stránek" if low else "písmo čitelné i na mobilu"},
            {"ok": not full, "text": f"na mobilu se na stránku vejde kolem {budget} slov, tady je {words}: rozdělte ji na víc menších" if full else f"text se na mobil vejde, {words} slov z asi {budget}"}]


def text_height(panel: dict, f: dict, k: float) -> float:
    """Kolik textový panel na stránce opravdu zabere: stejné vzorce jako Renderer, `rect` je jen rám."""
    _x, _y, w, _h = panel["rect"]
    small = panel.get("small_size", f["veta"] * k)
    below = small * 0.3     # dotažnice pod posledním řádkem
    items = panel["items"]
    if panel["typ"] == "fakta":
        size = panel.get("size", f["cislo"] * k)
        if panel.get("smer", "radek") == "radek":
            chars = int(panel.get("sirka", max(10, (w / len(items)) / (small * LINE_WIDTH))))
            return size * 0.9 + 32 * k + (max(len(wrap(i["text"], chars)) for i in items) - 1) * 25 * k + below
        return size + (len(items) - 1) * panel.get("krok", size * 1.5) + below
    size = panel.get("size", f["vedouci"] * k)
    if panel["typ"] == "text":
        chars = int(panel.get("sirka", w / (small * LINE_WIDTH)))
        counts = [len(wrap(i["text"], chars)) for i in items]
        steps = [panel.get("krok", (46 + 25 * n) * k) for n in counts]
        return size + sum(steps[:-1]) + (28 + (counts[-1] - 1) * 25) * k + below
    stacked = panel.get("pod_sebou")
    chars = int((w - (0.0 if stacked else axis_gap(panel, f, k, size)) - 24 * k) / (small * LINE_WIDTH))
    counts = [max(1, len(wrap(i["text"], chars))) for i in items]
    steps = [panel.get("krok", (22 + 25 * n) * k) for n in counts]
    return size + sum(steps[:-1]) + (counts[-1] - 1) * 25 * k + (28 * k if stacked else 0.0) + below


def _on_object(panel: dict, box: tuple, root: Path) -> bool:
    """Leží rámeček na viditelné části obrazu? Rámeček obrazu je větší než objekt, kolem objektu je průhledno."""
    with Image.open(panel_dir(root, panel["id"]) / "obraz.png") as im:
        place = placement(panel, {"res": im.size})
        k = place["k"]
        crop = (max(0, int((box[0] - place["x"]) / k)), max(0, int((box[1] - place["y"]) / k)), min(im.width, int((box[0] + box[2] - place["x"]) / k) + 1), min(im.height, int((box[1] + box[3] - place["y"]) / k) + 1))
        if crop[0] >= crop[2] or crop[1] >= crop[3]:
            return False
        return "A" not in im.getbands() or im.getchannel("A").crop(crop).getextrema()[1] > 60


def _collisions(doc: dict, f: dict, k: float, W: int, H: int, root: Path) -> list[dict]:
    """Text panelu přes jiný panel, přes patičku nebo mimo stránku. Nová stránka hlídá i popisky a text přes obraz měří podle objektu, ne podle rámečku."""
    texts = [(p["nazev"], p["rect"][0], p["rect"][1], p["rect"][2], text_height(p, f, p.get("k", k))) for p in doc["panels"] if p["typ"] in ("fakta", "text", "osa")]
    pictures = [p for p in doc["panels"] if p["typ"] == "obraz"]
    others = [(p["nazev"], *p["rect"]) for p in doc["panels"] if p["typ"] == "kresba" or (p["typ"] == "obraz" and not f["zalomit"])]
    lines, top = footer(doc, f, k, W, H)
    if lines:
        others.append(("patička", 0, top - f["zdroj"] * k, W, H))
    hit = [f"{a[0]} × {b[0]}" for i, a in enumerate(texts) for b in texts[i + 1:] + others if a[1] < b[1] + b[3] and b[1] < a[1] + a[3] and a[2] < b[2] + b[4] and b[2] < a[2] + a[4]]
    if f["zalomit"]:
        labels = [(label["text"], *_text_box(label, label.get("size", f["popisek"] * p.get("k", k)))) for p in pictures for label in p["labels"]]
        hit += [f"{a[0]} × {p['nazev']}" for a in texts + labels for p in pictures if a[1] < p["rect"][0] + p["rect"][2] and p["rect"][0] < a[1] + a[3] and a[2] < p["rect"][1] + p["rect"][3] and p["rect"][1] < a[2] + a[4] and _on_object(p, a[1:], root)]
    outside = [t[0] for t in texts if t[2] + t[4] > H or t[1] + t[3] > W + 0.5]
    return ([{"ok": False, "text": f"text panelu zasahuje jinam: {', '.join(hit)}"}] if hit else []) + ([{"ok": False, "text": f"text panelu přetéká stránku: {', '.join(outside)}"}] if outside else [])


def texts_of(doc: dict) -> list[dict]:
    """Co dokument říká, do provenience exportu: bez obrázků a kreseb."""
    keep = ("id", "typ", "poradi", "titulek", "otazka", "labels", "znacky", "items", "pod", "zdroj", "fakta")
    return [{k: p[k] for k in keep if k in p} for p in doc["panels"]]


def copy_render(source: Path, root: Path, panel_id: str) -> Path:
    """Kopie výstupu renderu do dokumentu: pozdější render modelu ani přeskládání ji nezmění. Skript lod_pantheon.py píše rez.png, Engine obraz.png."""
    if not (source / "body.json").is_file():
        raise InfoError(f"panel {panel_id}: render {source.name} nemá body.json")
    picture = next((source / n for n in ("obraz.png", "rez.png") if (source / n).is_file()), None)
    if picture is None:
        raise InfoError(f"panel {panel_id}: render {source.name} nemá obraz")
    target = panel_dir(root, panel_id)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(picture, target / "obraz.png")
    shutil.copy2(source / "body.json", target / "body.json")
    for layer in source.glob("vrstva-*.png"):
        shutil.copy2(layer, target / layer.name)
    return target


def _background(mask: Image.Image, keep_below: int = 400) -> Image.Image:
    """`mask` má 0 tam, kde je barva pozadí. Vrátí 0 pro pozadí a 255 pro postavu: pozadí navazuje na okraj, nebo je to velká plocha uzavřená postavou
    (mezi rukou a bokem). Plocha pod `keep_below` pixelů může být odlesk na kovu a zůstane."""
    w, h = mask.size
    mask = mask.copy()
    for seed in [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]:
        if mask.getpixel(seed) == 0:
            ImageDraw.floodfill(mask, seed, 128)
    for y in range(0, h, 6):
        for x in range(0, w, 6):
            if mask.getpixel((x, y)) == 0:
                ImageDraw.floodfill(mask, (x, y), 200)
                small = mask.histogram()[200] < keep_below
                mask = mask.point(lambda v, small=small: (255 if small else 128) if v == 200 else v)
    return mask.point(lambda v: 0 if v == 128 else 255)


def cut_green(rgba: Image.Image, shadow: bool = False) -> Image.Image:
    """Postava na zeleném plátně: měkká hrana, bez zeleného lemu. Leštěný kov plátno odráží, je ale méně sytý: práh je nad ním a malé díry v něm se zaplní.
    `shadow` nechá stín ze samotného obrázku, který sedí na světlo postavy a přirůstá k chodidlům: tmavší místa plátna proti jasu podlahy v tom řádku."""
    px = np.asarray(rgba.convert("RGB"), dtype=np.float32)
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    other = np.maximum(r, b)
    body = np.clip((48 - (g - other)) / 18, 0, 1)   # převaha zelené: plátno 56 až 74 i ve stínu, leštěný kov nejvýš 25
    sealed = Image.fromarray(np.where(body < 0.5, 0, 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    solid = np.asarray(_background(sealed, keep_below=2500), dtype=np.float32) / 255
    body = np.maximum(body * (solid > 0), solid * (body > 0.02))
    color = px.copy()
    color[..., 1] = np.minimum(g, other)            # zelený odlesk na hraně a v kovu pryč
    alpha = body
    if shadow:
        h, w = body.shape
        rows = np.nonzero((body > 0.5).any(axis=1))[0]
        feet, tall = int(rows[-1]), int(rows[-1] - rows[0])
        centre = np.nonzero((body[int(feet - tall * 0.08):feet + 1] > 0.5).any(axis=0))[0].mean()
        luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
        floor = np.array([np.percentile(luma[y][body[y] < 0.05], 85) if (body[y] < 0.05).sum() > 20 else 0.0 for y in range(h)], dtype=np.float32)
        floor = np.convolve(np.pad(floor, 20, mode="edge"), np.ones(41) / 41, mode="valid")[:, None]
        yy, xx = np.mgrid[0:h, 0:w]
        near = np.clip(1.2 - np.hypot((xx - centre) / (0.6 * tall), (yy - feet) / (0.2 * tall)), 0, 1)      # dál od chodidel je to nerovnoměrné plátno, ne stín
        edge = np.clip(np.minimum(np.minimum(xx, w - 1 - xx), h - 1 - yy) / 70, 0, 1)      # u kraje obrázku vybledne, ať nekončí rovnou hranou
        shade = np.clip((1 - luma / np.maximum(floor, 1)) * 1.8, 0, 1) * near * edge * (body < 0.5)
        shade = np.asarray(Image.fromarray((shade * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2.0)), dtype=np.float32) / 255
        alpha = body + (1 - body) * shade
        color = color * (body / np.maximum(alpha, 1e-3))[..., None]
    return Image.fromarray(np.dstack((np.clip(color, 0, 255), alpha * 255)).astype(np.uint8), "RGBA")


def cut_out(rgba: Image.Image, shadow: bool = False, tolerance: int = 9) -> Image.Image:
    """Studiové pozadí pryč: postava zůstane bez rámečku a bez rozmazaných okrajů (docs/infografiky-zasady.md). Pozadí je barva rohů obrázku,
    do jednoho rohu smí zasahovat předloktí nebo zbraň. Na tmavém pozadí se tmavý kov ztrácí, postavy s kovem proto chtějí zelené plátno."""
    source = rgba.convert("RGB")
    w, h = source.size
    corners = [source.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    backdrop = tuple(sorted(c[i] for c in corners)[1] for i in range(3))
    if backdrop[1] > 1.3 * max(backdrop[0], backdrop[2]):
        return cut_green(rgba, shadow)
    luma, cb, cr = ImageChops.difference(source.convert("YCbCr"), Image.new("RGB", (w, h), backdrop).convert("YCbCr")).split()
    # podle barvy, ne jasu: stín na kůži je tmavý jako pozadí, ale jinak barevný; osvětlené pozadí barvu drží
    mask = ImageChops.lighter(ImageChops.lighter(cb, cr).point(lambda v: 0 if v <= tolerance else 255), luma.point(lambda v: 0 if v <= 95 else 255))
    out = rgba.copy()
    # o pixel dovnitř a měkce: bez lemu pozadí a bez zubů
    out.putalpha(_background(mask).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8)))
    return out


def copy_image(source: Path, root: Path, panel_id: str, crop: list | None = None, cut: bool = False, shadow: bool = False) -> Path:
    """Hotový obrázek jako panel, volitelně jen výřez [x, y, w, h] v pixelech, volitelně bez studiového pozadí a se stínem z obrázku. Nemá model: kotva popisku [x, y, 0] jsou pixely obrázku."""
    target = panel_dir(root, panel_id)
    target.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as im:
        rgba = im.convert("RGBA")
    if crop:
        x, y, w, h = crop
        rgba = rgba.crop((int(x), int(y), int(x + w), int(y + h)))
    if cut:
        rgba = cut_out(rgba, shadow)
    rgba.save(target / "obraz.png")
    (target / "body.json").write_text(json.dumps({"res": list(rgba.size), "points": {}, "viditelne": [], "origin": [0, 0], "basis": {"x": [1, 0], "y": [0, 1], "z": [0, 0]}}), encoding="utf-8")
    return target


def credit(name: str, author: str | None, license_: str | None) -> str:
    """Věta do patičky. Commons má u autora někdy celý vzkaz, patří tam jen první věta."""
    who = (author or "autor neuveden").split(". ")[0]
    return f"{name}: {who}, {license_ or 'licence neuvedena'}"


def compose_note(render: bool, illustrated: dict[str, list[str]], credits: list[str]) -> str:
    """Patička dokumentu, kde jsou vedle sebe render z modelu, AI ilustrace a cizí obrazy. Licence FLUX § 2e: AI obraz musí být označený."""
    parts = (["Model a render: Blender, bez AI"] if render else []) + [f"{', '.join(names)}: {model} (AI)" for model, names in illustrated.items()] + credits
    return "; ".join(parts + ["schéma a popisky redakčně."])


def flat_hero(root: Path, doc: dict) -> bytes:
    """Náhled dokumentu v seznamu: hlavní obraz (nejnižší `poradi`) sloučený na barvu stránky. Stránka jen s textem má prázdnou plochu."""
    pictures = [p for p in doc["panels"] if p["typ"] == "obraz"]
    bg = THEMES.get(doc.get("template"), THEMES["dark"])["bg"]
    if not pictures:
        buf = BytesIO()
        Image.new("RGB", (256, 256), tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5))).save(buf, "PNG")
        return buf.getvalue()
    hero = min(pictures, key=lambda p: p["poradi"])
    with Image.open(panel_dir(root, hero["id"]) / "obraz.png") as im:
        rgba = im.convert("RGBA")
    back = Image.new("RGBA", rgba.size, tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5)) + (255,))
    buf = BytesIO()
    Image.alpha_composite(back, rgba).convert("RGB").save(buf, "PNG")
    return buf.getvalue()
