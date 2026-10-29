"""Rozložení vektorové vrstvy (`infographic_NN_ngvector_layout.json`, verze 2).

Souřadnice jsou v procentech podkladu, `[x, y]`, 0–100, počátek vlevo nahoře.

```
{
  "version": 2, "idx": "01", "base": "infographic_01_visual.png",
  "kind": "map", "view": "perspective" | "plan", "display_width": 800,
  "header":  {"title": "...", "subtitle": "...", "at": [50, 6]},
  "labels":  [{"id", "text", "kind", "at", "anchor"?, "offset"?, "path"?, "note"?, "leader_to"?,
               "expect"?, "color"?, "size"?}],
  "markers": [{"id", "at", "n"?, "kind": "numbered" | "town" | "capital" | "peak" | "airport", "expect"?,
               "scale"?}],
  "routes":  [{"id", "points": [[x, y], ...], "heading"?: "V", "label"?, "dashed"?}],
  "legend":  {"at", "title"?, "entries": [{"n", "text"}]},
  "north":   {"at"},
  "scale":   {"at", "km", "ref": {"a", "b", "km"}},
  "credit":  {"text", "at"}
}
```

`offset` posune text popisku o `[dx, dy]` px (při `display_width`) od místa `at` —
popisek osady tak stojí vedle tečky bez odkazové čáry.
`scale` značky sídla = násobek tečky podle velikosti sídla (`map_styles.town_size`).

`view` rozhoduje o měřítku: na perspektivním pohledu se vzdálenosti mění, takže
se měřítko nekreslí (NG: „Scale varies in this perspective“). `heading` trasy je
světová strana, kam má šipka mířit (S, SV, V, JV, J, JZ, Z, SZ) — kontrola ji
porovná se skutečným směrem posledního úseku.

Starý formát (`text_overlays` z fáze 11 / infographic-designer) převede
`from_legacy`; co z něj nejde vyčíst (pohled, směr trasy), zůstane prázdné
a kontroly to ohlásí.

Kopie z NG-ROBOT `ng_vector_labels/layout.py`, commit f27580e9534a408e35b153d06376e4d34697b092
(2026-10-29, GRAFIK fáze 3). Opravy z NG-ROBOT přenášej diffem originálu od tohoto commitu:
`git -C NG-ROBOT diff f27580e9 -- ng_vector_labels/layout.py`.
Změny proti originálu: bez zeměpisných poloh (`georef`, `{lat, lon}` → procenta přes `geo.py`);
ty patří KARTOGRAFU. `at` a body tras jsou tu vždy `[x, y]` v procentech.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from ngm_shared.textlayer.style import DEFAULT_DISPLAY_WIDTH, FEATURES

VERSION = 2
VIEWS = ("plan", "perspective")
HEADINGS = {"S": 90, "SV": 45, "V": 0, "JV": -45, "J": -90, "JZ": -135, "Z": 180, "SZ": 135}
_ANCHORS = ("center", "left", "right")


class LayoutError(ValueError):
    """Rozložení nejde složit (chybí text, souřadnice mimo obrázek…)."""


def _pt(value: Any, where: str) -> list:
    if isinstance(value, dict):
        raise LayoutError(f"{where}: zeměpisnou polohu {{lat, lon}} tahle kopie nepřepočítává, pošlete [x, y] v procentech (mapu z dat staví KARTOGRAF)")
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or not all(isinstance(v, (int, float)) for v in value)):
        raise LayoutError(f"{where}: souřadnice musí být [x, y] v procentech")
    x, y = float(value[0]), float(value[1])
    if not (0 <= x <= 100 and 0 <= y <= 100):
        raise LayoutError(f"{where}: souřadnice {value} leží mimo obrázek (0–100 %)")
    return [x, y]


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LayoutError(f"{where}: chybí text")
    return value.strip()


class _Errors(list):
    """Sběr chyb — `guard` zavolá ověření a chybu si zapíše místo vyhození."""

    def guard(self, fn, *args):
        try:
            return fn(*args)
        except LayoutError as e:
            self.append(str(e))
            return None

    def points(self, pts, where: str, what: str) -> list:
        if not isinstance(pts, list) or len(pts) < 2:
            self.append(f"{where}: {what} potřebuje aspoň 2 body")
            return [[0, 0], [1, 1]]
        return [self.guard(_pt, p, where) or [0, 0] for p in pts]


def _label(it: dict, where: str, err: _Errors) -> None:
    it["text"] = err.guard(_text, it.get("text"), where) or ""
    if it.get("kind") not in FEATURES:
        err.append(f"{where}: neznámý druh {it.get('kind')!r} (povolené: {', '.join(sorted(FEATURES))})")
    it["at"] = err.guard(_pt, it.get("at"), where) or [50, 50]
    if it.get("anchor") not in _ANCHORS:
        it["anchor"] = "center"
    off = it.get("offset")
    if off is not None and (not isinstance(off, (list, tuple)) or len(off) != 2
                            or not all(isinstance(v, (int, float)) and abs(v) <= 200 for v in off)):
        err.append(f"{where}: offset musí být [dx, dy] v px (nejvýš 200)")
    if it.get("leader_to") is not None:
        it["leader_to"] = err.guard(_pt, it["leader_to"], where + " (leader_to)")
    if it.get("path") is not None:
        it["path"] = err.points(it["path"], where, "path")


def _marker(it: dict, where: str, err: _Errors) -> None:
    it["at"] = err.guard(_pt, it.get("at"), where) or [50, 50]
    it.setdefault("kind", "numbered" if it.get("n") else "town")
    it.setdefault("expect", "land")
    sc = it.get("scale")
    if sc is not None and (not isinstance(sc, (int, float)) or not 0.3 <= sc <= 3):
        err.append(f"{where}: scale značky je násobek tečky 0,3–3")


def _route(it: dict, where: str, err: _Errors) -> None:
    it["points"] = err.points(it.get("points"), where, "trasa")
    if it.get("heading") is not None and it["heading"] not in HEADINGS:
        err.append(f"{where}: směr {it['heading']!r} není světová strana ({', '.join(HEADINGS)})")


_GROUPS = (("labels", _label), ("markers", _marker), ("routes", _route))


def _groups(lay: dict, err: _Errors) -> None:
    seen: set = set()
    for group, check in _GROUPS:
        items = lay.get(group) or []
        if not isinstance(items, list):
            err.append(f"{group}: musí být seznam")
            items = []
        lay[group] = items
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                err.append(f"{group}[{i}]: musí být objekt")
                continue
            it.setdefault("id", f"{group[:-1]}_{i + 1}")
            if it["id"] in seen:
                err.append(f"{group}[{i}]: id {it['id']} se opakuje")
            seen.add(it["id"])
            check(it, f"{group}/{it['id']}", err)


def _extras(lay: dict, err: _Errors) -> None:
    head = lay.get("header")
    if head:
        if not isinstance(head, dict) or not str(head.get("title") or "").strip():
            err.append("header: chybí titulek")
        else:
            head["at"] = err.guard(_pt, head.get("at", [50, 6]), "header") or [50, 6]
    leg = lay.get("legend")
    if leg:
        if not isinstance(leg, dict) or not isinstance(leg.get("entries"), list) or not leg["entries"]:
            err.append("legend: chybí položky")
        else:
            leg["at"] = err.guard(_pt, leg.get("at", [5, 50]), "legend") or [5, 50]
            if any(not isinstance(e, dict) or not str(e.get("text") or "").strip() for e in leg["entries"]):
                err.append("legend: položka bez textu")
    for key in ("north", "scale", "credit"):
        obj = lay.get(key)
        if not obj:
            continue
        if not isinstance(obj, dict):
            err.append(f"{key}: musí být objekt")
            continue
        obj["at"] = err.guard(_pt, obj.get("at"), key) or [50, 95]


def normalize(layout: dict) -> dict:
    """Ověří a doplní výchozí hodnoty. Vstup nemění; chyby hlásí všechny najednou."""
    if not isinstance(layout, dict):
        raise LayoutError("Rozložení musí být objekt JSON")
    if "text_overlays" in layout and "labels" not in layout:
        layout = from_legacy(layout)
    lay = deepcopy(layout)
    lay["version"] = VERSION
    lay.setdefault("kind", "map")
    if lay.get("view") not in VIEWS:
        lay["view"] = None          # neznámý pohled = měřítko se nekreslí, kontrola to ohlásí
    lay["display_width"] = float(lay.get("display_width") or DEFAULT_DISPLAY_WIDTH)
    err = _Errors()
    _groups(lay, err)
    _extras(lay, err)
    if err:
        raise LayoutError("; ".join(err))
    return lay


# --------------------------------------------------------------------------- legacy

_WATER_WORDS = (("oceán", "ocean"), ("moře", "sea"), ("ledov", "glacier"), ("záliv", "water"),
                ("průliv", "water"), ("fjord", "water"), ("jezer", "water"), ("řeka", "water"))
_LEGEND_ROW = re.compile(r"^\s*(\d+)[.)]?\s+(.+?)\s*$")


def _legacy_kind(ov: dict) -> str:
    text = str(ov.get("content") or "").lower()
    hint = str(ov.get("font_hint") or "").lower()
    role = str(ov.get("role") or "label").lower()
    for word, kind in _WATER_WORDS:
        if word in text:
            return kind
    if hint.startswith("caption"):
        return "ocean" if "caps" in hint else "water"
    if hint.startswith("bumstead"):
        return "physical" if "caps" in hint else "physical_small"
    if hint.startswith("neo_gothic_heavy"):
        return "region"
    if hint.startswith("neo_gothic"):
        return "town"
    if role in ("callout", "caption") or "italic" in hint:
        return "annotation"
    return "site"


def _xy(pos: dict, default=(50.0, 50.0)) -> list:
    try:
        return [float(pos.get("x_pct", default[0])), float(pos.get("y_pct", default[1]))]
    except (TypeError, ValueError, AttributeError):
        return list(default)


def from_legacy(old: dict) -> dict:
    """Převede `text_overlays` (fáze 11 / infographic-designer) na rozložení v2."""
    lay: dict = {"version": VERSION, "kind": old.get("subtype") or "map", "view": None,
                 "labels": [], "markers": [], "routes": [], "legacy_source": old.get("source")}
    if old.get("infographic_idx"):
        lay["idx"] = str(old["infographic_idx"]).zfill(2)
    head: dict = {}
    for ov in old.get("text_overlays") or []:
        if not isinstance(ov, dict):
            continue
        role = str(ov.get("role") or "label").lower()
        pos = ov.get("position") or {}
        text = str(ov.get("content") or "").strip()
        if role == "title":
            head.update(title=text, at=_xy(pos, (50, 6)))
        elif role == "subtitle":
            head["subtitle"] = text
        elif role == "numbered_marker":
            lay["markers"].append({"id": ov.get("id"), "at": _xy(pos), "n": text or None, "kind": "numbered"})
        elif role == "scale_bar":
            lay["scale"] = {"at": _xy(pos, (60, 94)), "km": None, "legacy_label": ov.get("label") or text}
        elif role == "legend" and "sever" in text.lower():
            lay["north"] = {"at": _xy(pos, (8, 92))}
        elif "\n" in text and all(_LEGEND_ROW.match(r) for r in text.splitlines() if r.strip()):
            rows = [_LEGEND_ROW.match(r) for r in text.splitlines() if r.strip()]
            lay["legend"] = {"at": _xy(pos, (5, 50)),
                             "entries": [{"n": m.group(1), "text": m.group(2)} for m in rows]}
        elif text:
            label = {"id": ov.get("id"), "text": text, "kind": _legacy_kind(ov), "at": _xy(pos),
                     "anchor": pos.get("anchor") if pos.get("anchor") in _ANCHORS else "center"}
            co = ov.get("callout_to")
            if isinstance(co, dict) and "x_pct" in co:
                label["leader_to"] = _xy(co)
            lay["labels"].append(label)
    if head.get("title"):
        lay["header"] = head
    return lay
