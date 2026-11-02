"""Rozdělit hotový dokument s panely na sérii stránek pro telefon (docs/infografiky-zasady.md, oddíl Web a mobil, náčrt 2. 11.).

Převod formátu (engine/reformat.py) stránku jen přeskládá, písmo zůstane drobné. Tady se obraz a písmo oddělí: obraz se zmenší na šířku
stránky, písmo má velikost pro telefon. Popisky přes obraz by se při té velikosti nevešly, proto se z nich stanou čísla v obraze a legenda
pod ním se stejným textem. Text se nepřepisuje a nic se nevypouští: každé slovo zdroje je na některé stránce. Kusy (`kus`) jsou bloky
z engine/reformat.py, velká řada obrazů se dělí po čtyřech. Stránka má šířku 1080 a výšku podle obsahu.
"""
from __future__ import annotations

from pathlib import Path

from engine.infographics import InfoError
from engine.panels import LINE_WIDTH, PHONE_MIN_PX, PHONE_W, body_of, placement, to_page, wrap
from engine.reformat import _same_series, make_blocks, panel_box

W = 1080
MARGIN = 40
GAP = 36
COL_GAP = 24
MIN_H, MAX_H = 1080, 1920           # delší než 9:16 se na obrazovku telefonu nevejde
MAX_WORDS = 120                     # stránka 2:3, oddíl Web a mobil
SMALL = PHONE_MIN_PX * W / PHONE_W  # nejmenší text na plátně, 36 px
K_TEXT = SMALL / 21                 # panel fakta, text, osa: drobné písmo je 21 * k
K_PICTURE = SMALL / 18              # panel obraz: číslice značky je 18 * k
K_FOOT = 27 / 17                    # zdroj a věta o AI: 9 px na telefonu
SERIES_ROWS = 2                     # řada obrazů má na telefonu dva sloupce
SERIES_CHUNK = 4
MAX_ZOOM = 2.0                      # malý render se víc nezvětšuje
PICTURE_HEIGHTS = (900, 760, 620, 500)


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


def make_pieces(doc: dict) -> list[dict]:
    """[{id, nazev, slov, panels, series, companion}], v pořadí důležitosti. Kus je to, co na stránce drží pohromadě."""
    pieces = []
    for n, block in enumerate(make_blocks(doc), 1):
        members = sorted((doc["panels"][m] for m in block["members"] if m != "nadpis"), key=lambda p: (p["rect"][1], p["rect"][0]))
        if not members:
            continue
        series: list[dict] = []
        for p in members:
            same = [q for q in members if q["typ"] == "obraz" and p["typ"] == "obraz" and _same_series(p, q)]
            if len(same) >= 2 and len(same) > len(series):
                series = same
        partner = next((p for p in members if p["typ"] in ("fakta", "text") and series and len(p.get("items", [])) == len(series)), None)
        rest = [p for p in members if p not in series and p is not partner]
        # Fakta přes hlavní obraz jsou na telefonu samostatný kus. Výjimka: vysvětlují čísla, která obraz nese, ta musí být vidět spolu.
        block_title = next((_name(p) for p in members if p.get("titulek")), None)
        grouped = []
        for p in sorted(rest, key=lambda p: p["poradi"]):
            numbers = {str(m["text"]) for m in p.get("znacky", [])}
            key = [q for q in rest if numbers and q["typ"] != "obraz" and {str(i["value"]) for i in q.get("items", [])} >= numbers]
            if p not in [q for g in grouped for q in g]:
                grouped.append([p, *key])
        for m, group in enumerate(grouped, 1):
            pieces.append({"id": f"k{n}p{m}", "panels": group, "series": [], "companion": None, "chunk": 0, "poradi": group[0]["poradi"], "block_title": block_title})
        for i in range(0, len(series), SERIES_CHUNK):
            part = series[i:i + SERIES_CHUNK]
            pieces.append({"id": f"k{n}s{i // SERIES_CHUNK + 1}", "panels": [], "series": part, "companion": partner, "chunk": i, "poradi": part[0]["poradi"], "block_title": block_title})
    pieces.sort(key=lambda p: p["poradi"])
    for piece in pieces:
        own = [*piece["panels"], *piece["series"]]
        titled = [p for p in [*own, piece["companion"]] if p and p.get("titulek")]
        piece["nazev"] = _name(titled[0]) if titled else piece["block_title"] or _name(own[0])
        piece["slov"] = sum(words_of(p) for p in own)
        if piece["companion"]:
            items = piece["companion"]["items"][piece["chunk"]:piece["chunk"] + len(piece["series"])]
            piece["slov"] += sum(len(f"{i['value']} {i['text']}".split()) for i in items)
            if piece["chunk"] == 0:
                piece["slov"] += len((piece["companion"].get("titulek") or {}).get("text", "").split())
    return pieces


def _text_height(panel: dict, width: float) -> float:
    """Výška textového panelu podle vzorců Rendereru (`engine/reformat.py`, `panel_box`)."""
    box = panel_box({**panel, "rect": [0, 0, width, 1]}, panel["k"])
    return box[1] + box[3]


def _fit_value(item: dict, width: float) -> dict:
    """Tučný řádek se nezalamuje: co se do sloupce nevejde, přejde na začátek věty. Slova zůstanou všechna."""
    if len(item["value"]) * 26 * K_TEXT * LINE_WIDTH <= width:
        return item
    number, name, *more = item["value"].split()     # „11 Aréna 83–87 × 48–55 m“: údaj přejde do věty celý
    return {**item, "value": f"{number} {name}", "text": " ".join([*more, item["text"]])}


class Page:
    def __init__(self, root: Path, max_h: float):
        self.root, self.max_h, self.y, self.panels, self.mark, self.notes = root, max_h, 0.0, [], 0, []

    def _picture(self, p: dict, x: float, width: float, max_h: float) -> tuple[dict, list[dict]]:
        """Obraz na danou šířku, popisky jako čísla. Vrací panel a položky legendy."""
        info = body_of(self.root, p)
        res_w, res_h = info["res"]
        scale = min(width / res_w, max_h / res_h, MAX_ZOOM)
        w, h = res_w * scale, res_h * scale
        legend, marks = [], list(p.get("znacky", []))
        used = [int(m["text"]) for m in marks if str(m["text"]).isdigit()]
        self.mark = max([self.mark, *used])
        for label in p["labels"]:
            self.mark += 1
            marks.append({"kotva": label["kotva"], "text": str(self.mark)})
            legend.append({"value": f"{self.mark} {label['text']}", "text": " ".join(label["small"])})
        out = {**p, "rect": [x + (width - w) / 2, 0, w, h], "k": K_PICTURE, "labels": [], "znacky": marks}
        place = placement(out, info)
        spots = [(m["text"], to_page(place, m["kotva"], p["id"])) for m in marks]
        for i, (a, (ax, ay)) in enumerate(spots):
            for b, (bx, by) in spots[i + 1:]:
                if ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 < 13 * K_PICTURE * 1.6:
                    self.notes.append(f"čísla {a} a {b} se v obraze překrývají")
        out.pop("pod", None)
        return out, legend

    def _text(self, panel: dict, x: float, width: float, title: bool = True) -> dict:
        out = {k: v for k, v in panel.items() if k not in ("size", "small_size", "krok", "sirka")}
        out["items"] = [{k: v for k, v in i.items() if k != "x"} for i in panel.get("items", [])]
        out.update(rect=[x, 0, width, 1], k=K_TEXT)
        if not title:
            out.pop("titulek", None)
        if out["typ"] == "fakta" and out.get("smer") == "sloupec":
            box = panel_box(out, K_TEXT)
            if box[2] > width:
                out["smer"] = "radek"
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
        """Buňky vedle sebe. Text má výšku podle zalomení, obraz svou, nadpis panelu nad ním se započítá."""
        top = 0.0
        tallest = 0.0
        for c in cells:
            box = panel_box({**c, "rect": [c["rect"][0], 0, c["rect"][2], c["rect"][3]]}, c["k"])
            top = max(top, -box[1])
            tallest = max(tallest, box[1] + box[3])
        for c in cells:
            x, _, w, h = c["rect"]
            y = self.y + top
            if c["typ"] in ("fakta", "text", "osa"):
                self._too_wide(c)
                h = _text_height(c, w)
            self.panels.append({**c, "rect": [x, y, w, max(1.0, h)]})
        self.y += top + tallest + GAP

    def text_rows(self, panel: dict, x: float, width: float) -> None:
        """Řada faktů se dělí po třech, aby sloupce unesly velké číslo."""
        if panel["typ"] == "fakta" and panel.get("smer", "radek") == "radek" and len(panel["items"]) > 3:
            for n, i in enumerate(range(0, len(panel["items"]), 3)):
                part = {**panel, "id": f"{panel['id']}_{n + 1}", "nazev": f"{panel['nazev']} {n + 1}", "items": panel["items"][i:i + 3]}
                self.row([self._text(part, x, width * len(part["items"]) / 3, title=n == 0)])
            return
        self.row([self._text(panel, x, width)])

    def legend(self, owner: str, items: list[dict], x: float, width: float) -> None:
        if not items:
            return
        def panel(part: list[dict], n: int) -> dict:
            return {"id": f"{owner}_legenda_{n}", "typ": "text", "poradi": 90 + n, "nazev": f"Legenda {n}", "fakta": [], "otazka": "", "items": part, "rect": [0, 0, 1, 1]}
        if len(items) <= 4:
            self.row([self._text(panel(items, 1), x, width)])
            return
        half = (len(items) + 1) // 2
        col = (width - COL_GAP) / 2
        items = [_fit_value(i, col) for i in items]
        self.row([self._text(panel(items[:half], 1), x, col), self._text(panel(items[half:], 2), x + col + COL_GAP, col)])

    def add_piece(self, piece: dict, title_taken: str | None) -> None:
        x, width = MARGIN, W - 2 * MARGIN
        for p in piece["panels"]:
            if title_taken and (p.get("titulek") or {}).get("text") == title_taken:
                p = {k: v for k, v in p.items() if k != "titulek"}
            if p["typ"] == "obraz":
                cell, legend = self._picture(p, x, width, self.max_h)
                self.row([cell])
                self.legend(p["id"], legend, x, width)
                if p.get("pod"):
                    self.row([self._text({"id": f"{p['id']}_popis", "typ": "text", "poradi": p["poradi"], "nazev": f"Popis {p['nazev']}", "fakta": [], "otazka": "",
                                          "items": [{"value": p["pod"]["text"], "text": p["pod"]["small"]}], "rect": [0, 0, 1, 1]}, x, width)])
            elif p["typ"] == "kresba":
                w = min(width, p["rect"][2] * 1.8)
                h = w * p["rect"][3] / p["rect"][2]
                self.row([{**p, "rect": [x + (width - w) / 2, 0, w, h], "k": K_TEXT}])
            else:
                self.text_rows(p, x, width)
        col = (width - COL_GAP) / 2
        series = piece["series"]
        for i in range(0, len(series), SERIES_ROWS):
            pair = series[i:i + SERIES_ROWS]
            cells, below, legends = [], [], []
            for j, p in enumerate(pair):
                cx = x + j * (col + COL_GAP)
                heading = p.get("titulek") or (piece["companion"] or {}).get("titulek") if i == 0 and j == 0 and piece["chunk"] == 0 else None
                keep = {k: v for k, v in p.items() if k != "titulek"}
                if heading and heading.get("text") != title_taken:
                    keep["titulek"] = {"text": heading["text"]}
                cell, legend = self._picture(keep, cx, col, self.max_h * 0.6)
                cells.append(cell)
                legends += legend
                items = []
                if p.get("pod"):
                    items.append({"value": p["pod"]["text"], "text": p["pod"]["small"]})
                if piece["companion"]:
                    extra = piece["companion"]["items"][piece["chunk"] + i + j]
                    if extra["value"] or extra["text"]:
                        items.append(extra)
                if items:
                    below.append(self._text({"id": f"{p['id']}_popis", "typ": "text", "poradi": p["poradi"], "nazev": f"Popis {p['nazev']}", "fakta": [], "otazka": "", "items": items, "rect": [0, 0, 1, 1]}, cx, col))
            self.row(cells)
            if below:
                self.row(below)
            self.legend(f"{piece['id'].replace('-', '_')}_rada_{i}", legends, x, width)


def _foot(doc: dict) -> int:
    note = f"{'Zdroj: ' + doc['sources'] + ' ' if doc.get('sources') else ''}{doc['ai_note']}"
    return len(wrap(note, round((W - 2 * MARGIN) / (17 * K_FOOT * LINE_WIDTH))))


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
        title, sub = pieces[0]["nazev"], doc["title"]
    sub_lines = [line for part in sub.split("\n") for line in wrap(part, int((W - 2 * MARGIN) / (31 * K_FOOT * LINE_WIDTH)))] + [f"Strana {number} z {total}"]
    size = min(88 * K_FOOT, (W - 2 * MARGIN) / (max(len(title), 1) * 0.62))
    head_y = MARGIN + size * 0.9
    page = Page(root, max_h)
    page.y = head_y + (44 + 38 * (len(sub_lines) - 1)) * K_FOOT + size * 0.25 + GAP
    for piece in pieces:
        page.add_piece(piece, None if number == 1 else title)
    lines = _foot(doc)
    foot_top = page.y
    height = max(MIN_H, round(foot_top + 30 * K_FOOT + lines * 22 * K_FOOT))
    notes = list(dict.fromkeys(page.notes))
    if height > MAX_H:
        notes.append(f"stránka má výšku {height} px, na obrazovku telefonu se nevejde; přesuňte část na jinou stránku")
    fields = {**{k: v for k, v in doc.items() if k not in ("id", "created", "updated", "exports", "in_library", "reviewed_by", "reviewed_at", "predelano_z")},
              "title": title, "subtitle": "\n".join(sub_lines), "size": f"{W}x{height}", "panels": page.panels, "meritko": K_FOOT, "urceni": "web", "paticka_x": MARGIN,
              "nadpis": {"x": MARGIN, "y": head_y, "size": size, "k": K_FOOT}, "paticka_y": height - (lines - 1) * 22 * K_FOOT - 20 * K_FOOT,
              "serie": {"zdroj": doc["id"], "stranka": number, "celkem": total}}
    return fields, notes


def default_pages(doc: dict, root: Path, pieces: list[dict]) -> list[list[dict]]:
    """Hlavní kus má stránku pro sebe, ostatní se přidávají, dokud se stránka vejde na výšku a do počtu slov."""
    pages: list[list[dict]] = [[pieces[0]]] if pieces else []
    for piece in pieces[1:]:
        group = [*pages[-1], piece]
        fits = len(pages) > 1 and sum(p["slov"] for p in group) <= MAX_WORDS
        if fits:
            fields, _ = build_page(doc, root, group, len(pages), len(pages))
            fits = int(fields["size"].split("x")[1]) <= MAX_H
        if fits:
            pages[-1] = group
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


def plan(doc: dict, root: Path, wanted: list[list[str]] | None = None) -> dict:
    pieces = make_pieces(doc)
    pages = resolve_pages(doc, root, pieces, wanted)
    out = []
    for n, group in enumerate(pages, 1):
        fields, notes = build_page(doc, root, group, n, len(pages))
        out.append({"kusy": [{"id": p["id"], "nazev": p["nazev"], "slov": p["slov"]} for p in group], "slov": sum(p["slov"] for p in group), "size": fields["size"], "hlaseni": notes})
    return {"stranky": out}
