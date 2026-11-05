"""Popis stavby z dílů (JSON) a jeho kontrola. Staví `engine/blender/lod_parts.py`, žádný generovaný kód se nespouští.

Osy: x podél delší strany, y napříč, z nahoru, střed stavby v počátku, metry. Základ všeho kulatého je elipsa `osy` [a, b]
(poloosy) a poloha na ní se udává odsazením od obrysu: kružnice je a = b, nebo [0, 0] a odsazení je přímo poloměr.

Tvar vznikl zobecněním `scripts/3d/lod_pantheon.py` (rotunda, kupole s kazetami, portik, sloupy, zeď) a přidáním elipsy,
arkád a hlediště. Každé číslo patří do `dim` nebo do dílu, u ne-doložených rozměrů to řeší `zdroje`: co nemá fakt z dossieru, je `odhad`.

Tvor (zobecnění `scripts/3d/lod_vorvan.py` a `vorvan_scena.py`, 3D infografika vorvaně 5. 11.): `telo` z profilu změřeného
na předlohách (`engine/silueta.py`), obecný loft `prurezy`, `elipsoid` (ploutve), `deska` (ocasní ploutev), `zuby`, `trubice`
(vnitřnosti jako jeden souvislý tvar) a `model` (postava v měřítku z knihovny 3D). Co je u vorvaně zvláštní, je v datech
popisu (`scripts/3d/dily/vorvan.py`), ne tady. Tělo se rozloží na průřezy už tady, Blender je jen spojí.
"""
from __future__ import annotations

import math
import re

MAX_PARTS = 240
MAX_COUNT = 400
MAX_METRES = 2000.0
ORGANIC = ("telo", "prurezy", "elipsoid", "deska", "zuby")
SOLID = ("prstenec", "hlediste", "kopule", "kvadr", "disk", "rada", "pricky") + ORGANIC
LOOSE = ("sloupy", "portik")
# oživení obrazu a co je uvnitř nebo vedle (vnitřnosti, postava v měřítku): do rozměrů ani do kontroly kontaktu se nepočítá
DECOR = ("sochy", "lide", "plachty", "zdvihadla", "trubice", "model")
CUTS = ("arkady", "vyrez", "ochoz", "schodiste", "sachty", "otvory", "dutina")
KINDS = SOLID + LOOSE + DECOR + CUTS
MATERIALS = ("travertin", "tuf", "cihla", "beton", "mramor", "zula", "bronz", "strecha", "pisek", "kamen", "drevo", "omitka", "platno", "zemina", "freska",
             "kuze", "kuze_tmava", "tkan", "sval", "sliznice", "strevo", "zub", "dutina")
MODEL_REF = re.compile(r"postava|[a-z0-9-]{1,80}/v\d{1,4}")    # vestavěná postava 1,72 m, nebo model z knihovny 3D
CUT_FACES = ("kamen", "cerna", "tmava")     # plocha řezu: z čeho je zeď, černá jako v architektonickém řezu, tmavý zásyp pod ní
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
    out = {"osy": axes, "od": start, "do": end, "z0": low, "z1": high, "z_dno": base, "stupnu": _count(name, "stupnu", raw.get("stupnu"))}
    if raw.get("tloustka") is not None:     # tenká deska pod stupni rovnoběžná s nimi, pod ní je prostor; bez ní plný klín až na z_dno
        out["tloustka"] = _num(name, "tloustka", raw["tloustka"], 0.05, 100)
    return out


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
    if out["rad"] not in ("hladky", "dorsky", "ionsky", "korintsky", "stozar"):
        raise SpecError(f"{name}: rad je hladky, dorsky, ionsky, korintsky nebo stozar")
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
    out = {"cil": raw.get("cil"), "osy": _axes(name, raw), "odsazeni": _pair(name, "odsazeni", raw.get("odsazeni")), "z0": _num(name, "z0", raw.get("z0", 0.0)),
           "vyska": _num(name, "vyska", raw.get("vyska"), 0.1, 200), "sirka": _num(name, "sirka", raw.get("sirka"), 0.05, 100), "pocet": _count(name, "pocet", raw.get("pocet")),
           "faze": _num(name, "faze", raw.get("faze", 0.0), 0.0, 1.0), "tvar": raw.get("tvar", "oblouk"), "vyjma": _intervals(name, raw)}
    if raw.get("ref") is not None:      # osa počítaná z obrysu s tímhle odsazením: oblouky v soustředných zdech pak leží v jedné přímce
        out["ref"] = _num(name, "ref", raw["ref"])
    return out


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


def _targets(name: str, raw: dict) -> list:
    targets = raw.get("cile")
    if not isinstance(targets, list) or not targets:
        raise SpecError(f"{name}: řez potřebuje seznam cile")
    return targets


def _span(name: str, raw: dict) -> tuple[float, float]:
    start, end = _num(name, "od", raw.get("od")), _num(name, "do", raw.get("do"))
    if end <= start:
        raise SpecError(f"{name}: od musí být menší než do")
    return start, end


def _vault(name: str, raw: dict) -> dict:
    """Chodba kolem celé stavby vyříznutá do plných dílů: v řezu je vidět klenba a podlaha patra."""
    if raw.get("tvar", "oblouk") not in ("oblouk", "obdelnik"):
        raise SpecError(f"{name}: tvar je oblouk nebo obdelnik")
    start, end = _span(name, raw)
    return {"cile": _targets(name, raw), "osy": _axes(name, raw), "od": start, "do": end, "z0": _num(name, "z0", raw.get("z0", 0.0)),
            "vyska": _num(name, "vyska", raw.get("vyska"), 0.1, 200), "tvar": raw.get("tvar", "oblouk")}


def _stairs(name: str, raw: dict) -> dict:
    """Radiální schodiště vyříznuté do plných dílů. faze 0 dá schodiště do roviny řezu, pak je vidět profil stupňů."""
    start, end = _span(name, raw)
    return {"cile": _targets(name, raw), "osy": _axes(name, raw), "od": start, "do": end, "z0": _num(name, "z0", raw.get("z0")), "z1": _num(name, "z1", raw.get("z1")),
            "sirka": _num(name, "sirka", raw.get("sirka"), 0.05, 100), "pruchod": _num(name, "pruchod", raw.get("pruchod", 2.5), 0.5, 50),
            "stupnu": _count(name, "stupnu", raw.get("stupnu", 12)), "pocet": _count(name, "pocet", raw.get("pocet")), "faze": _num(name, "faze", raw.get("faze", 0.0), 0.0, 1.0),
            "vyjma": _intervals(name, raw)}


def _shafts(name: str, raw: dict) -> dict:
    """Svislé otvory po elipse (výtahy, poklopy v podlaze arény): delka po normále, sirka po tečně."""
    z_range = _pair(name, "z", raw.get("z"))
    if z_range[1] <= z_range[0]:
        raise SpecError(f"{name}: z chce [od, do]")
    out = {"cile": _targets(name, raw), "osy": _axes(name, raw), "odsazeni": _num(name, "odsazeni", raw.get("odsazeni", 0.0)), "pocet": _count(name, "pocet", raw.get("pocet")),
           "sirka": _num(name, "sirka", raw.get("sirka"), 0.05, 100), "delka": _num(name, "delka", raw.get("delka"), 0.05, 100), "z": z_range,
           "faze": _num(name, "faze", raw.get("faze", 0.0), 0.0, 1.0), "vyjma": _intervals(name, raw)}
    if raw.get("ref") is not None:
        out["ref"] = _num(name, "ref", raw["ref"])
    return out


def _mirror(name: str, raw: dict) -> list:
    axes = raw.get("zrcadlo", [])
    if not isinstance(axes, list) or set(axes) - {"x", "y"}:
        raise SpecError(f"{name}: zrcadlo je seznam os x a y")
    return axes


def _points(name: str, raw: dict) -> list[list[float]]:
    profile = raw.get("profil")
    if not isinstance(profile, list) or not 3 <= len(profile) <= 200:
        raise SpecError(f"{name}: profil musí být 3 až 200 bodů [odsazení, z]")
    return [_pair(name, "profil", p) for p in profile]


def _row(name: str, raw: dict) -> dict:
    """Řada stejných kvádrů s krokem: příčky cel, trámy, pilíře. `zrcadlo` ji zopakuje přes osu x, y nebo obě."""
    box = _box(name, raw)
    return {"od": box["od"], "do": box["do"], "krok": _triple(name, "krok", raw.get("krok", [0, 0, 0])), "pocet": _count(name, "pocet", raw.get("pocet", 1)), "zrcadlo": _mirror(name, raw)}


def _walls(name: str, raw: dict) -> dict:
    """Profil [odsazení, z] vytažený na tloušťku, po přímkách kolmých k obrysu `osy`: radiální stěny, schodiště, omítka na stěně (`posun` po tečně)."""
    axes = _pair(name, "osy", raw.get("osy"), 0.1)
    return {"osy": axes, "profil": _points(name, raw), "pocet": _count(name, "pocet", raw.get("pocet")), "tloustka": _num(name, "tloustka", raw.get("tloustka"), 0.01, 100),
            "faze": _num(name, "faze", raw.get("faze", 0.0), 0.0, 1.0), "posun": _num(name, "posun", raw.get("posun", 0.0), -100, 100), "vyjma": _intervals(name, raw)}


def _openings(name: str, raw: dict) -> dict:
    """Řada otvorů skrz rovné zdi; `stred` = [x, y, z dole], `smer` = kudy otvor vede, x nebo y."""
    if raw.get("smer") not in ("x", "y"):
        raise SpecError(f"{name}: smer je x nebo y")
    if raw.get("tvar", "oblouk") not in ("oblouk", "obdelnik"):
        raise SpecError(f"{name}: tvar je oblouk nebo obdelnik")
    return {"cile": _targets(name, raw), "stred": _triple(name, "stred", raw.get("stred")), "krok": _pair(name, "krok", raw.get("krok", [0, 0])), "pocet": _count(name, "pocet", raw.get("pocet", 1)),
            "smer": raw["smer"], "sirka": _num(name, "sirka", raw.get("sirka"), 0.05, 100), "vyska": _num(name, "vyska", raw.get("vyska"), 0.1, 200),
            "hloubka": _num(name, "hloubka", raw.get("hloubka"), 0.05, MAX_METRES), "tvar": raw.get("tvar", "oblouk"), "zrcadlo": _mirror(name, raw)}


def _cavity(name: str, raw: dict) -> dict:
    """Prostor s vlastním profilem [odsazení, z] kolem celé stavby, třeba to, co obepíná arénu."""
    axes = _axes(name, raw)
    points = _points(name, raw)
    if min(axes) + min(p[0] for p in points) < 0:
        raise SpecError(f"{name}: odsazení {min(p[0] for p in points)} přechází přes střed elipsy {axes}")
    return {"cile": _targets(name, raw), "osy": axes, "profil": points}


def _sectors(name: str, raw: dict) -> list[list[float]]:
    given = raw.get("azimut", [0, 360])
    spans = [given] if given and isinstance(given[0], (int, float)) else given
    out = [_pair(name, "azimut", s, -720, 720) for s in spans]
    if not out or any(b <= a for a, b in out):
        raise SpecError(f"{name}: azimut chce [od, do] nebo seznam takových dvojic")
    return out


def _statues(name: str, raw: dict) -> dict:
    """Sochy na podstavci po elipse; `aedikula` je dá do rámu s červeným pozadím na zdi, `preskoc` n vynechá každou n-tou (dveře)."""
    return {"osy": _pair(name, "osy", raw.get("osy"), 0.1), "odsazeni": _num(name, "odsazeni", raw.get("odsazeni", 0.0)), "pocet": _count(name, "pocet", raw.get("pocet")),
            "faze": _num(name, "faze", raw.get("faze", 0.0), 0.0, 1.0), "z0": _num(name, "z0", raw.get("z0")), "vyska": _num(name, "vyska", raw.get("vyska"), 0.2, 30),
            "preskoc": _count(name, "preskoc", raw.get("preskoc", 0), 0), "aedikula": bool(raw.get("aedikula")), "vyjma": _intervals(name, raw)}


def _people(name: str, raw: dict) -> dict:
    """Lidé rozsetí mezi odsazeními od a do; výška země jde lineárně z0 až z1 (hlediště). Rozsev určuje název dílu, obraz se opakuje."""
    axes = _axes(name, raw)
    start, end = _span(name, raw)
    if min(axes) + start < 0:
        raise SpecError(f"{name}: odsazení {start} přechází přes střed elipsy {axes}")
    low = _num(name, "z0", raw.get("z0"))
    return {"osy": axes, "od": start, "do": end, "z0": low, "z1": _num(name, "z1", raw.get("z1", low)), "pocet": _count(name, "pocet", raw.get("pocet")),
            "azimut": _sectors(name, raw), "vyska": _num(name, "vyska", raw.get("vyska", 1.7), 0.3, 5)}


def _sails(name: str, raw: dict) -> dict:
    """Plachty mezi obrysem a vnitřním okrajem v jednom výseku, s lany: odsazení od je dovnitř (z_dov), do je nad zdí (z_ven)."""
    span = _pair(name, "azimut", raw.get("azimut"), -720, 720)
    if span[1] <= span[0] or span[1] - span[0] >= 360:
        raise SpecError(f"{name}: azimut chce [od, do] menší než celý kruh")
    start, end = _span(name, raw)
    out = {"osy": _pair(name, "osy", raw.get("osy"), 0.1), "od": start, "do": end, "z_dov": _num(name, "z_dov", raw.get("z_dov")), "z_ven": _num(name, "z_ven", raw.get("z_ven")),
           "azimut": span, "pocet": _count(name, "pocet", raw.get("pocet")), "prohyb": _num(name, "prohyb", raw.get("prohyb", 1.0), 0.0, 50)}
    if raw.get("lana") is not None:     # holá lana bez plátna dál do stran, výsek plachet musí ležet uvnitř
        ropes = _pair(name, "lana", raw["lana"], -720, 720)
        if not ropes[0] <= span[0] or not span[1] <= ropes[1] or ropes[1] - ropes[0] >= 360:
            raise SpecError(f"{name}: lana chtějí [od, do] kolem výseku plachet, menší než celý kruh")
        out["lana"] = ropes
    return out


def _lifts(name: str, raw: dict) -> dict:
    """Dřevěné výtahy v řadě: rám od z0 do z1 a klec s lanem někde na cestě nahoru."""
    start, end = _num(name, "z0", raw.get("z0")), _num(name, "z1", raw.get("z1"))
    if end <= start:
        raise SpecError(f"{name}: výtah chce z0 < z1")
    return {"stred": _pair(name, "stred", raw.get("stred")), "krok": _pair(name, "krok", raw.get("krok", [0, 0])), "pocet": _count(name, "pocet", raw.get("pocet", 1)), "zrcadlo": _mirror(name, raw),
            "z0": start, "z1": end, "sirka": _num(name, "sirka", raw.get("sirka"), 0.1, 50), "delka": _num(name, "delka", raw.get("delka"), 0.1, 50)}


def _smooth(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def table_at(table: list[list[float]], x: float) -> float:
    """Hodnota tabulky [[x, hodnota], ...] v bodě x; mezi body plynule (smoothstep), mimo ni krajní hodnota."""
    if x <= table[0][0]:
        return table[0][1]
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * _smooth((x - x0) / (x1 - x0)) if x1 > x0 else y1
    return table[-1][1]


def _linear(xs: list[float], ys: list[float], x: float) -> float:
    if x <= xs[0]:
        return ys[0]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            return ys[i - 1] + (ys[i] - ys[i - 1]) * (x - xs[i - 1]) / (xs[i] - xs[i - 1])
    return ys[-1]


def _table(name: str, raw: dict, key: str, default: float, lo: float, hi: float) -> list[list[float]]:
    rows = raw.get(key, [[0.0, default], [1.0, default]])
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise SpecError(f"{name}: {key} je tabulka [[x, hodnota], ...]")
    out = [[_num(name, key, r[0], 0.0, 1.0), _num(name, key, r[1], lo, hi)] for r in (_pair(name, key, row) for row in rows)]
    if any(b[0] < a[0] for a, b in zip(out, out[1:])):
        raise SpecError(f"{name}: {key} musí mít x vzestupně")
    return out


def _turn(name: str, raw: dict) -> dict | None:
    """Otočení hotového dílu kolem osy procházející bodem `stred`, třeba otevřená čelist kolem kloubu."""
    turn = raw.get("otoceni")
    if turn is None:
        return None
    if not isinstance(turn, dict) or turn.get("osa") not in ("x", "y", "z"):
        raise SpecError(f"{name}: otoceni je {{stred, osa x/y/z, uhel}}")
    return {"stred": _triple(name, "otoceni.stred", turn.get("stred")), "osa": turn["osa"], "uhel": _num(name, "otoceni.uhel", turn.get("uhel"), -360, 360)}


def _section_rows(name: str, rows) -> list[list[float]]:
    if not isinstance(rows, list) or not 2 <= len(rows) <= 400:
        raise SpecError(f"{name}: rezy jsou 2 až 400 průřezů [x, polosirka, z_stred, polovyska, n, zuzeni_dole]")
    out = []
    for r in rows:
        if not isinstance(r, (list, tuple)) or not 4 <= len(r) <= 6:
            raise SpecError(f"{name}: průřez {r!r} chce [x, polosirka, z_stred, polovyska] a volitelně n a zuzeni_dole")
        x, hw, zc, hh = (_num(name, "rezy", v) for v in r[:4])
        if hw <= 0 or hh <= 0:
            raise SpecError(f"{name}: průřez v x {x} má nulovou šířku nebo výšku")
        n = _num(name, "rezy n", r[4], 0.5, 10) if len(r) > 4 else 2.0
        taper = _num(name, "rezy zuzeni_dole", r[5], 0.0, 0.95) if len(r) > 5 else 0.0
        out.append([x, hw, zc, hh, n, taper, 0.0])
    return out


def _lofted(name: str, raw: dict) -> dict:
    """Obecný loft: průřezy po ose x, každý superelipsa (n = 2 elipsa, víc = hranatější), dole zúžená o `zuzeni_dole`."""
    out = {"rezy": _section_rows(name, raw.get("rezy")), "hladit": bool(raw.get("hladit", True))}
    if (turn := _turn(name, raw)) is not None:
        out["otoceni"] = turn
    return out


DENSE_FRONT = [0.0, 0.002, 0.005, 0.009, 0.014, 0.02, 0.028, 0.038, 0.05, 0.065]   # zaoblené čelo potřebuje husté průřezy


def body_sections(p: dict) -> list[list[float]]:
    """Tělo z profilu na průřezy [x, polosirka, z_stred, polovyska, n, zuzeni_dole, hreben] v metrech.
    Profil je v podílech délky od špičky (x = 0) k konci, hřbet a břicho nad nejnižším bodem břicha, šířka celá."""
    length, prof = p["delka"], p["profil"]
    xs = prof["x"]
    ridge = prof.get("hreben") or [0.0] * len(xs)
    out = []
    for x in p["vzorky"]:
        k_dome, x_s = 1.0, x
        if x < p["celo"]:                       # čelo vyklenuté jako polovina elipsoidu, ne deska
            k_dome, x_s = max(math.sqrt(1 - ((p["celo"] - x) / p["celo"]) ** 2), 0.02), p["celo"]
        top, bot = _linear(xs, prof["hrbet"], x_s) * length, _linear(xs, prof["bricho"], x_s) * length
        zc = (top + bot) / 2 + 0.12 * (1 - k_dome) * (top - bot)      # špička klenby nad středem: spodek hlavy ustupuje
        hh = max((top - bot) / 2 * k_dome, 0.005) * table_at(p["zplosteni"], x_s)
        hw = max(_linear(xs, prof["sirka"], x_s) * length / 2 * k_dome, 0.005)
        out.append([round(p["x0"] + x * length, 4), round(hw, 4), round(p["z0"] + zc, 4), round(hh, 4),
                    round(table_at(p["hranatost"], x_s), 3), round(table_at(p["zuzeni_dole"], x_s), 3), round(_linear(xs, ridge, x_s) * length, 4)])
    return out


def _body(name: str, raw: dict) -> dict:
    """Tělo tvora z profilu (engine/silueta.py): hřbet, břicho a šířka po délce, `hreben` jen ve střední čáře hřbetu."""
    length = _num(name, "delka", raw.get("delka"), 0.01, MAX_METRES)
    prof = raw.get("profil")
    if not isinstance(prof, dict):
        raise SpecError(f"{name}: profil je {{x, hrbet, bricho, sirka}} v podílech délky")
    xs = prof.get("x")
    if not isinstance(xs, list) or not 3 <= len(xs) <= 1001:
        raise SpecError(f"{name}: profil.x jsou 3 až 1001 podílů délky")
    clean = {"x": [_num(name, "profil.x", v, 0.0, 1.0) for v in xs]}
    if any(b <= a for a, b in zip(clean["x"], clean["x"][1:])):
        raise SpecError(f"{name}: profil.x musí růst")
    for key in ("hrbet", "bricho", "sirka", "hreben"):
        values = prof.get(key)
        if values is None and key == "hreben":
            continue
        if not isinstance(values, list) or len(values) != len(xs):
            raise SpecError(f"{name}: profil.{key} musí mít stejně hodnot jako profil.x")
        clean[key] = [_num(name, f"profil.{key}", v, -1.0, 1.0) for v in values]
    end = _num(name, "konec", raw.get("konec", 1.0), 0.5, 1.0)
    samples = raw.get("vzorky") or [x for x in DENSE_FRONT if x < end] + [round(0.08 + 0.015 * i, 4) for i in range(int((end - 0.08) / 0.015) + 1)]
    part = {"delka": length, "x0": _num(name, "x0", raw.get("x0", -length / 2)), "z0": _num(name, "z0", raw.get("z0", 0.0)), "profil": clean,
            "celo": _num(name, "celo", raw.get("celo", 0.0), 0.0, 0.4), "vzorky": [_num(name, "vzorky", v, 0.0, 1.0) for v in samples],
            "hranatost": _table(name, raw, "hranatost", 2.0, 0.5, 10), "zuzeni_dole": _table(name, raw, "zuzeni_dole", 0.0, 0.0, 0.95),
            "zplosteni": _table(name, raw, "zplosteni", 1.0, 0.01, 2.0)}
    part["rezy"] = body_sections(part)
    part["hladit"] = True
    return part


def _ellipsoid(name: str, raw: dict) -> dict:
    out = {"stred": _triple(name, "stred", raw.get("stred")), "poloosy": [_num(name, "poloosy", v, 0.001, MAX_METRES) for v in _triple(name, "poloosy", raw.get("poloosy"))],
           "natoceni": _triple(name, "natoceni", raw.get("natoceni", [0, 0, 0])), "zrcadlo": _mirror(name, raw)}
    if (turn := _turn(name, raw)) is not None:
        out["otoceni"] = turn
    return out


def _plate(name: str, raw: dict) -> dict:
    """Plochý díl z obrysu shora [[x, y], ...] s tloušťkou, skloněný kolem osy y v `osa_x` (ocasní ploutev při záběru)."""
    outline = raw.get("obrys")
    if not isinstance(outline, list) or not 3 <= len(outline) <= 200:
        raise SpecError(f"{name}: obrys je 3 až 200 bodů [x, y]")
    pts = [_pair(name, "obrys", p) for p in outline]
    if raw.get("zrcadlit_y"):       # zadaná je jen strana y >= 0 od kořene ke špičce, druhá se dopočítá
        pts = pts + [[x, -y] for x, y in reversed(pts[1:-1])]
    return {"obrys": pts, "z": _num(name, "z", raw.get("z", 0.0)), "tloustka": _num(name, "tloustka", raw.get("tloustka"), 0.001, 100),
            "osa_x": _num(name, "osa_x", raw.get("osa_x", pts[0][0])), "sklon": _num(name, "sklon", raw.get("sklon", 0.0), -90, 90)}


def _teeth(name: str, raw: dict) -> dict:
    points = raw.get("body")
    if not isinstance(points, list) or not 1 <= len(points) <= MAX_COUNT:
        raise SpecError(f"{name}: body jsou 1 až {MAX_COUNT} bodů [x, y, z] (pata zubu)")
    out = {"body": [_triple(name, "body", p) for p in points], "vyska": _num(name, "vyska", raw.get("vyska"), 0.001, 10),
           "polomer": _num(name, "polomer", raw.get("polomer"), 0.001, 5), "spicka": _num(name, "spicka", raw.get("spicka", 0.0), 0.0, 5), "zrcadlo": _mirror(name, raw)}
    if (turn := _turn(name, raw)) is not None:
        out["otoceni"] = turn
    return out


def _tube(name: str, raw: dict) -> dict:
    """Trubice s proměnným poloměrem po hladké křivce bodů [x, y, z, r]; `useky` určí tkáň po klíčových bodech, `klubko` na konci smotá střevo."""
    points = raw.get("body")
    if not isinstance(points, list) or not 2 <= len(points) <= 200:
        raise SpecError(f"{name}: body jsou 2 až 200 bodů [x, y, z, polomer]")
    keys = []
    for p in points:
        if not isinstance(p, (list, tuple)) or len(p) != 4:
            raise SpecError(f"{name}: bod {p!r} chce [x, y, z, polomer]")
        keys.append([_num(name, "body", v) for v in p[:3]] + [_num(name, "body polomer", p[3], 0.001, 50)])
    sections = []
    for item in raw.get("useky", []):
        if not isinstance(item, (list, tuple)) or len(item) != 2 or item[1] not in MATERIALS:
            raise SpecError(f"{name}: useky jsou [do_bodu, material] s materiálem z {', '.join(MATERIALS)}")
        sections.append([_num(name, "useky", item[0], 0, len(keys)), item[1]])
    out = {"body": keys, "useky": sections, "stlaceni_y": _num(name, "stlaceni_y", raw.get("stlaceni_y", 1.0), 0.1, 1.0),
           "stlaceni_od": _num(name, "stlaceni_od", raw.get("stlaceni_od", 0.0), 0.0, 50)}
    coil = raw.get("klubko")
    if coil is not None:
        if not isinstance(coil, dict):
            raise SpecError(f"{name}: klubko je {{stred, rozmer, smycek, polomer}}")
        out["klubko"] = {"stred": _triple(name, "klubko.stred", coil.get("stred")), "rozmer": _triple(name, "klubko.rozmer", coil.get("rozmer")),
                         "smycek": _num(name, "klubko.smycek", coil.get("smycek", 12), 1, 60), "polomer": _num(name, "klubko.polomer", coil.get("polomer"), 0.001, 10),
                         "bodu": int(_num(name, "klubko.bodu", coil.get("bodu", 400), 20, 2000))}
    return out


def _model(name: str, raw: dict) -> dict:
    """Hotový model vedle stavby nebo tvora: postava v měřítku. Nejdelší rozměr = `delka`, natočení ve stupních kolem x, y, z."""
    ref = str(raw.get("model") or "")
    if not MODEL_REF.fullmatch(ref):
        raise SpecError(f"{name}: model je 'postava' nebo '<id>/v<n>' z knihovny 3D ({ref!r})")
    return {"model": ref, "delka": _num(name, "delka", raw.get("delka"), 0.01, MAX_METRES), "stred": _triple(name, "stred", raw.get("stred")),
            "natoceni": _triple(name, "natoceni", raw.get("natoceni", [0, 0, 0]))}


BUILDERS = {"telo": _body, "prurezy": _lofted, "elipsoid": _ellipsoid, "deska": _plate, "zuby": _teeth, "trubice": _tube, "model": _model,
            "sachty": _shafts, "ochoz": _vault, "schodiste": _stairs, "prstenec": _ring, "hlediste": _seating, "kopule": _dome, "kvadr": _box, "disk": _disc, "sloupy": _columns, "portik": _portico, "arkady": _arcade, "vyrez": _cut,
            "rada": _row, "pricky": _walls, "otvory": _openings, "dutina": _cavity, "sochy": _statues, "lide": _people, "plachty": _sails, "zdvihadla": _lifts}


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
        if kind in CUTS and raw.get("povrch") is not None:      # vnitřek vyříznutého prostoru, třeba omítka schodiště
            if raw["povrch"] not in MATERIALS:
                raise SpecError(f"{name}: povrch {raw['povrch']!r} není v {', '.join(MATERIALS)}")
            part["povrch"] = raw["povrch"]
        if kind not in CUTS:
            material = raw.get("material", "kamen")
            if material not in MATERIALS:
                raise SpecError(f"{name}: material {material!r} není v {', '.join(MATERIALS)}")
            part["material"] = material
        if raw.get("okoli") and kind in SOLID + LOOSE:      # terén, terasa a sloupky kolem stavby, rozměry stavby se bez nich počítají
            part["okoli"] = True
        if kind in SOLID:
            solids.add(name)
            if raw.get("rez") is not None:      # vlastní plocha řezu dílu
                if raw["rez"] not in CUT_FACES:
                    raise SpecError(f"{name}: rez je {', '.join(CUT_FACES)}")
                part["rez"] = raw["rez"]
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
