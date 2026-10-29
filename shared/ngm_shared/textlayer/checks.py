"""Deterministické kontroly vektorové vrstvy — bez modelu, z geometrie a pixelů podkladu.

Každá kontrola vrací nálezy `{"level": "error"|"warn", "code", "msg", "ids"}`;
seznam `passed` říká, které kontroly proběhly bez nálezu (aby „0 nálezů“ šlo
rozlišit od „kontrola se nespustila“).

| kód | co hlídá | zdroj pravidla |
|-----|----------|----------------|
| `typo_eth` | Đ/đ (chorvatské D) místo Ð/ð (eth) | review Vikingové (5) |
| `typo_dash` | spojovník mezi čísly, `-` s mezerami, svislice `|` | ČSN 01 6910, review (6) |
| `typo_digit` | číslice v NeoGothic/Bumstead (1 vypadá jako I) | render 2026-10-08, review (9) |
| `font` | náhradní řez nebo chybějící znaky písma | `text.fonts` VectorCraftu |
| `collision` | překryv textů (včetně halo) a textu se značkou | NG str. 22 „no doubt what feature“ |
| `margin` | text v bezpečném okraji | 4 % kratší strany |
| `contrast` | kontrast textu proti nejhoršímu okolí bez halo / proti halo | WCAG 3:1 velký text |
| `place` | značka/cíl odkazu ve vodě, popisek moře na pevnině | review (2), (11) |
| `leader` | čára začíná v textu nebo jím prochází | review (10) |
| `note` | poznámka odtržená od názvu | review (12) |
| `route` | šipka míří jinam, než říká `heading` | review (1) |
| `scale` | měřítko na perspektivním pohledu / bez reference | review (3), NG str. 17 |
| `north` | písmeno S není nad hrotem severky | review (13) |
| `legend` | číslo značky bez položky v legendě a naopak | review (8) |
| `overflow` | text po křivce je delší než křivka (konec se usekne) | render 2026-10-08 |
| `numbers` | číslo v popisku, které v článku není | jako kontrola čísel infografik |
| `terms` | známý chybný český termín (vnitrozemský ledovec → pevninský ledovec) | review (7) |

Kopie z NG-ROBOT `ng_vector_labels/checks.py`, commit f27580e9534a408e35b153d06376e4d34697b092
(2026-10-29, GRAFIK fáze 3). Opravy z NG-ROBOT přenášej diffem originálu od tohoto commitu:
`git -C NG-ROBOT diff f27580e9 -- ng_vector_labels/checks.py`.
Změny proti originálu: jen importy (`ngm_shared.textlayer`).
"""

from __future__ import annotations

import math
import re
from typing import Iterable

from ngm_shared.textlayer import style as st
from ngm_shared.textlayer.layout import HEADINGS
from ngm_shared.textlayer.raster import WATER_LABEL, Base

TEXT_TYPES = ("header", "label", "note", "route_label", "legend", "credit", "north", "scale")

_ETH_WRONG = re.compile(r"[Đđ]")
_DIGIT_HYPHEN = re.compile(r"\d\s?-\s?\d")
_SPACED_HYPHEN = re.compile(r"\s-\s")


def _f(level: str, code: str, msg: str, ids: Iterable[str] = ()) -> dict:
    return {"level": level, "code": code, "msg": msg, "ids": list(ids)}


def _overlap(a: tuple, b: tuple, pad_a: float = 0.0, pad_b: float = 0.0) -> float:
    """Plocha překryvu dvou obdélníků (x, y, w, h) zvětšených o pad."""
    ax0, ay0 = a[0] - pad_a, a[1] - pad_a
    ax1, ay1 = a[0] + a[2] + pad_a, a[1] + a[3] + pad_a
    bx0, by0 = b[0] - pad_b, b[1] - pad_b
    bx1, by1 = b[0] + b[2] + pad_b, b[1] + b[3] + pad_b
    w = min(ax1, bx1) - max(ax0, bx0)
    h = min(ay1, by1) - max(ay0, by0)
    return w * h if w > 0 and h > 0 else 0.0


def _seg_hits_rect(p: list, q: list, r: tuple) -> bool:
    """Protíná úsečka p–q obdélník r (x, y, w, h)? (vzorkování po 1/40 délky)"""
    for i in range(41):
        t = i / 40
        x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
        if r[0] < x < r[0] + r[2] and r[1] < y < r[1] + r[3]:
            return True
    return False


def _bearing(dx: float, dy: float) -> float:
    """Úhel ve stupních, 0 = východ, 90 = sever (osa y míří dolů)."""
    return math.degrees(math.atan2(-dy, dx))


def _angle_diff(a: float, b: float) -> float:
    d = (a - b + 180) % 360 - 180
    return abs(d)


def _compass(deg: float) -> str:
    return min(HEADINGS, key=lambda k: _angle_diff(HEADINGS[k], deg))


def _texts(els: list) -> list:
    return [e for e in els if e["type"] in TEXT_TYPES and e.get("text")]


def check_typography(els: list) -> list:
    out = []
    for e in _texts(els):
        t = e["text"]
        if _ETH_WRONG.search(t):
            fixed = t.replace("Đ", "Ð").replace("đ", "ð")
            out.append(_f("error", "typo_eth", f"„{t}“: Đ (chorvatské D s pruhem) místo Ð (eth) — "
                                               f"správně „{fixed}“", [e["id"]]))
        if _DIGIT_HYPHEN.search(t) or _SPACED_HYPHEN.search(t):
            out.append(_f("error", "typo_dash", f"„{t}“: rozsah a vsuvka se píšou pomlčkou – (U+2013), "
                                                "ne spojovníkem -", [e["id"]]))
        if "|" in t and e["type"] != "legend":
            out.append(_f("warn", "typo_dash", f"„{t}“: svislice | v písmu vypadá jako I — použijte "
                                               "pomlčku nebo dva řádky", [e["id"]]))
        fam = (e.get("font") or [""])[0]
        if fam in st.DIGIT_UNSAFE_FONTS and re.search(r"\d", t) and not e.get("digit_font"):
            out.append(_f("error", "typo_digit", f"„{t}“: číslice v písmu {fam} (1 vypadá jako I)", [e["id"]]))
    return out


# Chybné české termíny, které se v infografikách opakují (vzor → správně). Rozšiřuj po nálezu.
_TERMS = ((re.compile(r"vnitrozemsk\w*\s+ledov", re.IGNORECASE), "pevninský ledovec"),)


def check_terms(els: list) -> list:
    out = []
    for e in _texts(els):
        for pat, right in _TERMS:
            m = pat.search(e["text"])
            if m:
                out.append(_f("error", "terms", f"„{e['text']}“: „{m.group(0)}…“ — česky {right}", [e["id"]]))
    return out


def check_fonts(fonts: list) -> list:
    out = []
    for f in fonts or []:
        name = f"{f.get('family')} {f.get('style')}"
        if f.get("status") != "exact":
            res = f.get("resolved") or {}
            out.append(_f("error", "font", f"Písmo {name} chybí, nahrazeno {res.get('family')} {res.get('style')}"))
        if f.get("missingGlyphs"):
            out.append(_f("error", "font", f"Písmu {name} chybí {f['missingGlyphs']} znaků (kreslí je jiné písmo)"))
    return out


def _boxes(e: dict) -> list:
    """Plocha prvku: u textu po křivce řada čtverečků podél písma, jinak jeho obdélník."""
    return e.get("footprint") or [e["bbox"]]


def _hits(a: dict, b: dict, pad_a: float = 0, pad_b: float = 0) -> bool:
    return any(_overlap(x, y, pad_a, pad_b) > 0 for x in _boxes(a) for y in _boxes(b))


def check_collisions(els: list) -> list:
    out = []
    texts = [e for e in _texts(els) if e["type"] != "scale"]
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            if a.get("parent") == b["id"] or b.get("parent") == a["id"]:
                if _hits(a, b):
                    out.append(_f("error", "collision", f"„{a['text']}“ a „{b['text']}“ se překrývají",
                                  [a["id"], b["id"]]))
                continue
            if _hits(a, b, a.get("halo_pad", 0), b.get("halo_pad", 0)):
                out.append(_f("error", "collision", f"„{a['text']}“ a „{b['text']}“ se překrývají",
                              [a["id"], b["id"]]))
    markers = [e for e in els if e["type"] == "marker"]
    for t in texts:
        for m in markers:
            if _hits(t, m, t.get("halo_pad", 0)):
                out.append(_f("warn", "collision", f"„{t['text']}“ zakrývá značku {m.get('text') or m['id']}",
                              [t["id"], m["id"]]))
    return out


def check_margins(els: list, W: float, H: float) -> list:
    out = []
    m = st.SAFE_MARGIN * min(W, H) * 0.98
    for e in _texts(els) + [e for e in els if e["type"] == "marker"]:
        x, y, w, h = e["bbox"]
        if x < m or y < m or x + w > W - m or y + h > H - m:
            what = f"„{e['text']}“" if e.get("text") else e["id"]
            out.append(_f("error", "margin", f"{what} zasahuje do okraje (bezpečný okraj {st.SAFE_MARGIN:.0%})",
                          [e["id"]]))
        if e.get("shifted"):
            dx, dy = e["shifted"]
            out.append(_f("warn", "margin", f"„{e['text']}“ posunut dovnitř o {math.hypot(dx, dy):.0f} bodů — "
                                            "zkontrolujte, že pořád patří ke svému místu", [e["id"]]))
    return out


def check_contrast(els: list, base: Base) -> list:
    out = []
    for e in _texts(els):
        if not e.get("color") or e["type"] in ("legend", "scale"):
            continue
        x, y, w, h = e["bbox"]
        dark, light = base.bg_percentiles(x, y, w, h)
        worst = min(st.contrast(e["color"], dark), st.contrast(e["color"], light))
        if e.get("halo"):
            halo_c = st.contrast(e["color"], e["halo"])
            if halo_c < st.MIN_CONTRAST:
                out.append(_f("error", "contrast", f"„{e['text']}“: text a halo mají kontrast jen {halo_c:.1f}:1",
                              [e["id"]]))
            elif worst < 1.5:
                out.append(_f("warn", "contrast", f"„{e['text']}“: pozadí je místy skoro stejné barvy jako text "
                                                  f"({worst:.1f}:1), drží ho jen halo", [e["id"]]))
        elif worst < st.MIN_CONTRAST:
            out.append(_f("error", "contrast", f"„{e['text']}“: kontrast {worst:.1f}:1 (min. 3:1)", [e["id"]]))
    return out


def check_placement(els: list, base: Base, W: float) -> list:
    out = []
    r = 0.006 * W
    for e in els:
        exp = e.get("expect")
        if not exp or exp == "any" or not e.get("point"):
            continue
        x, y = e["point"]
        got, share = base.classify(x, y, r)
        if got == exp:
            continue
        if e.get("geo") and exp == "land" and got == "coast":
            continue        # přístav ze souřadnic: na skutečném pobřeží je to správně
        name = e.get("text") or e["id"]
        if e["type"] == "leader":
            parent = next((p for p in els if p["id"] == e.get("parent")), {})
            name = f"odkaz od „{parent.get('text', e.get('parent'))}“"
        elif e["type"] == "marker":
            name = f"značka {e.get('text') or e['id']}"
        else:
            name = f"„{name}“"
        level = "warn" if got == "coast" else "error"
        want = WATER_LABEL.get(exp, WATER_LABEL["land"])
        msg = f"{name} leží {WATER_LABEL[got]} (voda {share:.0%} okolí), má ležet {want}"
        near = base.nearest(x, y, exp, max_r=0.06 * W, r=r)
        if near:
            msg += f"; nejbližší vhodné místo [{near[0] / base.width * 100:.1f}, {near[1] / base.height * 100:.1f}] %"
        out.append(_f(level, "place", msg, [e["id"]]))
    return out


def check_leaders(els: list) -> list:
    out = []
    by_id = {e["id"]: e for e in els}
    texts = _texts(els)
    for e in els:
        if not e.get("leader"):
            continue
        start, end = e["leader"]
        x, y, w, h = e["bbox"]
        inside = x - 1 <= start[0] <= x + w + 1 and y - 1 <= start[1] <= y + h + 1
        if inside:
            out.append(_f("error", "leader", f"Odkazová čára „{e['text']}“ začíná uvnitř textu", [e["id"]]))
        for t in texts:
            if t["id"] in (e["id"], f"{e['id']}__note"):
                continue
            if _seg_hits_rect(start, end, t["bbox"]):
                out.append(_f("error", "leader", f"Odkazová čára „{e['text']}“ přetíná text „{t['text']}“",
                              [e["id"], t["id"]]))
        own_note = by_id.get(f"{e['id']}__note")
        if own_note and _seg_hits_rect(start, end, own_note["bbox"]):
            out.append(_f("error", "leader", f"Odkazová čára „{e['text']}“ škrtá vlastní poznámku", [e["id"]]))
    return out


def check_notes(els: list) -> list:
    out = []
    by_id = {e["id"]: e for e in els}
    for e in els:
        if e["type"] != "note":
            continue
        p = by_id.get(e.get("parent"))
        if not p:
            continue
        gap = e["bbox"][1] - (p["bbox"][1] + p["bbox"][3])
        hx = min(p["bbox"][0] + p["bbox"][2], e["bbox"][0] + e["bbox"][2]) - max(p["bbox"][0], e["bbox"][0])
        if gap > 1.2 * p["size"] or gap < -0.2 * p["size"] or hx <= 0:
            out.append(_f("error", "note", f"Poznámka „{e['text']}“ je odtržená od „{p['text']}“",
                          [e["id"], p["id"]]))
    return out


def check_routes(els: list) -> list:
    out = []
    for e in els:
        if e["type"] != "route":
            continue
        pts = e.get("points") or []
        if len(pts) < 2:
            continue
        if not e.get("heading"):
            out.append(_f("warn", "route", f"Trasa {e.get('text') or e['id']}: chybí směr (heading), "
                                           "šipku nejde ověřit", [e["id"]]))
            continue
        tail = pts[max(0, int(len(pts) * 0.8) - 1)]
        dx, dy = pts[-1][0] - tail[0], pts[-1][1] - tail[1]
        got = _bearing(dx, dy)
        want = HEADINGS[e["heading"]]
        if _angle_diff(got, want) > 60:
            out.append(_f("error", "route", f"Šipka trasy „{e.get('text') or e['id']}“ míří na {_compass(got)}, "
                                            f"má mířit na {e['heading']}", [e["id"]]))
    return out


def check_overflow(els: list) -> list:
    out = []
    for e in els:
        w, ln = e.get("text_width"), e.get("path_len")
        if w and ln and ln < w * 1.02:
            out.append(_f("error", "overflow", f"„{e['text']}“ se na křivku nevejde ({ln:.0f} z {w:.0f} bodů) "
                                               "— konec textu se usekne", [e["id"]]))
    return out


_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_THOUSANDS = re.compile(r"(?<=\d)[ \u00a0\u202f](?=\d{3}\b)")


def check_numbers(els: list, article: str) -> list:
    """Čísla v popiscích (ne čísla značek) musí stát v článku; bez článku se kontrola neprovede."""
    if not article:
        return []
    joined = _THOUSANDS.sub("", article)          # oddělovače tisíců: 3 000 → 3000
    known = set(_NUMBER.findall(article)) | set(_NUMBER.findall(joined))
    known |= {n.replace(",", ".") for n in known}
    out = []
    for e in _texts(els):
        if e["type"] in ("legend", "scale"):
            continue
        for num in _NUMBER.findall(e["text"]):
            if num not in known and num.replace(",", ".") not in known:
                out.append(_f("warn", "numbers", f"„{e['text']}“: číslo {num} v článku není", [e["id"]]))
    return out


def check_scale(layout: dict, skipped: list) -> list:
    out = []
    sc = layout.get("scale")
    if not sc:
        return out
    why = next((s["reason"] for s in skipped if s.get("id") == "scale"), None)
    if layout.get("view") != "plan":
        out.append(_f("error", "scale", "Měřítko na perspektivním (nebo neurčeném) pohledu nekreslíme — "
                                        "vzdálenosti se v něm mění. Buď `view: plan`, nebo poznámka "
                                        "„Měřítko se v perspektivě mění“.", ["scale"]))
    elif why:
        out.append(_f("error", "scale", f"Měřítko chybí: {why}", ["scale"]))
    return out


def check_north(els: list) -> list:
    out = []
    for e in els:
        if e["type"] != "north" or not e.get("points"):
            continue
        letter_bottom, tip = e["points"]
        if letter_bottom[1] > tip[1]:
            out.append(_f("error", "north", "Písmeno S severky není nad hrotem šipky", [e["id"]]))
    return out


def check_legend(layout: dict) -> list:
    out = []
    numbered = {str(m.get("n")) for m in layout.get("markers") or [] if m.get("n")}
    entries = {str(e.get("n")) for e in (layout.get("legend") or {}).get("entries", []) if e.get("n")}
    for n in sorted(numbered - entries):
        out.append(_f("error", "legend", f"Značka {n} nemá vysvětlení v legendě", [f"marker_{n}"]))
    for n in sorted(entries - numbered):
        out.append(_f("error", "legend", f"Legenda vysvětluje {n}, ale značka {n} na mapě není", ["legend"]))
    texts = [str(e.get("text", "")).strip().lower() for e in (layout.get("legend") or {}).get("entries", [])]
    dup = {t for t in texts if texts.count(t) > 1}
    if dup:
        out.append(_f("warn", "legend", f"Legenda opakuje položku: {', '.join(sorted(dup))}", ["legend"]))
    return out


CHECKS = ("typo_eth", "typo_dash", "typo_digit", "font", "collision", "margin", "contrast", "place",
          "leader", "note", "route", "scale", "north", "legend", "overflow", "numbers", "terms")


def run_all(comp: dict, layout: dict, base: Base, article: str = "") -> dict:
    """Všechny kontroly nad `Composition.to_dict()`; vrací {findings, passed, errors, warnings}."""
    els = comp["elements"]
    W, H = comp["width"], comp["height"]
    findings = (check_typography(els) + check_fonts(comp.get("fonts")) + check_collisions(els)
                + check_margins(els, W, H) + check_contrast(els, base) + check_placement(els, base, W)
                + check_leaders(els) + check_notes(els) + check_routes(els) + check_scale(layout, comp["skipped"])
                + check_north(els) + check_legend(layout) + check_overflow(els)
                + check_numbers(els, article) + check_terms(els))
    hit = {f["code"] for f in findings}
    if not article:
        hit.add("numbers")      # neproběhla — nesmí se tvářit jako „bez nálezu“
    return {
        "findings": findings,
        "passed": [c for c in CHECKS if c not in hit],
        "errors": sum(1 for f in findings if f["level"] == "error"),
        "warnings": sum(1 for f in findings if f["level"] == "warn"),
    }
