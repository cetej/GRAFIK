"""Popis stavby z dílů (JSON) a jeho kontrola. Staví `engine/blender/lod_parts.py`, žádný generovaný kód se nespouští.

Osy: x podél delší strany, y napříč, z nahoru, střed stavby v počátku, metry. Základ všeho kulatého je elipsa `osy` [a, b]
(poloosy) a poloha na ní se udává odsazením od obrysu: kružnice je a = b, nebo [0, 0] a odsazení je přímo poloměr.

Tvar vznikl zobecněním `scripts/3d/lod_pantheon.py` (rotunda, kupole s kazetami, portik, sloupy, zeď) a přidáním elipsy,
arkád a hlediště. Každé číslo patří do `dim` nebo do dílu, u ne-doložených rozměrů to řeší `zdroje`: co nemá fakt z dossieru, je `odhad`.
"""
from __future__ import annotations

import math
import re

MAX_PARTS = 240
MAX_COUNT = 400
MAX_METRES = 2000.0
SOLID = ("prstenec", "hlediste", "kopule", "kvadr", "disk", "rada", "pricky")
LOOSE = ("sloupy", "portik")
DECOR = ("sochy", "lide", "plachty", "zdvihadla")     # oživení obrazu: do rozměrů ani do kontroly kontaktu se nepočítá
CUTS = ("arkady", "vyrez", "ochoz", "schodiste", "sachty", "otvory", "dutina")
KINDS = SOLID + LOOSE + DECOR + CUTS
MATERIALS = ("travertin", "tuf", "cihla", "beton", "mramor", "zula", "bronz", "strecha", "pisek", "kamen", "drevo", "omitka", "platno", "zemina", "freska")
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


BUILDERS = {"sachty": _shafts, "ochoz": _vault, "schodiste": _stairs, "prstenec": _ring, "hlediste": _seating, "kopule": _dome, "kvadr": _box, "disk": _disc, "sloupy": _columns, "portik": _portico, "arkady": _arcade, "vyrez": _cut,
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
