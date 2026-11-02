"""Předělat dokument s panely na jiný formát (krok 3d, docs/plans/2026-11-01-infografika-z-tematu.md).

Stránka se rozdělí na bloky: panely, které se překrývají nebo těsně sousedí, i s popisky, nadpisy a textem přes obraz, drží pohromadě.
Blok se zvětší nebo zmenší celý, takže se uvnitř nic neposune, nezalomí ani neořízne. Na novém plátně má největší místo blok s nejnižším
`poradi`, ostatní jdou do řad nebo sloupců podle toho, kde vyjde větší písmo. Výsledek je nový dokument, zdroj se nemění.
"""
from __future__ import annotations

import re

from engine.infographics import InfoError, canvas_size
from engine.panels import LINE_WIDTH, _text_box, short_note, wrap

GAP_JOIN = 6            # panely blíž než tolik (při k = 1) tvoří jeden blok
GAP_SERIES = 40
HERO_SHARES = [x / 100 for x in range(25, 101)]
MIN_REST = 0.5          # ostatní bloky se zmenší nejvýš na tolik, hlavní obraz má přednost (operátor 2. 11.)
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
    return doc.get("meritko") or canvas_size(doc["size"])[0] / 1600


def _union(boxes: list[tuple]) -> tuple:
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    return x0, y0, max(b[0] + b[2] for b in boxes) - x0, max(b[1] + b[3] for b in boxes) - y0


def _text_extent(panel: dict, k: float) -> tuple:
    """Kam až text panelu opravdu sahá, podle stejných vzorců jako Renderer: `rect` je jen rám, text z něj smí přetéct i nevyplnit ho."""
    x, y, w, _h = panel["rect"]
    size = panel.get("size", (36 if panel["typ"] == "fakta" else 26) * k)
    small = panel.get("small_size", 21 * k)
    below = small * 0.3     # dotažnice pod posledním řádkem
    items = panel["items"]
    if panel["typ"] == "fakta" and panel["smer"] == "radek":
        step = w / len(items)
        chars = int(panel.get("sirka", max(10, step / (small * LINE_WIDTH))))
        rows = max(len(wrap(i["text"], chars)) for i in items)
        return x, y, w, size * 0.9 + 32 * k + (rows - 1) * 25 * k + below
    if panel["typ"] == "fakta":
        step = panel.get("krok", size * 1.5)
        offset = max(len(i["value"]) for i in items) * size * LINE_WIDTH + 12 * k
        return x, y, offset + max(len(i["text"]) for i in items) * small * LINE_WIDTH, size + (len(items) - 1) * step + below
    if panel["typ"] == "text":
        chars = int(panel.get("sirka", w / (small * LINE_WIDTH)))
        counts = [len(wrap(i["text"], chars)) for i in items]
        steps = [panel.get("krok", (46 + 25 * n) * k) for n in counts]
        return x, y, w, size + sum(steps[:-1]) + (28 + (counts[-1] - 1) * 25) * k + below
    gap = panel.get("sirka", 118 * k)
    chars = int((w - gap - 24 * k) / (small * LINE_WIDTH))
    counts = [max(1, len(wrap(i["text"], chars))) for i in items]
    steps = [panel.get("krok", (22 + 25 * n) * k) for n in counts]
    return x, y, w, size + sum(steps[:-1]) + (counts[-1] - 1) * 25 * k + below


def panel_box(panel: dict, k: float) -> tuple:
    """Co panel na stránce opravdu zabírá, i s tím, co přesahuje `rect`."""
    pk = panel.get("k", k)
    if panel["typ"] in ("fakta", "text", "osa"):
        boxes = [_text_extent(panel, pk)]
    else:
        boxes = [tuple(panel["rect"])]
    if panel["typ"] == "obraz":
        boxes += [_text_box(label, label.get("size", 23 * pk)) for label in panel["labels"]]
        pod = panel.get("pod")
        if pod:
            x, y, w, h = panel["rect"]
            boxes.append((x, y + h, w, (62 if pod["text"] and pod["small"] else 36) * pk))
    title = panel.get("titulek")
    if title and title["text"]:
        x, y = title.get("x", panel["rect"][0]), title.get("y", panel["rect"][1] - 12 * pk)
        size = 25 * pk
        boxes.append((x, y - size, len(title["text"]) * size * 0.62, size * 1.2))
    return _union(boxes)


def head_box(doc: dict, k: float) -> tuple:
    head = doc.get("nadpis") or {}
    hk = head.get("k", k)
    size = head.get("size", 88 * hk)
    x, y = head.get("x", 50 * hk), head.get("y", 118 * hk)
    lines = [line for line in (doc.get("subtitle") or "").split("\n") if line]
    width = max([len(doc["title"]) * size * 0.62] + [len(line) * 31 * hk * LINE_WIDTH for line in lines])
    return x, y - size, width, size + (44 + 38 * len(lines)) * hk


def _touch(a: tuple, b: tuple, gap: float) -> bool:
    return a[0] < b[0] + b[2] + gap and b[0] < a[0] + a[2] + gap and a[1] < b[1] + b[3] + gap and b[1] < a[1] + a[3] + gap


def _same_series(a, b) -> bool:
    """Řada stejných obrazů (vzorky betonu, gladiátoři) drží pohromadě i přes větší mezeru."""
    return a is not None and b is not None and a["typ"] == b["typ"] and abs(a["rect"][2] - b["rect"][2]) < 0.03 * a["rect"][2] and abs(a["rect"][3] - b["rect"][3]) < 0.03 * a["rect"][3]


def make_blocks(doc: dict) -> list[dict]:
    """[{box, members (index panelu, nebo "nadpis"), poradi}], nejdůležitější první."""
    k = page_k(doc)
    items = [(i, panel_box(p, k), p["poradi"], p) for i, p in enumerate(doc["panels"])]
    if doc.get("title"):
        items.append(("nadpis", head_box(doc, k), 0, None))
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
    """[(blok, měřítko, x, y)]. Hlavní blok dostane co nejvíc plochy, ostatní se přizpůsobí, dokud nejsou menší než MIN_REST originálu."""
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
    best, best_score = None, (-1.0, -1.0, -1.0)
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
                if (sh, hero_area, sh) > best_score:
                    best, best_score = (side, sh, None, None, False, area), (sh, hero_area, sh)
                continue
            if min(area) <= 0:
                continue
            found = _best_fill(others, area[0], area[1], gap)
            if not found:
                continue
            s, lines, tall = found
            s = min(s, sh)      # nic není větší než hlavní obraz
            if hero_area < max(b["box"][2] * b["box"][3] for b in others) * s * s:
                continue
            score = (min(s, MIN_REST), hero_area, s)    # nad MIN_REST rozhoduje velikost hlavního obrazu
            if score > best_score:
                best, best_score = (side, sh, s, lines, tall, area), score
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


def _note_without(note: str, names: set[str]) -> str:
    """Patička bez vynechaných panelů. Co nepozná přesně podle jména, nechá: označení AI nesmí zmizet omylem."""
    parts = []
    for part in note.split("; "):
        head, colon, tail = part.partition(":")
        left = [name for name in head.split(", ") if name not in names]
        if colon and left:
            parts.append(f"{', '.join(left)}:{tail}")
        elif not colon:
            parts.append(part)
    return "; ".join(parts)


def omit(doc: dict, panely: list[str], popisky: dict[str, list[int]]) -> dict:
    """Dokument bez toho, co vybral editor: celé panely a řádky podle pořadí (popisky obrazu, položky textu). Kód sám nic nevyhazuje. Vstup se nemění."""
    known = {p["id"] for p in doc["panels"]}
    unknown = [pid for pid in [*panely, *popisky] if pid not in known]
    if unknown:
        raise InfoError(f"neznámý panel: {', '.join(unknown)}")
    kept, gone = [], [p for p in doc["panels"] if p["id"] in panely]
    for p in doc["panels"]:
        if p["id"] in panely:
            continue
        rows = "labels" if p["typ"] == "obraz" else "items"
        drop = popisky.get(p["id"], [])
        if any(rows not in p or not 0 <= i < len(p[rows]) for i in drop):
            raise InfoError(f"panel {p['id']}: takový řádek nemá")
        if not drop:
            kept.append(p)
            continue
        left = [row for i, row in enumerate(p[rows]) if i not in drop]
        if left or rows == "labels":
            kept.append({**p, rows: left})
        else:
            gone.append(p)      # text bez jediného řádku není panel
    if not any(p["typ"] == "obraz" for p in kept):
        raise InfoError("musí zůstat aspoň jeden obraz")
    out = {**doc, "panels": kept}
    if gone:
        out["ai_note"] = _note_without(doc.get("ai_note") or "", {p["nazev"] for p in gone})
        if doc.get("ai_generated"):
            out["ai_generated"] = "(AI)" in out["ai_note"]
    return out


def hero_share(doc: dict) -> float:
    """Kolik stránky zabírá hlavní obraz."""
    W, H = canvas_size(doc["size"])
    rect = min((p for p in doc["panels"] if p["typ"] == "obraz"), key=lambda p: p["poradi"])["rect"]
    return rect[2] * rect[3] / (W * H)


def reformat(doc: dict, size: str) -> dict:
    """Pole nového dokumentu: stejné panely, texty a soubory, jiné plátno. Vstup se nemění."""
    W, H = canvas_size(size)
    k = page_k(doc)
    new_k = k * ((W * H) / (canvas_size(doc["size"])[0] * canvas_size(doc["size"])[1])) ** 0.5
    note = short_note(doc)
    lines = wrap(note, round((W - 100 * new_k) / (17 * new_k * LINE_WIDTH)))
    foot = 30 * new_k + len(lines) * 22 * new_k if lines else 0
    blocks = make_blocks(doc)
    panels_out = list(doc["panels"])
    head = None
    for block, s, nx, ny in arrange(blocks, W, H, foot, new_k):
        bx, by = block["box"][:2]
        for member in block["members"]:
            if member == "nadpis":
                old = doc.get("nadpis") or {}
                hk = old.get("k", k)
                head = {"x": (old.get("x", 50 * hk) - bx) * s + nx, "y": (old.get("y", 118 * hk) - by) * s + ny, "size": old.get("size", 88 * hk) * s, "k": hk * s}
            else:
                panels_out[member] = _move_panel(doc["panels"][member], s, (bx, nx), (by, ny), doc["panels"][member].get("k", k))
    for p in panels_out:
        if p["typ"] in ("fakta", "text", "osa"):    # rám textu je širší než text sám, kreslí se z něj jen to, co je v `_text_extent`
            x, y, w, h = p["rect"]
            p["rect"] = [x, y, min(w, W - x), min(h, H - y)]
    fields = {**doc, "size": size, "panels": panels_out, "meritko": new_k, "predelano_z": {"id": doc["id"], "size": doc["size"]}}
    if head:
        fields["nadpis"] = head
    return fields
