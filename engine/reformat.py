"""Předělat dokument s panely na jiný formát (krok 3d, docs/plans/2026-11-01-infografika-z-tematu.md).

Stránka se rozdělí na bloky: panely, které se překrývají nebo těsně sousedí, i s popisky, nadpisy a textem přes obraz, drží pohromadě.
Blok se zvětší nebo zmenší celý, takže se uvnitř nic neposune, nezalomí ani neořízne. Na novém plátně má největší místo blok s nejnižším
`poradi`, ostatní jdou do řad nebo sloupců podle toho, kde vyjde větší písmo. Výsledek je nový dokument, zdroj se nemění.
"""
from __future__ import annotations

import re

from engine.infographics import InfoError, canvas_size
from engine.panels import LINE_WIDTH, _text_box, fonts, text_height, title_lines, wrap

GAP_JOIN = 6            # panely blíž než tolik (při k = 1) tvoří jeden blok
GAP_SERIES = 40
HERO_SHARES = [x / 100 for x in range(25, 80, 5)]
HERO_MIN_AREA = 0.25    # hlavní blok zabere aspoň tolik volné plochy, jinak by vyhrály drobnosti
MAX_SCALE = 2.0         # obrázky v dokumentu jsou tak velké, jak je render uložil


def target_size(value: str, source: str) -> str:
    """„16:9“ = stejná plocha jako zdroj (stejná ostrost a hustota), „1920x1080“ = přesný rozměr."""
    if canvas_size(value):
        return value
    m = re.fullmatch(r"(\d{1,2}):(\d{1,2})", value or "")
    if not m or not int(m[1]) or not int(m[2]):
        raise InfoError(f"neznámý formát {value!r}")
    W, H = canvas_size(source)
    h = (W * H * int(m[2]) / int(m[1])) ** 0.5
    return f"{round(h * int(m[1]) / int(m[2]))}x{round(h)}"


def page_k(doc: dict) -> float:
    return doc.get("meritko") or canvas_size(doc["size"])[0] / fonts(doc)["jednotek"]


def _union(boxes: list[tuple]) -> tuple:
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    return x0, y0, max(b[0] + b[2] for b in boxes) - x0, max(b[1] + b[3] for b in boxes) - y0


def panel_box(panel: dict, k: float, f: dict) -> tuple:
    """Co panel na stránce opravdu zabírá, i s tím, co přesahuje `rect`."""
    pk = panel.get("k", k)
    if panel["typ"] in ("fakta", "text", "osa"):
        x, y, w, _h = panel["rect"]
        boxes = [(x, y, w, text_height(panel, f, pk))]
    else:
        boxes = [tuple(panel["rect"])]
    if panel["typ"] == "obraz":
        boxes += [_text_box(label, label.get("size", f["popisek"] * pk)) for label in panel["labels"]]
        pod = panel.get("pod")
        if pod:
            x, y, w, h = panel["rect"]
            boxes.append((x, y + h, w, (62 if pod["text"] and pod["small"] else 36) * pk))
    title = panel.get("titulek")
    if title and title["text"]:
        x, y = title.get("x", panel["rect"][0]), title.get("y", panel["rect"][1] - 12 * pk)
        size = f["nadpis"] * pk
        boxes.append((x, y - size, len(title["text"]) * size * 0.62, size * 1.2))
    return _union(boxes)


def head_box(doc: dict, k: float, f: dict) -> tuple:
    head = doc.get("nadpis") or {}
    hk = head.get("k", k)
    size = head.get("size", f["titulek"] * hk)
    x, y = head.get("x", f["titulek_x"] * hk), head.get("y", f["titulek_y"] * hk)
    rows = title_lines(doc, f, hk, canvas_size(doc["size"])[0])
    lines = [line for line in (doc.get("subtitle") or "").split("\n") if line]
    width = max([max(len(row) for row in rows) * size * 0.62] + [len(line) * f["podtitulek"] * hk * LINE_WIDTH for line in lines])
    return x, y - size, width, size * (1 + 1.08 * (len(rows) - 1)) + (f["podtitulek_od"] + f["podtitulek_krok"] * len(lines)) * hk


def _touch(a: tuple, b: tuple, gap: float) -> bool:
    return a[0] < b[0] + b[2] + gap and b[0] < a[0] + a[2] + gap and a[1] < b[1] + b[3] + gap and b[1] < a[1] + a[3] + gap


def _same_series(a, b) -> bool:
    """Řada stejných obrazů (vzorky betonu, gladiátoři) drží pohromadě i přes větší mezeru."""
    return a is not None and b is not None and a["typ"] == b["typ"] and abs(a["rect"][2] - b["rect"][2]) < 0.03 * a["rect"][2] and abs(a["rect"][3] - b["rect"][3]) < 0.03 * a["rect"][3]


def make_blocks(doc: dict) -> list[dict]:
    """[{box, members (index panelu, nebo "nadpis"), poradi}], nejdůležitější první."""
    k, f = page_k(doc), fonts(doc)
    items = [(i, panel_box(p, k, f), p["poradi"], p) for i, p in enumerate(doc["panels"])]
    if doc.get("title"):
        items.append(("nadpis", head_box(doc, k, f), 0, None))
    groups = [[it] for it in items]
    merged = True
    while merged:
        merged = False
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                if any(_touch(x[1], y[1], (GAP_SERIES if _same_series(x[3], y[3]) else GAP_JOIN) * k) for x in groups[a] for y in groups[b]):
                    groups[a] += groups.pop(b)
                    merged = True
                    break
            if merged:
                break
    blocks = [{"box": _union([it[1] for it in g]), "members": [it[0] for it in g],
               "poradi": min((it[2] for it in g if it[0] != "nadpis"), default=0), "title_only": all(it[0] == "nadpis" for it in g)} for g in groups]
    return sorted(blocks, key=lambda b: (not b["title_only"], b["poradi"]))


def _size(b: dict, tall: bool) -> tuple[float, float]:
    """(délka v řadě, výška řady). `tall` = sloupce místo řad."""
    w, h = b["box"][2:]
    return (h, w) if tall else (w, h)


def _lines(blocks: list[dict], s: float, length: float, gap: float, tall: bool) -> list[list[dict]] | None:
    lines, used = [[]], 0.0
    for b in blocks:
        size = _size(b, tall)[0] * s
        if size > length:
            return None
        if lines[-1] and used + gap + size > length:
            lines.append([])
            used = 0.0
        used += (gap if lines[-1] else 0) + size
        lines[-1].append(b)
    return lines


def _depth(lines: list[list[dict]], s: float, gap: float, tall: bool) -> float:
    return sum(max(_size(b, tall)[1] for b in line) * s for line in lines) + gap * (len(lines) - 1)


def _best_fill(blocks: list[dict], width: float, height: float, gap: float) -> tuple | None:
    """Největší společné měřítko, při kterém se bloky vejdou do plochy: (měřítko, řady nebo sloupce, tall)."""
    best = None
    for tall in (False, True):
        length, depth = (height, width) if tall else (width, height)
        for order in (blocks, sorted(blocks, key=lambda b: -_size(b, tall)[1])):
            lo, hi = 0.0, MAX_SCALE
            found = None
            for _ in range(26):
                s = (lo + hi) / 2
                lines = _lines(order, s, length, gap, tall)
                if lines and _depth(lines, s, gap, tall) <= depth:
                    lo, found = s, lines
                else:
                    hi = s
            if found and (best is None or lo > best[0]):
                best = (lo, found, tall)
    return best


def _place(lines, s, tall, x0, y0, width, height, gap, out) -> None:
    length, depth = (height, width) if tall else (width, height)
    spare = max(0.0, depth - _depth(lines, s, gap, tall)) / (len(lines) + 1)
    across = spare
    for line in lines:
        total = sum(_size(b, tall)[0] * s for b in line)
        step = (length - total) / (len(line) - 1) if len(line) > 1 else 0
        along = 0.0 if len(line) > 1 else (length - total) / 2
        thick = max(_size(b, tall)[1] for b in line) * s
        for b in line:
            a, t = _size(b, tall)
            mid = across + (thick - t * s) / 2
            out.append((b, s, x0 + mid, y0 + along) if tall else (b, s, x0 + along, y0 + mid))
            along += a * s + step
        across += thick + gap + spare


def arrange(blocks: list[dict], W: int, H: int, foot: float, k: float) -> list[tuple]:
    """[(blok, měřítko, x, y)]. Zkouší hlavní blok nahoře i vlevo a různě velký; vyhrává největší písmo v ostatních blocích."""
    margin, gap = 30 * k, 26 * k
    free_w, free_h = W - 2 * margin, H - 2 * margin - foot
    top = margin
    placed: list[tuple] = []
    for b in [b for b in blocks if b["title_only"]]:    # samostatný nadpis jde vždy nahoře
        s = min(free_w / b["box"][2], 1.2)
        placed.append((b, s, margin, top))
        top += b["box"][3] * s + gap
        free_h -= b["box"][3] * s + gap
    rest = [b for b in blocks if not b["title_only"]]
    hero, others = rest[0], rest[1:]
    hw, hh = hero["box"][2:]
    best, best_score = None, (-1.0, -1.0)
    for side in ("top", "left"):
        for share in HERO_SHARES:
            if side == "top":
                sh = min(free_w / hw, share * free_h / hh, MAX_SCALE)
                area = (free_w, free_h - hh * sh - gap)
            else:
                sh = min(share * free_w / hw, free_h / hh, MAX_SCALE)
                area = (free_w - hw * sh - gap, free_h)
            hero_area = hw * hh * sh * sh
            if not others:
                if (sh, hero_area) > best_score:
                    best, best_score = (side, sh, None, None, False, area), (sh, hero_area)
                continue
            if min(area) <= 0 or hero_area < HERO_MIN_AREA * free_w * free_h:
                continue
            found = _best_fill(others, area[0], area[1], gap)
            if not found:
                continue
            s, lines, tall = found
            s = min(s, sh)      # nic není větší než hlavní obraz
            if hero_area < max(b["box"][2] * b["box"][3] for b in others) * s * s:
                continue
            if (s, hero_area) > best_score:
                best, best_score = (side, sh, s, lines, tall, area), (s, hero_area)
    if best is None:
        raise InfoError("panely se do tohohle formátu nevejdou; zvolte jiný poměr nebo větší rozměr")
    side, sh, s, lines, tall, area = best
    if side == "top":
        placed.append((hero, sh, margin + (free_w - hw * sh) / 2, top))
        ax, ay = margin, top + hh * sh + gap
    else:
        placed.append((hero, sh, margin, top + (free_h - hh * sh) / 2))
        ax, ay = margin + hw * sh + gap, top
    if lines:
        _place(lines, s, tall, ax, ay, area[0], area[1], gap, placed)
    return placed


def _move_panel(p: dict, s: float, ox: tuple, oy: tuple, pk: float) -> dict:
    """Panel v novém měřítku: co je na stránce, přepočítá se, co je uvnitř obrazu, jede s ním (kotvy jsou v `body.json`)."""
    at = lambda x, y: [(x - ox[0]) * s + ox[1], (y - oy[0]) * s + oy[1]]
    out = dict(p)
    x, y, w, h = p["rect"]
    out["rect"] = [*at(x, y), w * s, h * s]
    out["k"] = pk * s
    if p.get("titulek"):
        title = dict(p["titulek"])
        tx, ty = title.get("x", x), title.get("y", y - 12 * pk)
        title["x"], title["y"] = at(tx, ty)
        out["titulek"] = title
    if p["typ"] == "obraz":
        out["labels"] = [{**label, "pos": at(*label["pos"]), **({"size": label["size"] * s} if "size" in label else {})} for label in p["labels"]]
    elif p["typ"] != "kresba":
        out["items"] = [{**i, **({"x": (i["x"] - ox[0]) * s + ox[1]} if "x" in i else {})} for i in p["items"]]
        keys = ("size", "small_size", "krok") + (("sirka",) if p["typ"] == "osa" else ())   # jinde je `sirka` počet znaků
        out.update({key: p[key] * s for key in keys if key in p})
    return out


def reformat(doc: dict, size: str) -> dict:
    """Pole nového dokumentu: stejné panely, texty a soubory, jiné plátno. Vstup se nemění."""
    W, H = canvas_size(size)
    k, f = page_k(doc), fonts(doc)
    new_k = k * ((W * H) / (canvas_size(doc["size"])[0] * canvas_size(doc["size"])[1])) ** 0.5
    note = f"{'Zdroj: ' + doc['sources'] + ' ' if doc.get('sources') else ''}{doc['ai_note']}"
    lines = wrap(note, round((W - 2 * f["okraj"] * new_k) / (f["zdroj"] * new_k * LINE_WIDTH)))
    foot = f["zdroj_dole"] * new_k + len(lines) * f["zdroj_krok"] * new_k
    blocks = make_blocks(doc)
    panels_out = list(doc["panels"])
    head = None
    for block, s, nx, ny in arrange(blocks, W, H, foot, new_k):
        bx, by = block["box"][:2]
        for member in block["members"]:
            if member == "nadpis":
                old = doc.get("nadpis") or {}
                hk = old.get("k", k)
                head = {"x": (old.get("x", f["titulek_x"] * hk) - bx) * s + nx, "y": (old.get("y", f["titulek_y"] * hk) - by) * s + ny, "size": old.get("size", f["titulek"] * hk) * s, "k": hk * s}
            else:
                panels_out[member] = _move_panel(doc["panels"][member], s, (bx, nx), (by, ny), doc["panels"][member].get("k", k))
    for p in panels_out:
        if p["typ"] in ("fakta", "text", "osa"):    # rám textu je širší než text sám, kreslí se z něj jen to, co je v `_text_extent`
            x, y, w, h = p["rect"]
            p["rect"] = [x, y, min(w, W - x), min(h, H - y)]
    fields = {**doc, "size": size, "panels": panels_out, "meritko": new_k, "paticka_y": H - f["zdroj_dole"] * new_k - (len(lines) - 1) * f["zdroj_krok"] * new_k, "predelano_z": {"id": doc["id"], "size": doc["size"]}}
    if head:
        fields["nadpis"] = head
    return fields
