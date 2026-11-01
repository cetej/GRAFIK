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
KINDS = ("obraz", "fakta", "text", "osa", "kresba")
THEMES = {"dark": {"bg": "#1d2532", "ink": "#f1ede4", "muted": "#a7b1bf", "foot": "#8b95a4", "lead": "#ffffff", "halo": "#000000"},
          "light": {"bg": "#f2f3f5", "ink": "#1d1f23", "muted": "#5d636b", "foot": "#6b7079", "lead": "#1d1f23", "halo": "#ffffff"},
          "ruda": {"bg": "#3a0c10", "ink": "#f6ebdf", "muted": "#d9b8a8", "foot": "#bd9a8e", "lead": "#ffffff", "halo": None, "stin": True}}
TEXT_SHADOW = ('<defs><filter id="stin-textu" x="-20%" y="-40%" width="140%" height="180%">'
               '<feDropShadow dx="0" dy="0" stdDeviation="4" flood-color="#000000" flood-opacity="0.75"/>'
               '<feDropShadow dx="1" dy="1.4" stdDeviation="1.2" flood-color="#000000" flood-opacity="0.85"/></filter></defs>')
FONT = "Bahnschrift, 'Roboto Condensed', 'Arial Narrow', sans-serif"
LINE_WIDTH = 0.47           # průměrná šířka znaku Bahnschrift semi-condensed v em, změřeno na patičce plakátu
# kopie prahů z studio/src/Infographics.tsx a docs/infografiky-zasady.md
MAX_LABELS = 10
MAX_LABEL_CHARS = 40
LEADER_MEDIAN_MAX = 0.06
LEADER_MAX = 0.12
MIN_NAME_PX, MIN_SMALL_PX = 15, 13     # při šířce 1280
PANEL_ID = re.compile(r"[a-z0-9_]{1,40}")
FILE_NAME = re.compile(r"[\w\-]+\.(png|jpg|json)")
SVG_NS = "http://www.w3.org/2000/svg"


def is_panel_doc(doc: dict | None) -> bool:
    return bool(doc) and doc.get("schema_version") == SCHEMA


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
        if raw.get("titulek"):
            title = raw["titulek"] if isinstance(raw["titulek"], dict) else {"text": str(raw["titulek"])}
            panel["titulek"] = {"text": str(title.get("text") or ""), **{k: _number(f"panel {pid}: titulek", title[k]) for k in ("x", "y") if title.get(k) is not None}}
        if panel["typ"] == "obraz":
            panel["labels"] = [_label(f"panel {pid}", label) for label in raw.get("labels") or []]
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


class Renderer:
    """SVG dokumentu. `href(panel, soubor)` dá odkaz pro náhled ve Studiu; bez něj se obrázky vloží a SVG jde do exportu."""

    def __init__(self, doc: dict, root: Path, href=None):
        self.doc, self.root, self.href = doc, root, href
        self.W, self.H = canvas_size(doc["size"])
        self.k = self.W / 1600
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
        r, size = 13 * self.k, 18 * self.k
        dots, digits = "", ""
        for mark in panel["znacky"]:
            x, y = to_page(place, mark["kotva"], panel["id"])
            dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{self.accent}" stroke="{self.t["bg"]}" stroke-width="{1.6 * self.k:.1f}"/>'
            digits += _text(x, y + size * 0.36, mark["text"], size, self.t["bg"], 700, "middle")
        return f'<g id="{self.gid(f"Značky {panel["nazev"]}")}">{dots}</g>', f'<g id="{self.gid(f"Čísla {panel["nazev"]}")}">{digits}</g>'

    def _labels(self, panel: dict, place: dict) -> tuple[str, str]:
        leads, words = [], []
        for label in panel["labels"]:
            size = label.get("size", 23 * self.k)
            pts = leader_points(label, place, size, panel["id"])
            ax, ay = pts[0]
            poly = " ".join(f"{a:.1f},{b:.1f}" for a, b in pts)
            leads.append(f'<g id="{self.gid(f"Vodítko {label["text"]}")}"><polyline points="{poly}" fill="none" stroke="{self.t["lead"]}" stroke-opacity=".8" stroke-width="{1.3 * self.k:.2f}"/>'
                         f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="{3.6 * self.k:.1f}" fill="{self.t["lead"]}"/></g>')
            px, py = label["pos"]
            anchor = "start" if label["align"] == "left" else "end"
            line = _text(px, py + size * 0.9, label["text"], size, self.accent, 700, anchor, self.t["halo"])
            for i, small in enumerate(label["small"]):
                line += _text(px, py + size * (1.95 + 1.1 * i), small, size * 0.86, self.t["ink"], 400, anchor, self.t["halo"])
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
        return f'<g id="{self.gid(f"Nadpis {title["text"]}")}">{_text(x, y, title["text"].upper(), 25 * self.k, self.accent, 700, spacing=1.2)}</g>'

    def _picture(self, panel: dict) -> tuple[str, str]:
        place = placement(panel, body_of(self.root, panel))
        pictures = "".join(self._layer(panel, place, key, title) for key, title in panel["vrstvy"].items()) if panel["vrstvy"] else self._flat(panel, place)
        lead, words = self._labels(panel, place)
        dots, digits = self._marks(panel, place)
        below = ""
        if panel.get("pod"):
            x, y, _w, h = panel["rect"]
            if panel["pod"]["text"]:
                below = _text(x, y + h + 30 * self.k, panel["pod"]["text"], 22 * self.k, self.accent, 700)  # pod obrazem, jako vzorky betonu u Pantheonu
            if panel["pod"]["small"]:
                below += _text(x, y + h + (56 if below else 30) * self.k, panel["pod"]["small"], 20 * self.k, self.t["ink"])
            below = f'<g id="{self.gid(f"Popisek {panel["nazev"]}")}">{below}</g>'
        return f'<g id="{self.gid(panel["nazev"])}">{pictures}</g>{self._overlays(panel, place)}{lead}{dots}', self._heading(panel) + words + digits + below

    def _facts(self, panel: dict) -> tuple[str, str]:
        x0, y0, w, _h = panel["rect"]
        size, small = panel.get("size", 36 * self.k), panel.get("small_size", 21 * self.k)
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
        size, small = panel.get("size", 26 * self.k), panel.get("small_size", 21 * self.k)
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
        size, small = panel.get("size", 26 * self.k), panel.get("small_size", 21 * self.k)
        gap = panel.get("sirka", 118 * self.k)
        chars = int((w - gap - 24 * self.k) / (small * LINE_WIDTH))
        y, dots, words = y0 + size, [], []
        for item in panel["items"]:
            lines = wrap(item["text"], chars)
            dots.append((x0 + 6 * self.k, y - size * 0.36))
            value = _text(x0 + 24 * self.k, y, item["value"], size, self.accent, 700)
            body = "".join(_text(x0 + gap + 24 * self.k, y + j * 25 * self.k, line, small, self.t["ink"]) for j, line in enumerate(lines))
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
        size = head.get("size", 88 * k)
        x, y = head.get("x", 50 * k), head.get("y", 118 * k)
        title = _text(x, y, doc["title"].upper(), size, self.accent, 700, spacing=2)
        for i, line in enumerate((doc.get("subtitle") or "").split("\n")):
            if line:
                title += _text(x, y + (44 + 38 * i) * k, line, 31 * k, self.t["muted"])
        txt.append(f'<g id="{self.gid("Nadpis")}">{title}</g>')
        draw = {"obraz": self._picture, "fakta": self._facts, "text": self._prose, "osa": self._timeline, "kresba": self._drawing}
        for panel in doc["panels"]:
            graphics, words = draw[panel["typ"]](panel)
            gfx.append(graphics)
            txt.append(words)
        foot = 17 * k
        lines = wrap(f"{'Zdroj: ' + doc['sources'] + ' ' if doc.get('sources') else ''}{doc['ai_note']}", round((W - 100 * k) / (foot * LINE_WIDTH)))
        top = doc.get("paticka_y") or H - 30 * k - (len(lines) - 1) * 22 * k
        txt.append(f'<g id="{self.gid("Patička")}">{"".join(_text(50 * k, top + i * 22 * k, line, foot, self.t["foot"]) for i, line in enumerate(lines))}</g>')
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
    k = W / 1600
    out, lengths = [], []
    long_lines, crossings, outside, missing, unseen = 0, 0, [], [], []
    labels = 0
    too_small = None
    boxes = []
    struck = []
    pictures = [p for p in doc["panels"] if p["typ"] == "obraz"]
    hero = min(pictures, key=lambda p: p["poradi"]) if pictures else None
    model_of = lambda p: (p.get("zdroj") or {}).get("model_id")
    repeats = [p["nazev"] for p in pictures if p is not hero and model_of(p) and model_of(p) == model_of(hero) and not p.get("otazka")]
    for panel in doc["panels"]:
        if panel["typ"] != "obraz":
            continue
        info = body_of(root, panel)
        place = placement(panel, info)
        missing += [f"{panel['id']}: značka {m['text']}" for m in panel.get("znacky", []) if isinstance(m["kotva"], str) and m["kotva"] not in info["points"]]
        polys = []
        for label in panel["labels"]:
            labels += 1
            size = label.get("size", 23 * k)
            if isinstance(label["kotva"], str):
                if label["kotva"] not in info["points"]:
                    missing.append(f"{panel['id']}: {label['text']}")
                    continue
                if label["kotva"] not in info.get("viditelne", [label["kotva"]]):
                    unseen.append(label["text"])
            poly = leader_points(label, place, size, panel["id"])
            polys.append(poly)
            lengths.append(sum(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 for a, b in _segments(poly)) / W)
            if len(label["text"]) + sum(len(s) for s in label["small"]) > MAX_LABEL_CHARS:
                long_lines += 1
            x, y, w, h = _text_box(label, size)
            if x < 0 or y < 0 or x + w > W or y + h > H:
                outside.append(label["text"])
            boxes.append((label["text"], x, y, w, h))
            px = size * 1280 / W
            if px < MIN_NAME_PX or (label["small"] and px * 0.86 < MIN_SMALL_PX):
                too_small = round(px, 1)
        own_boxes = [_text_box(label, label.get("size", 23 * k)) for label in panel["labels"]]
        struck += [panel["labels"][i]["text"] for i, poly in enumerate(polys) for box in own_boxes if _strikes(poly, box)] if len(polys) == len(panel["labels"]) else []
        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                crossings += any(_cross(a, b, c, d) for a, b in _segments(polys[i]) for c, d in _segments(polys[j]))
    out.append({"ok": True, "text": f"{len(doc['panels'])} panelů, {labels} popisků"})
    if lengths:
        median = sorted(lengths)[len(lengths) // 2]
        out.append({"ok": median <= LEADER_MEDIAN_MAX, "text": f"vodítka: medián {median * 100:.1f} % šířky"})
        far = [x for x in lengths if x > LEADER_MAX]
        out.append({"ok": not far, "text": f"{len(far)} vodítek delších než {LEADER_MAX * 100:.0f} % šířky" if far else "žádné vodítko není dlouhé"})
    out.append({"ok": crossings == 0, "text": f"{crossings}× se vodítka kříží" if crossings else "vodítka se nekříží"})
    out.append({"ok": not struck, "text": f"vodítko přeškrtává text: {', '.join(dict.fromkeys(struck))}" if struck else "vodítka nepřeškrtávají text"})
    if repeats:
        out.append({"ok": False, "text": f"opakují hlavní model a neříkají proč: {', '.join(repeats)}. Co ukážou víc než hlavní obraz?"})
    out.append({"ok": not long_lines, "text": f"{long_lines} popisků delších než {MAX_LABEL_CHARS} znaků" if long_lines else "popisky krátké"})
    out.append({"ok": too_small is None, "text": f"písmo popisku {too_small} px při šířce 1280, chce aspoň {MIN_NAME_PX}" if too_small else "písmo popisků čitelné"})
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


def compose_note(render: bool, illustrated: dict[str, list[str]], credits: list[str]) -> str:
    """Patička dokumentu, kde jsou vedle sebe render z modelu, AI ilustrace a cizí obrazy. Licence FLUX § 2e: AI obraz musí být označený."""
    parts = (["Model a render: Blender, bez AI"] if render else []) + [f"{', '.join(names)}: {model} (AI)" for model, names in illustrated.items()] + credits
    return "; ".join(parts + ["schéma a popisky redakčně."])


def flat_hero(root: Path, doc: dict) -> bytes:
    """Náhled dokumentu v seznamu: hlavní obraz (nejnižší `poradi`) sloučený na barvu stránky."""
    pictures = [p for p in doc["panels"] if p["typ"] == "obraz"]
    if not pictures:
        raise InfoError("dokument nemá žádný obraz")
    hero = min(pictures, key=lambda p: p["poradi"])
    bg = THEMES.get(doc.get("template"), THEMES["dark"])["bg"]
    with Image.open(panel_dir(root, hero["id"]) / "obraz.png") as im:
        rgba = im.convert("RGBA")
    back = Image.new("RGBA", rgba.size, tuple(int(bg[i:i + 2], 16) for i in (1, 3, 5)) + (255,))
    buf = BytesIO()
    Image.alpha_composite(back, rgba).convert("RGB").save(buf, "PNG")
    return buf.getvalue()
