"""Rozdělit hotový dokument s panely na sérii stránek pro telefon (docs/infografiky-zasady.md, oddíl Web a mobil).

Vzor je přijatá Studna (library/plakaty/velsen/mobil2/): velký titulek, jedna věta, velký obraz a popisky s vodítkem přímo u věci.
Popisek má na telefonu aspoň 12 px, takže se jich k obrazu vejde kolem pěti. Další jdou na další stránku s výřezem téhož obrazu, kde
leží. Obraz na výšku má popisky ve sloupci vedle sebe, obraz na šířku nad sebou a pod sebou, vodítka svisle od věci. Text se nepřepisuje
a nic se nevypouští. Plný výčet zdrojů zůstává v dokumentu (`sources`) a patří pod článek, na stránce je jen označení AI a cizí autor.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from PIL import Image

from engine.infographics import InfoError
from engine.panels import LINE_WIDTH, PHONE_MIN_PX, PHONE_W, body_of, panel_dir, wrap
from engine.reformat import _same_series, make_blocks, panel_box

W = 1080
MARGIN = 40
GAP = 40
MIN_H, MAX_H = 900, 1920            # delší než 9:16 se na obrazovku telefonu nevejde
MAX_WORDS = 120                     # stránka 2:3, oddíl Web a mobil
SMALL = PHONE_MIN_PX * W / PHONE_W  # nejmenší text na plátně, 36 px
NAME = SMALL / 0.86                 # název popisku, řádek pod ním je 0,86 * název
K_TEXT = SMALL / 21                 # panel fakta, text, osa: drobné písmo je 21 * k
K_PICTURE = SMALL / 18              # panel obraz: číslice značky je 18 * k
K_FOOT = 27 / 17                    # označení AI: 9 px na telefonu
LABELS_PER_VIEW = 5
SERIES_CHUNK = 3                    # řada obrazů: obraz vlevo, text vpravo, tři řádky na stránku
SERIES_PICTURE = 400
MAX_ZOOM = 2.0                      # malý render se víc nezvětšuje
CROP_MARGIN = 0.14                  # výřez kolem popisovaných bodů, podíl strany obrazu
PICTURE_HEIGHTS = (1000, 800, 620, 480)


def words_of(panel: dict) -> int:
    texts = [(panel.get("titulek") or {}).get("text", "")]
    for label in panel.get("labels", []):
        texts += [label["text"], *label["small"]]
    if panel.get("pod"):
        texts += [panel["pod"]["text"], panel["pod"]["small"]]
    for item in panel.get("items", []):
        texts += [item["value"], item["text"]]
    return len(" ".join(texts).split())


def _name(panel: dict) -> str:
    return (panel.get("titulek") or {}).get("text") or panel["nazev"]


def _point(info: dict, kotva) -> tuple[float, float] | None:
    """Bod v pixelech obrazu."""
    if isinstance(kotva, str):
        return tuple(info["points"][kotva]) if kotva in info["points"] else None
    ox, oy = info["origin"]
    b = info["basis"]
    return ox + b["x"][0] * kotva[0] + b["y"][0] * kotva[1] + b["z"][0] * kotva[2], oy + b["x"][1] * kotva[0] + b["y"][1] * kotva[1] + b["z"][1] * kotva[2]


def _crop_box(info: dict, labels: list[dict]) -> list[int] | None:
    spots = [p for p in (_point(info, label["kotva"]) for label in labels) if p]
    if not spots:
        return None
    res_w, res_h = info["res"]
    x0, x1 = min(p[0] for p in spots) - CROP_MARGIN * res_w, max(p[0] for p in spots) + CROP_MARGIN * res_w
    y0, y1 = min(p[1] for p in spots) - CROP_MARGIN * res_h, max(p[1] for p in spots) + CROP_MARGIN * res_h
    x0, y0 = max(0.0, x0), max(0.0, y0)
    return [round(x0), round(y0), round(min(res_w, x1) - x0), round(min(res_h, y1) - y0)]


def _crop_info(info: dict, box: list[int]) -> dict:
    x, y, w, h = box
    out = {**info, "res": [w, h], "points": {k: [v[0] - x, v[1] - y] for k, v in info["points"].items()}, "origin": [info["origin"][0] - x, info["origin"][1] - y]}
    for key, value in info.items():     # křivky překryvů jsou seznamy bodů v pixelech obrazu
        if key not in ("res", "origin", "points") and isinstance(value, list) and value and isinstance(value[0], (list, tuple)):
            out[key] = [[p[0] - x, p[1] - y] for p in value]
    return out


@lru_cache(maxsize=256)
def _filled(path: str, stamp: float) -> tuple[int, int, int, int] | None:
    with Image.open(path) as im:
        return im.convert("RGBA").getchannel("A").getbbox()


def _trim(panel: dict, root: Path) -> dict:
    """Render má kolem modelu průhledný okraj. Na telefonu je to ztracená plocha, stránka bere jen to, co je vidět."""
    if panel["typ"] != "obraz":
        return panel
    picture = panel_dir(root, panel["id"]) / "obraz.png"
    box = _filled(str(picture), picture.stat().st_mtime)
    info = body_of(root, panel)
    if box is None:
        return panel
    pad = 8
    x0, y0, x1, y1 = max(0, box[0] - pad), max(0, box[1] - pad), min(info["res"][0], box[2] + pad), min(info["res"][1], box[3] + pad)
    if (x1 - x0) * (y1 - y0) > 0.94 * info["res"][0] * info["res"][1]:
        return panel
    return {**panel, "vyrez": {"zdroj": panel["id"], "box": [x0, y0, x1 - x0, y1 - y0]}}


def _viewed_info(panel: dict, root: Path) -> dict:
    info = body_of(root, panel)
    return _crop_info(info, panel["vyrez"]["box"]) if panel.get("vyrez") else info


def _views(panel: dict, info: dict) -> list[dict]:
    """Obraz s popisky rozdělený po pěti: první na celý obraz, další na výřez kolem svých bodů."""
    labels = sorted(panel["labels"], key=lambda label: (_point(info, label["kotva"]) or (0, 0))[0])
    if len(labels) <= LABELS_PER_VIEW:
        return [panel]
    chunks = [labels[i:i + LABELS_PER_VIEW] for i in range(0, len(labels), LABELS_PER_VIEW)]
    views = [{**panel, "labels": chunks[0]}]
    for n, chunk in enumerate(chunks[1:], 2):
        view = {**panel, "id": f"{panel['id']}_v{n}", "nazev": f"{panel['nazev']}, detail", "labels": chunk, "znacky": [], "prekryvy": [], "puvod": panel["nazev"]}
        view.pop("titulek", None)
        view.pop("pod", None)
        box = _crop_box(info, chunk) or [0, 0, *info["res"]]
        shift = (panel.get("vyrez") or {}).get("box", [0, 0])
        view["vyrez"] = {"zdroj": panel["id"], "box": [box[0] + shift[0], box[1] + shift[1], box[2], box[3]]}
        views.append(view)
    return views


def make_pieces(doc: dict, root: Path) -> list[dict]:
    """[{id, nazev, slov, panels, series, companion}], v pořadí důležitosti. Kus je to, co na stránce drží pohromadě."""
    pieces = []
    for n, block in enumerate(make_blocks(doc), 1):
        members = sorted((_trim(doc["panels"][m], root) for m in block["members"] if m != "nadpis"), key=lambda p: (p["rect"][1], p["rect"][0]))
        if not members:
            continue
        series: list[dict] = []
        for p in members:
            same = [q for q in members if q["typ"] == "obraz" and p["typ"] == "obraz" and _same_series(p, q)]
            if len(same) >= 2 and len(same) > len(series):
                series = same
        partner = next((p for p in members if p["typ"] in ("fakta", "text") and series and len(p.get("items", [])) == len(series)), None)
        rest = [p for p in members if p not in series and p is not partner]
        block_title = next((_name(p) for p in members if p.get("titulek")), None)
        grouped: list[list[dict]] = []
        for p in sorted(rest, key=lambda p: p["poradi"]):
            if p in [q for g in grouped for q in g]:
                continue
            numbers = {str(m["text"]) for m in p.get("znacky", [])}
            # fakta, která vysvětlují čísla v obraze, musí být vidět spolu s ním
            key = [q for q in rest if numbers and q["typ"] != "obraz" and {str(i["value"]) for i in q.get("items", [])} >= numbers]
            grouped.append([p, *key])
        for m, group in enumerate(grouped, 1):
            first = group[0]
            views = _views(first, _viewed_info(first, root)) if first["typ"] == "obraz" else [first]
            for v, view in enumerate(views, 1):
                pieces.append({"id": f"k{n}p{m}" + (f"d{v}" if v > 1 else ""), "panels": [view, *group[1:]] if v == 1 else [view], "series": [], "companion": None, "chunk": 0,
                               "poradi": first["poradi"] + (v - 1) * 0.1, "block_title": block_title, "detail": v > 1})
        for i in range(0, len(series), SERIES_CHUNK):
            part = series[i:i + SERIES_CHUNK]
            pieces.append({"id": f"k{n}s{i // SERIES_CHUNK + 1}", "panels": [], "series": part, "companion": partner, "chunk": i, "poradi": part[0]["poradi"], "block_title": block_title, "detail": False})
    pieces.sort(key=lambda p: p["poradi"])
    for piece in pieces:
        own = [*piece["panels"], *piece["series"]]
        titled = [p for p in [*own, piece["companion"]] if p and p.get("titulek")]
        if piece["detail"]:
            piece["nazev"] = f"{doc['title']}: detail"
        else:
            piece["nazev"] = _name(titled[0]) if titled else (piece["block_title"] if piece["series"] else None) or _name(own[0])
        piece["slov"] = sum(words_of(p) for p in own)
        if piece["companion"]:
            items = piece["companion"]["items"][piece["chunk"]:piece["chunk"] + len(piece["series"])]
            piece["slov"] += sum(len(f"{i['value']} {i['text']}".split()) for i in items)
            if piece["chunk"] == 0:
                piece["slov"] += len((piece["companion"].get("titulek") or {}).get("text", "").split())
    return pieces


def _fit_value(item: dict, width: float, size: float) -> dict:
    """Tučný řádek se nezalamuje: co se do sloupce nevejde, přejde na začátek věty. Slova zůstanou všechna."""
    words = item["value"].split()
    if len(item["value"]) * size * LINE_WIDTH <= width or len(words) < 2:
        return item
    keep = []
    while words and len(" ".join([*keep, words[0]])) * size * LINE_WIDTH <= width:
        keep.append(words.pop(0))
    keep = keep or [words.pop(0)]
    return {**item, "value": " ".join(keep), "text": " ".join([*words, item["text"]]).strip()}


def _set_label(label: dict, width: float) -> dict:
    """Popisek na velikost pro telefon: název jeden řádek, drobný text zalomený do šířky."""
    name_chars = int(width / (NAME * LINE_WIDTH * 1.08))
    words = label["text"].split()
    keep = []
    while words and len(" ".join([*keep, words[0]])) <= name_chars:
        keep.append(words.pop(0))
    keep = keep or [words.pop(0)]
    small_chars = int(width / (SMALL * LINE_WIDTH))
    small = wrap(" ".join([*words, *label["small"]]), small_chars) if words or label["small"] else []
    return {**label, "text": " ".join(keep), "small": small, "size": NAME}


def _label_height(label: dict) -> float:
    return NAME * (1.2 + 1.1 * len(label["small"]))


def _label_width(label: dict) -> float:
    return max([len(label["text"]) * NAME * LINE_WIDTH * 1.08] + [len(s) * SMALL * LINE_WIDTH for s in label["small"]])


class Page:
    def __init__(self, root: Path, max_h: float):
        self.root, self.max_h, self.y, self.panels, self.notes = root, max_h, 0.0, [], []

    def _info(self, p: dict) -> dict:
        if p.get("vyrez"):
            source = json.loads((panel_dir(self.root, p["vyrez"]["zdroj"]) / "body.json").read_text(encoding="utf-8"))
            return _crop_info(source, p["vyrez"]["box"])
        return body_of(self.root, p)

    def _check_marks(self, p: dict, info: dict, scale: float) -> None:
        spots = [(m["text"], _point(info, m["kotva"])) for m in p.get("znacky", [])]
        spots = [(t, xy) for t, xy in spots if xy]
        for i, (a, (ax, ay)) in enumerate(spots):
            for b, (bx, by) in spots[i + 1:]:
                if ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 * scale < 13 * K_PICTURE * 1.6:
                    self.notes.append(f"čísla {a} a {b} se v obraze překrývají")

    def _side(self, p: dict, info: dict, labels: list[dict]) -> dict:
        """Obraz na výšku: popisky ve sloupci vpravo, každý co nejblíž výšce své věci."""
        res_w, res_h = info["res"]
        scale = min(620 / res_w, self.max_h / res_h, MAX_ZOOM)
        w, h = res_w * scale, res_h * scale
        self._check_marks(p, info, scale)
        x = MARGIN
        col = x + w + 44
        width = W - MARGIN - col
        placed = []
        for label in labels:
            spot = _point(info, label["kotva"])
            placed.append((spot[1] * scale if spot else h / 2, _set_label(label, width)))
        placed.sort(key=lambda pair: pair[0])
        y, out = 0.0, []
        for want, label in placed:
            top = max(y, want - NAME * 0.72)
            out.append({**label, "pos": [col, top], "align": "left"})
            y = top + _label_height(label) + 22
        return {**p, "rect": [x, 0, w, h], "k": K_PICTURE, "labels": out}

    def _stacked(self, p: dict, info: dict, labels: list[dict]) -> dict:
        """Obraz na šířku: popisky nad ním a pod ním, vodítka svisle od věci. Vnější popisek jde první a nejblíž obrazu, každý další
        hledá nejbližší řádek a stranu, kde nezakryje jiný text ani vodítko."""
        res_w, res_h = info["res"]
        scale = min((W - 2 * MARGIN) / res_w, self.max_h / res_h, MAX_ZOOM)
        w, h = res_w * scale, res_h * scale
        x = MARGIN + (W - 2 * MARGIN - w) / 2
        self._check_marks(p, info, scale)
        spots = []
        for label in labels:
            spot = _point(info, label["kotva"]) or (res_w / 2, res_h)
            spots.append((x + spot[0] * scale, spot[1] * scale, label))
        orders = (lambda t: -abs(t[0] - W / 2), lambda t: abs(t[0] - W / 2), lambda t: t[0], lambda t: -t[0])
        best, missed = None, None
        for order in orders:
            out, failed = [], []
            placed: dict[bool, list[tuple]] = {True: [], False: []}     # (x, y, šířka, výška textu, x vodítka, konec vodítka)
            for ax, ay, label in sorted(spots, key=order):
                near_top = ay < h / 2
                done = self._place_label(ax, near_top, h, label, placed[near_top]) or self._place_label(ax, not near_top, h, label, placed[not near_top])
                if done is None:
                    failed.append((ax, label))
                else:
                    out.append(done)
            if best is None or len(failed) < len(missed):
                best, missed = out, failed
            if not failed:
                break
        out = best
        for ax, label in missed:
            self.notes.append(f"popisek „{label['text']}“ se bez překryvu nevešel, přesuňte ho na výřez")
            text = _set_label(label, W - MARGIN - ax - 8 if ax < W / 2 else ax - 8 - MARGIN)
            out.append({**text, "pos": [ax + 8 if ax < W / 2 else ax - 8, h + 26], "align": "left" if ax < W / 2 else "right"})
        return {**p, "rect": [x, 0, w, h], "k": K_PICTURE, "labels": out}

    def _place_label(self, ax: float, top: bool, h: float, label: dict, placed: list[tuple]) -> dict | None:
        outward_left = ax < W / 2
        best = None
        for to_left in (outward_left, not outward_left):
            room = ax - 8 - MARGIN if to_left else W - MARGIN - ax - 8
            if room < 230:
                continue
            text = _set_label(label, room)
            height, width = _label_height(text), _label_width(text)
            tx = ax - 8 - width if to_left else ax + 8
            for step in range(120):
                near = 26 + step * 12
                y = -near - height if top else h + near
                if self._free(tx, y, width, height, ax, top, h, placed):
                    if best is None or near < best[0]:
                        best = (near, text, y, tx, width, height, to_left)
                    break
        if best is None:
            return None
        _, text, y, tx, width, height, to_left = best
        placed.append((tx, y, width, height, ax, y if top else y + NAME))
        return {**text, "pos": [ax - 8 if to_left else ax + 8, y], "align": "right" if to_left else "left"}

    @staticmethod
    def _free(tx: float, y: float, width: float, height: float, ax: float, top: bool, h: float, placed: list[tuple]) -> bool:
        end = y + NAME * 0.72
        pad = 12
        for ox, oy, ow, oh, line_x, line_end in placed:
            if tx < ox + ow + pad and ox < tx + width + pad and y < oy + oh + pad and oy < y + height + pad:
                return False
            # moje vodítko přes cizí text, cizí vodítko přes můj text
            lo, hi = (end, 0) if top else (h, end)
            if ox - 4 < ax < ox + ow + 4 and oy < hi and lo < oy + oh:
                return False
            lo2, hi2 = (line_end, 0) if top else (h, line_end)
            if tx - 4 < line_x < tx + width + 4 and y < hi2 and lo2 < y + height:
                return False
        return True

    def picture(self, p: dict) -> dict:
        info = self._info(p)
        res_w, res_h = info["res"]
        labels = p.get("labels", [])
        out = {k: v for k, v in p.items() if k != "pod"}
        if labels and res_w / res_h < 1.0:
            return self._side(out, info, labels)
        if labels:
            return self._stacked(out, info, labels)
        scale = min((W - 2 * MARGIN) / res_w, self.max_h / res_h, MAX_ZOOM)
        w, h = res_w * scale, res_h * scale
        self._check_marks(out, info, scale)
        return {**out, "rect": [MARGIN + (W - 2 * MARGIN - w) / 2, 0, w, h], "k": K_PICTURE, "labels": []}

    def _text(self, panel: dict, x: float, width: float, title: bool = True) -> dict:
        out = {k: v for k, v in panel.items() if k not in ("size", "small_size", "krok", "sirka")}
        out["items"] = [{k: v for k, v in i.items() if k != "x"} for i in panel.get("items", [])]
        out.update(rect=[x, 0, width, 1], k=K_TEXT)
        if not title:
            out.pop("titulek", None)
        if out["typ"] == "fakta" and out.get("smer") == "sloupec" and panel_box(out, K_TEXT)[2] > width:
            out["smer"] = "radek"
        if out["typ"] == "text":
            out["items"] = [_fit_value(i, width, 26 * K_TEXT) for i in out["items"]]
        return out

    def _too_wide(self, panel: dict) -> None:
        width = panel["rect"][2]
        size = (36 if panel["typ"] == "fakta" else 26) * K_TEXT
        if panel["typ"] == "fakta" and panel.get("smer") == "radek":
            width /= len(panel["items"])
        for item in panel.get("items", []):
            if len(item["value"]) * size * LINE_WIDTH > width + 1:
                self.notes.append(f"nápis „{item['value']}“ je širší než sloupec")

    def row(self, cells: list[dict]) -> None:
        """Buňky vedle sebe. Všechno v buňce (popisky, nadpis nad panelem) se započítá do výšky."""
        cells = [{**c, "titulek": {"text": c["titulek"]["text"]}} if c.get("titulek") else c for c in cells]
        boxes = [panel_box(c, c["k"]) for c in cells]
        top = max(-b[1] for b in boxes)
        bottom = max(b[1] + b[3] for b in boxes)
        y = self.y + top
        for c in cells:
            x, y0, w, h = c["rect"]
            moved = {**c, "rect": [x, y0 + y, w, h]}
            if c.get("labels"):
                moved["labels"] = [{**label, "pos": [label["pos"][0], label["pos"][1] + y]} for label in c["labels"]]
            if c["typ"] in ("fakta", "text", "osa"):
                self._too_wide(c)
                box = panel_box({k: v for k, v in c.items() if k != "titulek"}, c["k"])
                moved["rect"] = [x, y, w, max(1.0, box[1] + box[3])]
            self.panels.append(moved)
        self.y += top + bottom + GAP

    def text_rows(self, panel: dict, x: float, width: float, title: bool = True) -> None:
        """Řada faktů se dělí po třech, aby sloupce unesly velké číslo."""
        if panel["typ"] == "fakta" and panel.get("smer", "radek") == "radek" and len(panel["items"]) > 3:
            for n, i in enumerate(range(0, len(panel["items"]), 3)):
                part = {**panel, "id": f"{panel['id']}_{n + 1}", "nazev": f"{panel['nazev']} {n + 1}", "items": panel["items"][i:i + 3]}
                self.row([self._text(part, x, width * len(part["items"]) / 3, title=title and n == 0)])
            return
        self.row([self._text(panel, x, width, title=title)])

    def add_piece(self, piece: dict, page_title: str | None) -> None:
        x, width = MARGIN, W - 2 * MARGIN
        for p in piece["panels"]:
            title = (p.get("titulek") or {}).get("text") != page_title
            if p["typ"] == "obraz":
                keep = p if title else {k: v for k, v in p.items() if k != "titulek"}
                self.row([self.picture(keep)])
                if p.get("pod"):
                    self.row([self._text({"id": f"{p['id']}_popis", "typ": "text", "poradi": p["poradi"], "nazev": f"Popis {p['nazev']}", "fakta": [], "otazka": "",
                                          "items": [{"value": p["pod"]["text"], "text": p["pod"]["small"]}], "rect": [0, 0, 1, 1]}, x, width)])
            elif p["typ"] == "kresba":
                w = min(width, p["rect"][2] * 1.8)
                h = w * p["rect"][3] / p["rect"][2]
                self.row([{**p, "rect": [x + (width - w) / 2, 0, w, h], "k": K_TEXT}])
            else:
                self.text_rows(p, x, width, title=title)
        text_x, text_w = x + SERIES_PICTURE + 30, width - SERIES_PICTURE - 30
        companion = piece["companion"]
        for j, p in enumerate(piece["series"]):
            info = self._info(p)
            scale = min(SERIES_PICTURE / info["res"][0], self.max_h * 0.4 / info["res"][1], MAX_ZOOM)
            heading = (p.get("titulek") or (companion or {}).get("titulek")) if j == 0 and piece["chunk"] == 0 else None
            cell = {k: v for k, v in p.items() if k not in ("titulek", "pod")}
            if heading and heading.get("text") != page_title:
                cell["titulek"] = {"text": heading["text"]}
            picture = {**cell, "rect": [x, 0, info["res"][0] * scale, info["res"][1] * scale], "k": K_PICTURE, "labels": []}
            items = []
            if p.get("pod"):
                items.append({"value": p["pod"]["text"], "text": p["pod"]["small"]})
            if companion:
                extra = companion["items"][piece["chunk"] + j]
                if extra["value"] or extra["text"]:
                    items.append(extra)
            cells = [picture]
            if items:
                cells.append(self._text({"id": f"{p['id']}_popis", "typ": "text", "poradi": p["poradi"], "nazev": f"Popis {p['nazev']}", "fakta": [], "otazka": "", "items": items, "rect": [0, 0, 1, 1]}, text_x, text_w))
            self.row(cells)


def page_note(doc: dict, pieces: list[dict]) -> str:
    """Co na stránce zůstává: označení AI a cizí autor u obrazů, které na ní jsou. Zbytek je v `sources` a patří pod článek."""
    names = {p.get("puvod", p["nazev"]) for piece in pieces for p in [*piece["panels"], *piece["series"]]}
    kept = []
    for part in (doc.get("ai_note") or "").split(";"):
        who, _, what = part.partition(":")
        if not what or "bez AI" in what:
            continue
        here = [n.strip() for n in who.split(",") if n.strip() in names]
        if here:
            kept.append(f"{', '.join(here)}:{what}")
    return "; ".join(kept)


def build_page(doc: dict, root: Path, pieces: list[dict], number: int, total: int) -> tuple[dict, list[str]]:
    """Pole jednoho dokumentu série a nálezy. Když je stránka moc dlouhá, zmenší se vysoké obrazy, text nikdy."""
    fields, notes = _build_page(doc, root, pieces, number, total, PICTURE_HEIGHTS[0])
    for max_h in PICTURE_HEIGHTS[1:]:
        if int(fields["size"].split("x")[1]) <= MAX_H:
            break
        fields, notes = _build_page(doc, root, pieces, number, total, max_h)
    return fields, notes


def _build_page(doc: dict, root: Path, pieces: list[dict], number: int, total: int, max_h: float) -> tuple[dict, list[str]]:
    if number == 1:
        title, sub = doc["title"], doc.get("subtitle") or ""
    else:
        title, sub = pieces[0]["nazev"], "" if doc["title"] in pieces[0]["nazev"] else doc["title"]
    sub_lines = [line for part in sub.split("\n") if part for line in wrap(part, int((W - 2 * MARGIN) / (31 * K_FOOT * LINE_WIDTH)))]
    size = min(88 * K_FOOT, (W - 2 * MARGIN) / (max(len(title), 1) * 0.62))
    head_y = MARGIN + size * 0.9
    page = Page(root, max_h)
    page.y = head_y + (38 * len(sub_lines) + 6) * K_FOOT + GAP
    for piece in pieces:
        page.add_piece(piece, title)
    note = page_note(doc, pieces)
    lines = wrap(note, round((W - 2 * MARGIN) / (17 * K_FOOT * LINE_WIDTH))) if note else []
    height = max(MIN_H, round(page.y + len(lines) * 22 * K_FOOT + 10))
    notes = list(dict.fromkeys(page.notes))
    if height > MAX_H:
        notes.append(f"stránka má výšku {height} px, na obrazovku telefonu se nevejde; přesuňte část na jinou stránku")
    keep = {k: v for k, v in doc.items() if k not in ("id", "created", "updated", "exports", "in_library", "reviewed_by", "reviewed_at", "predelano_z")}
    fields = {**keep, "title": title, "subtitle": "\n".join(sub_lines), "size": f"{W}x{height}", "panels": page.panels, "meritko": K_FOOT, "urceni": "web", "paticka_x": MARGIN, "paticka": note,
              "nadpis": {"x": MARGIN, "y": head_y, "size": size, "k": K_FOOT}, "paticka_y": height - 10 - (len(lines) - 1) * 22 * K_FOOT if lines else None,
              "serie": {"zdroj": doc["id"], "stranka": number, "celkem": total}}
    return fields, notes


def default_pages(doc: dict, root: Path, pieces: list[dict]) -> list[list[dict]]:
    """Hlavní kus má stránku pro sebe. Ostatní jdou na první stránku, kde se vejdou na výšku a do počtu slov."""
    pages: list[list[dict]] = [[pieces[0]]] if pieces else []
    for piece in pieces[1:]:
        for n in range(1, len(pages)):
            group = [*pages[n], piece]
            if sum(p["slov"] for p in group) > MAX_WORDS or sum(bool(q.get("labels")) for p in group for q in p["panels"]) > 1:
                continue
            fields, _ = build_page(doc, root, group, n + 1, len(pages))
            if int(fields["size"].split("x")[1]) <= MAX_H:
                pages[n] = group
                break
        else:
            pages.append([piece])
    return pages


def resolve_pages(doc: dict, root: Path, pieces: list[dict], wanted: list[list[str]] | None) -> list[list[dict]]:
    if wanted is None:
        return default_pages(doc, root, pieces)
    by_id = {p["id"]: p for p in pieces}
    groups = [g for g in wanted if g]
    flat = [i for g in groups for i in g]
    if sorted(flat) != sorted(by_id):
        raise InfoError("rozdělení musí obsahovat každý kus právě jednou, aby žádný text nezmizel")
    return [[by_id[i] for i in g] for g in groups]


def copy_pictures(fields: dict, source: Path, target: Path) -> None:
    """Obrazy stránky do jejího dokumentu, oříznuté na to, co je vidět. Originál zůstane."""
    for panel in fields["panels"]:
        if panel["typ"] != "obraz":
            continue
        cut = panel.get("vyrez") or {"zdroj": panel["id"], "box": None}
        origin = panel_dir(source, cut["zdroj"])
        out = panel_dir(target, panel["id"])
        out.mkdir(parents=True, exist_ok=True)
        info = json.loads((origin / "body.json").read_text(encoding="utf-8"))
        box = cut["box"] or [0, 0, *info["res"]]
        x, y, w, h = box
        for file in [origin / "obraz.png", *origin.glob("vrstva-*.png")]:
            with Image.open(file) as im:
                im.crop((x, y, x + w, y + h)).save(out / file.name)
        (out / "body.json").write_text(json.dumps(_crop_info(info, box)), encoding="utf-8")


def plan(doc: dict, root: Path, wanted: list[list[str]] | None = None) -> dict:
    pieces = make_pieces(doc, root)
    pages = resolve_pages(doc, root, pieces, wanted)
    out = []
    for n, group in enumerate(pages, 1):
        fields, notes = build_page(doc, root, group, n, len(pages))
        out.append({"kusy": [{"id": p["id"], "nazev": p["nazev"], "slov": p["slov"]} for p in group], "slov": sum(p["slov"] for p in group), "size": fields["size"], "hlaseni": notes})
    return {"stranky": out}
