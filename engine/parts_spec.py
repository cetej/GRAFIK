"""Popis stavby z dílů (JSON) a jeho kontrola. Staví `engine/blender/lod_parts.py`, žádný generovaný kód se nespouští.

Osy: x podél delší strany, y napříč, z nahoru, střed stavby v počátku, metry. Základ všeho kulatého je elipsa `osy` [a, b]
(poloosy) a poloha na ní se udává odsazením od obrysu: kružnice je a = b, nebo [0, 0] a odsazení je přímo poloměr.

Tvar vznikl zobecněním `scripts/3d/lod_pantheon.py` (rotunda, kupole s kazetami, portik, sloupy, zeď) a přidáním elipsy,
arkád a hlediště. Každé číslo patří do `dim` nebo do dílu, u ne-doložených rozměrů to řeší `zdroje`: co nemá fakt z dossieru, je `odhad`.
"""
from __future__ import annotations

import math
import re

MAX_PARTS = 80
MAX_COUNT = 400
MAX_METRES = 2000.0
SOLID = ("prstenec", "hlediste", "kopule", "kvadr", "disk")
LOOSE = ("sloupy", "portik")
CUTS = ("arkady", "vyrez")
KINDS = SOLID + LOOSE + CUTS
MATERIALS = ("travertin", "tuf", "cihla", "beton", "mramor", "zula", "bronz", "strecha", "pisek", "kamen")
NAME = re.compile(r"[a-z0-9_]{1,40}")


class SpecError(ValueError):
    """Popis nejde postavit; zpráva říká který díl a proč, model ji dostane v dalším kole."""


def _num(part: str, key: str, value, lo: float = -MAX_METRES, hi: float = MAX_METRES) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SpecError(f"{part}: {key} není číslo ({value!r})")
    if not lo <= value <= hi:
        raise SpecError(f"{part}: {key} = {value} je mimo rozsah {lo} až {hi}")
    return float(value)


def _pair(part: str, key: str, value, lo: float = -MAX_METRES, hi: float = MAX_METRES) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise SpecError(f"{part}: {key} musí být dvě čísla")
    return [_num(part, key, v, lo, hi) for v in value]


def _triple(part: str, key: str, value) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise SpecError(f"{part}: {key} musí být tři čísla")
    return [_num(part, key, v) for v in value]


def _count(part: str, key: str, value, lo: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= MAX_COUNT:
        raise SpecError(f"{part}: {key} musí být celé číslo {lo} až {MAX_COUNT} ({value!r})")
    return value


def _axes(name: str, raw: dict) -> list[float]:
    return _pair(name, "osy", raw.get("osy", [0, 0]), 0.0)


def _intervals(name: str, raw: dict) -> list[list[float]]:
    return [_pair(name, "vyjma", v, -720, 720) for v in raw.get("vyjma", [])]


def _ring(name: str, raw: dict) -> dict:
    axes = _axes(name, raw)
    profile = raw.get("profil")
    if not isinstance(profile, list) or not 3 <= len(profile) <= 200:
        raise SpecError(f"{name}: profil musí být 3 až 200 bodů [odsazení, z]")
    points = [_pair(name, "profil", p) for p in profile]
    if min(axes) + min(p[0] for p in points) < 0:
        raise SpecError(f"{name}: odsazení {min(p[0] for p in points)} přechází přes střed elipsy {axes}")
    return {"osy": axes, "profil": points}


def _seating(name: str, raw: dict) -> dict:
    axes = _axes(name, raw)
    start, end = _num(name, "od", raw.get("od")), _num(name, "do", raw.get("do"))
    low, high = _num(name, "z0", raw.get("z0")), _num(name, "z1", raw.get("z1"))
    base = _num(name, "z_dno", raw.get("z_dno", 0.0))
    if end <= start or high <= low or low < base:
        raise SpecError(f"{name}: hlediště chce od < do a z_dno <= z0 < z1")
    if min(axes) + start < 0:
        raise SpecError(f"{name}: odsazení {start} přechází přes střed elipsy {axes}")
    return {"osy": axes, "od": start, "do": end, "z0": low, "z1": high, "z_dno": base, "stupnu": _count(name, "stupnu", raw.get("stupnu"))}


def _dome(name: str, raw: dict) -> dict:
    radius = _num(name, "polomer", raw.get("polomer"), 0.1)
    thick = _pair(name, "tloustka", raw.get("tloustka"), 0.01)
    oculus = _num(name, "okulus", raw.get("okulus", 0.0), 0.0, radius * 0.9)
    out = {"polomer": radius, "tloustka": thick, "okulus": oculus, "z_patka": _num(name, "z_patka", raw.get("z_patka")),
           "vyska_ku_polomeru": _num(name, "vyska_ku_polomeru", raw.get("vyska_ku_polomeru", 1.0), 0.2, 3.0)}
    coffers = raw.get("kazety")
    if coffers:
        out["kazety"] = {"rad": _count(name, "kazety.rad", coffers.get("rad")), "v_rade": _count(name, "kazety.v_rade", coffers.get("v_rade"), 3),
                         "hloubka": _num(name, "kazety.hloubka", coffers.get("hloubka"), 0.01, thick[0] * 0.8),
                         "od_uhlu": _num(name, "kazety.od_uhlu", coffers.get("od_uhlu", 8.0), 0.0, 80.0)}
    return out


def _box(name: str, raw: dict) -> dict:
    low, high = _triple(name, "od", raw.get("od")), _triple(name, "do", raw.get("do"))
    if any(h <= l for l, h in zip(low, high)):
        raise SpecError(f"{name}: kvádr chce od < do ve všech osách")
    return {"od": low, "do": high, "azimut": _num(name, "azimut", raw.get("azimut", 0.0), -360, 360)}


def _disc(name: str, raw: dict) -> dict:
    axes = _pair(name, "osy", raw.get("osy"), 0.1)
    low, high = _num(name, "z0", raw.get("z0")), _num(name, "z1", raw.get("z1"))
    if high <= low:
        raise SpecError(f"{name}: disk chce z0 < z1")
    return {"osy": axes, "z0": low, "z1": high}


def _columns(name: str, raw: dict) -> dict:
    out = {"pocet": _count(name, "pocet", raw.get("pocet")), "z0": _num(name, "z0", raw.get("z0", 0.0)), "d": _num(name, "d", raw.get("d"), 0.05, 20),
           "drik": _num(name, "drik", raw.get("drik"), 0.1, 200), "rad": raw.get("rad", "hladky")}
    if out["rad"] not in ("hladky", "korintsky"):
        raise SpecError(f"{name}: rad je hladky nebo korintsky")
    if "od" in raw:
        out.update(od=_pair(name, "od", raw["od"]), to=_pair(name, "do", raw.get("do")))
    else:
        out.update(osy=_axes(name, raw), odsazeni=_num(name, "odsazeni", raw.get("odsazeni", 0.0)), faze=_num(name, "faze", raw.get("faze", 0.0), 0.0, 1.0), vyjma=_intervals(name, raw))
    return out


def _portico(name: str, raw: dict) -> dict:
    return {"x_sloupy": _num(name, "x_sloupy", raw.get("x_sloupy")), "x_zed": _num(name, "x_zed", raw.get("x_zed")),
            "sirka": _num(name, "sirka", raw.get("sirka"), 0.5), "pocet": _count(name, "pocet", raw.get("pocet"), 2),
            "d": _num(name, "d", raw.get("d"), 0.05, 20), "drik": _num(name, "drik", raw.get("drik"), 0.1, 200),
            "z0": _num(name, "z0", raw.get("z0", 0.0)), "stit": _num(name, "stit", raw.get("stit"), 0.1, 200),
            "schodu": _count(name, "schodu", raw.get("schodu", 1)), "azimut": _num(name, "azimut", raw.get("azimut", 0.0), -360, 360),
            "zadni_rady": [_num(name, "zadni_rady", v) for v in raw.get("zadni_rady", [])],
            "zadni_indexy": [_count(name, "zadni_indexy", v, 0) for v in raw.get("zadni_indexy", [])]}


def _arcade(name: str, raw: dict) -> dict:
    if raw.get("tvar", "oblouk") not in ("oblouk", "obdelnik"):
        raise SpecError(f"{name}: tvar je oblouk nebo obdelnik")
    return {"cil": raw.get("cil"), "osy": _axes(name, raw), "odsazeni": _pair(name, "odsazeni", raw.get("odsazeni")), "z0": _num(name, "z0", raw.get("z0", 0.0)),
            "vyska": _num(name, "vyska", raw.get("vyska"), 0.1, 200), "sirka": _num(name, "sirka", raw.get("sirka"), 0.05, 100), "pocet": _count(name, "pocet", raw.get("pocet")),
            "faze": _num(name, "faze", raw.get("faze", 0.0), 0.0, 1.0), "tvar": raw.get("tvar", "oblouk"), "vyjma": _intervals(name, raw)}


def _cut(name: str, raw: dict) -> dict:
    targets = raw.get("cile")
    if not isinstance(targets, list) or not targets:
        raise SpecError(f"{name}: řez potřebuje seznam cile")
    if "kvadr" in raw:
        return {"cile": targets, "kvadr": _box(name, raw["kvadr"])}
    span = _pair(name, "azimut", raw.get("azimut"), -720, 720)
    if span[1] <= span[0] or span[1] - span[0] >= 360:
        raise SpecError(f"{name}: azimut chce [od, do] menší než celý kruh")
    z_range = _pair(name, "z", raw.get("z"))
    if z_range[1] <= z_range[0]:
        raise SpecError(f"{name}: z chce [od, do]")
    return {"cile": targets, "azimut": span, "z": z_range}


BUILDERS = {"prstenec": _ring, "hlediste": _seating, "kopule": _dome, "kvadr": _box, "disk": _disc, "sloupy": _columns, "portik": _portico, "arkady": _arcade, "vyrez": _cut}


def validate(spec: dict) -> dict:
    """Zkontrolovaný popis s jen známými poli. Neznámý druh, chybějící číslo nebo odkaz na neexistující díl je SpecError."""
    if not isinstance(spec, dict):
        raise SpecError("popis není objekt")
    dim = spec.get("dim") or {}
    dims = {k: _num("dim", k, dim.get(k), 0.1) for k in ("length", "width", "height")}
    raw_parts = spec.get("dily")
    if not isinstance(raw_parts, list) or not raw_parts:
        raise SpecError("popis nemá žádné díly")
    if len(raw_parts) > MAX_PARTS:
        raise SpecError(f"popis má {len(raw_parts)} dílů, nejvýš {MAX_PARTS}")
    parts, solids = [], set()
    for i, raw in enumerate(raw_parts):
        if not isinstance(raw, dict):
            raise SpecError(f"díl {i + 1} není objekt")
        kind, name = raw.get("typ"), str(raw.get("nazev") or "")
        if kind not in KINDS:
            raise SpecError(f"díl {i + 1}: neznámý typ {kind!r}, jde použít {', '.join(KINDS)}")
        if not NAME.fullmatch(name):
            raise SpecError(f"díl {i + 1}: nazev {name!r} musí být malá písmena bez diakritiky, číslice a podtržítka")
        if any(p["nazev"] == name for p in parts):
            raise SpecError(f"{name}: název dílu se opakuje")
        part = {"typ": kind, "nazev": name, **BUILDERS[kind](name, raw)}
        if kind not in CUTS:
            material = raw.get("material", "kamen")
            if material not in MATERIALS:
                raise SpecError(f"{name}: material {material!r} není v {', '.join(MATERIALS)}")
            part["material"] = material
        if kind in SOLID:
            solids.add(name)
        targets = [part["cil"]] if kind == "arkady" else part.get("cile", [])
        for target in targets:
            if target not in solids:
                raise SpecError(f"{name}: řeže {target!r}, ale řezat jde jen plný díl uvedený dřív ({', '.join(sorted(solids)) or 'žádný'})")
        parts.append(part)
    return {"nazev": str(spec.get("nazev") or "model"), "dim": dims, "dily": parts, "kotvy": _anchors(spec.get("kotvy") or [], parts),
            "zdroje": spec.get("zdroje") or {}}


def _anchors(raw: list, parts: list[dict]) -> list[dict]:
    """Pojmenované body modelu, kam míří popisky (render je promítne do obrazu): `xyz` v metrech, `dil` = díl, se kterým se bod hýbe v rozkladu."""
    if not isinstance(raw, list) or len(raw) > MAX_PARTS:
        raise SpecError(f"kotvy musí být seznam nejvýš {MAX_PARTS} bodů")
    names = {p["nazev"] for p in parts if p["typ"] not in CUTS}
    out = []
    for item in raw:
        name = str(item.get("nazev") or "") if isinstance(item, dict) else ""
        if not NAME.fullmatch(name):
            raise SpecError(f"kotva {name!r}: nazev musí být malá písmena bez diakritiky, číslice a podtržítka")
        if name in names or any(a["nazev"] == name for a in out):
            raise SpecError(f"kotva {name}: název se opakuje")
        xyz = item.get("xyz")
        if not isinstance(xyz, (list, tuple)) or len(xyz) != 3:
            raise SpecError(f"kotva {name}: xyz musí být tři čísla")
        anchor = {"nazev": name, "xyz": [_num(f"kotva {name}", "xyz", v) for v in xyz]}
        if item.get("dil") is not None:
            if item["dil"] not in names:
                raise SpecError(f"kotva {name}: díl {item['dil']!r} v popisu není")
            anchor["dil"] = item["dil"]
        out.append(anchor)
    return out
