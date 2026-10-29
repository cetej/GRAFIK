"""Pravidla National Geographic pro vrstvu popisků.

Zdroj: Resource Guide „04 Maps 2022.pdf“ — typografie str. 15–20 (tisk i web),
maskování textu str. 12–14, umisťování názvů str. 21–22. Velikosti jsou z webové
specifikace (str. 19–20) v px při šířce zobrazení `display_width` (výchozí 800 px,
sloupec článku) a přepočítávají se na rozměr podkladu.

Druh prvku (`kind`) určuje písmo, verzálky, prostrkání, barvu a to, kde má
prvek ležet (`expect`: voda / pevnina). Barvu volí `pick_text_color` podle
pozadí: první kandidát, který dá dost kontrastu; když žádný, rozhoduje halo.

Kopie z NG-ROBOT `ng_vector_labels/style.py`, commit f27580e9534a408e35b153d06376e4d34697b092
(2026-10-29, GRAFIK fáze 3). Opravy z NG-ROBOT přenášej diffem originálu od tohoto commitu:
`git -C NG-ROBOT diff f27580e9 -- ng_vector_labels/style.py`.
Změny proti originálu: žádné.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

GEO = "Geograph Edit"
NEO = "NatGeo NeoGothic"
CAP = "NatGeo Caption"
BUM = "NatGeo Bumstead"

# Barvy z webové specifikace NG (str. 20)
WATER_TEXT = "#93BFDD"        # Text – Water 147/191/221
WATER_TEXT_DARK = "#2F5F86"   # tmavší odstín pro vodu na světlém podkladu (led, mělčina)
GREEN_TEXT = "#636D38"        # Text – Physical green 99/109/56
TAN_TEXT = "#8C785A"          # Text – Physical tan 140/120/90
WHITE = "#FFFFFF"
INK = "#1A1A1A"
ACCENT = "#C9A227"            # zlatá NG pro trasy a zvýraznění

DEFAULT_DISPLAY_WIDTH = 800
# Písma, jejichž číslice 1 vypadá jako I (ověřeno renderem 2026-10-08) — číslice
# se v nich sází Geographem.
DIGIT_UNSAFE_FONTS = {NEO, BUM}


@dataclass(frozen=True)
class FeatureStyle:
    font: tuple            # (rodina, řez)
    size: float            # px při display_width
    caps: bool = False
    tracking: int = 0      # 1/1000 em
    colors: tuple = (WHITE, INK)   # kandidáti barvy textu, první vhodný vyhrává
    expect: Optional[str] = None   # "water" | "land" | None
    note: str = ""


# Velikosti = varianta „B vyrovnaná“, kterou operátor vybral 2026-10-09 ze tří náhledů
# Vikingů ve skutečné velikosti čtení: titulek zůstává hlavní, popisky jdou přečíst
# bez zvětšení (dřív titulek 28 proti osadám 12 px). Zbylé druhy zvětšeny ve stejném poměru.
FEATURES: dict[str, FeatureStyle] = {
    # Voda — Caption (tisk CAPTION BOLD CAPS), barva textu vody
    "ocean": FeatureStyle((CAP, "Heavy"), 18, caps=True, tracking=300,
                          colors=(WATER_TEXT, WATER_TEXT_DARK), expect="water", note="Ocean — CAPTION BOLD CAPS"),
    "sea": FeatureStyle((CAP, "Heavy"), 17, tracking=100, colors=(WATER_TEXT, WATER_TEXT_DARK), expect="water"),
    "water": FeatureStyle((CAP, "Heavy"), 14, colors=(WATER_TEXT, WATER_TEXT_DARK), expect="water",
                          note="řeka, jezero, záliv, průliv, fjord"),
    # Řeka leží na pevnině: tmavší vodní modrá napřed, světlá na reliéfu nemá kontrast (operátor 2026-10-20)
    "river": FeatureStyle((CAP, "Heavy"), 14, colors=(WATER_TEXT_DARK, WATER_TEXT), note="po křivce toku"),
    "glacier": FeatureStyle((CAP, "Heavy"), 16, colors=(WATER_TEXT_DARK, WATER_TEXT), expect="land",
                            note="ledovec je ve specifikaci vodní prvek (Caption bold)"),
    # Kultura — NeoGothic
    "country": FeatureStyle((NEO, "Heavy"), 17, caps=True, tracking=150, colors=(WHITE, INK), expect="land"),
    "region": FeatureStyle((NEO, "Regular"), 16, caps=True, tracking=120, colors=(WHITE, INK),
                           note="stát, provincie, historická oblast"),
    "town": FeatureStyle((NEO, "Regular"), 15, colors=(WHITE, INK)),
    "capital": FeatureStyle((NEO, "Heavy"), 16, colors=(WHITE, INK)),
    "site": FeatureStyle((NEO, "Regular"), 15, colors=(WHITE, INK), note="zajímavé místo, zřícenina"),
    # Fyzická geografie — Bumstead
    "continent": FeatureStyle((BUM, "Heavy"), 18, caps=True, tracking=250, colors=(WHITE, INK)),
    "physical": FeatureStyle((BUM, "Regular"), 15, caps=True, tracking=200, colors=(WHITE, INK),
                             note="pohoří, náhorní plošina, poušť, ostrovy"),
    "peak": FeatureStyle((BUM, "Regular"), 13, colors=(WHITE, INK)),
    "physical_small": FeatureStyle((BUM, "Regular"), 13, colors=(WHITE, INK), note="mys, malý ostrov, průsmyk"),
    "park": FeatureStyle((BUM, "Heavy"), 15, caps=True, tracking=100, colors=(WHITE, INK)),
    # Prvky mapy a redakční texty — Geograph Edit
    "title": FeatureStyle((GEO, "Black"), 26, colors=(WHITE, INK)),
    "subtitle": FeatureStyle((GEO, "Medium"), 15, colors=(WHITE, INK)),
    "annotation": FeatureStyle((GEO, "Regular Italic"), 13, colors=(WHITE, INK), note="poznámka u prvku"),
    "note": FeatureStyle((NEO, "Regular"), 13, colors=(WHITE, INK), note="směrová poznámka se šipkou"),
    "legend_title": FeatureStyle((GEO, "Medium"), 15, colors=(WHITE, INK)),
    "legend_entry": FeatureStyle((GEO, "Regular"), 14, colors=(WHITE, INK)),
    "scale": FeatureStyle((GEO, "Regular"), 12, colors=(WHITE, INK), note="nikdy větší než názvy na mapě"),
    "north": FeatureStyle((NEO, "Regular"), 13, colors=(WHITE, INK)),
    "marker_number": FeatureStyle((GEO, "Bold"), 11, colors=(WHITE,)),
    "credit": FeatureStyle((GEO, "Regular"), 10, caps=True, tracking=50, colors=(WHITE, INK)),
}

LABEL_KINDS = sorted(k for k in FEATURES if k not in ("marker_number",))

# Délky v px při display_width (str. 20: town spot 6 px, leader 1.5 pt, měřítko 1.5 pt)
TOWN_SPOT = 6.0
AIRPORT_SPOT = 16.0         # značka letiště (silueta letadla), operátor 2026-10-13
CAPITAL_STAR = 12.0         # hlavní město = černá hvězdička (průměr), operátor 2026-10-13
SCALE_MAX_FRAC = 0.12       # měřítko nejvýš 12 % šířky (18 % bylo „moc dlouhé“, operátor 2026-10-13)
MARKER_DIAMETER = 17.0
LEADER_WIDTH = 1.5          # str. 20: leader line 1.5 pt
ROUTE_WIDTH = 1.6           # tenká čárkovaná trasa (výběr operátora 2026-10-09)
SCALE_LINE = 1.5
# Měřítko: čára 1,5 pt s dílky jen na koncích, šedá, ne černá — nesvítí proti názvům (operátor 2026-10-20)
SCALE_TICK = 4.0
SCALE_INK, SCALE_INK_ON_DARK = "#8A8680", "#D8D6D2"   # úsečka střední šedá; #666360 působilo černě (operátor 2026-10-20)
SCALE_TEXT, SCALE_TEXT_ON_DARK = "#4E4B47", "#EEEDEA"  # čísla tmavší než úsečka, jinak zanikají (operátor 2026-10-20)
PEAK_CROSS = 7.0            # vrchol = rovný křížek „+“ (rameno přes celou šířku, px), operátor 2026-10-20
PEAK_CROSS_LINE = 1.4
SAFE_MARGIN = 0.04          # bezpečný okraj (podíl kratší strany), stejný jako starý composer
LEADING = 1.0               # řádkování víceřádkových popisků jako podíl velikosti (NG „7.5 on 7.5“)
PEAK_ELEV_SCALE = 0.8        # kóta vrcholu o stupeň menší než jeho název
PEAK_LEADING = 0.9           # název a kóta těsně pod sebou (kóta je menší, plné řádkování dělalo mezeru)
HALO_WEIGHT = 0.16          # tloušťka halo tahu jako podíl velikosti písma (NG 1–2 pt při 7–10 pt)


def scale_factor(canvas_width: float, display_width: float = DEFAULT_DISPLAY_WIDTH) -> float:
    """Kolik bodů podkladu odpovídá 1 px na obrazovce čtenáře."""
    return canvas_width / float(display_width or DEFAULT_DISPLAY_WIDTH)


def feature(kind: str) -> FeatureStyle:
    return FEATURES.get(kind) or FEATURES["site"]


def _lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_rgb(color: str) -> tuple:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def rgb_to_hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, int(round(v)))) for v in rgb[:3]))


def luminance(rgb) -> float:
    r, g, b = rgb[:3]
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a, b) -> float:
    """Kontrastní poměr WCAG mezi dvěma barvami (RGB 0–255 nebo #hex)."""
    a = hex_to_rgb(a) if isinstance(a, str) else a
    b = hex_to_rgb(b) if isinstance(b, str) else b
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# Popisky NG jsou velké (≥ 11 px na obrazovce, většinou tučné) — WCAG pro velký text 3:1.
MIN_CONTRAST = 3.0


def pick_text_color(kind: str, bg_rgb, override: Optional[str] = None) -> str:
    """Barva textu: zadaná, jinak první kandidát druhu s kontrastem ≥ 3:1, jinak nejlepší z nich."""
    if override:
        return override
    cands = feature(kind).colors
    for c in cands:
        if contrast(c, bg_rgb) >= MIN_CONTRAST:
            return c
    return max(cands + (WHITE, INK), key=lambda c: contrast(c, bg_rgb))


HALO_MODES = ("auto", "none", "soft", "solid")
WATER_KINDS = ("ocean", "sea", "water", "glacier")   # popisky na vodní ploše bez hala (jen na přání editora)
# Název řeky leží na pevnině → vždy aspoň jemné zesvětlení podkladu pod textem (operátor 2026-10-20:
# „Chybí zesvětlení pod názvy řek“); šedé halo pod modrým textem na vodě (2026-10-13) se to netýká.
LAND_WATER_KINDS = ("river",)
HALO_CALM_STD = 12.0        # směrodatná odchylka jasu pozadí (0–255), pod kterou je pozadí „klidné“


def halo_mode(text_color: str, bg_rgb, bg_std: float, override: Optional[str] = None) -> str:
    """Kolik hala popisek potřebuje — změřeno, ne odhadnuto (operátor 2026-10-13).

    NG halo slouží čitelnosti, není povinné; častěji je to jemné zesvětlení
    podkladu (Resource Guide 04 Maps str. 12–14: Gaussian blur halo) než
    obrys. Pravidlo: kontrast ≥ 4,5 : 1 na klidném pozadí → žádné; kontrast
    ≥ 3 : 1 nebo členité pozadí → jemné (rozostřené); jinak plné (tenký tah
    v zesvětlené barvě pozadí). `override` = volba editora pro mapu či popisek.
    """
    if override in ("none", "soft", "solid"):
        return override
    con = contrast(text_color, tuple(bg_rgb[:3]))
    if con >= 4.5 and bg_std < HALO_CALM_STD:
        return "none"
    if con >= MIN_CONTRAST:
        return "soft"
    return "solid"


def halo_color(text_color: str, bg_rgb) -> str:
    """Halo v barvě pozadí (NG „type halo“), posunuté od textu, aby ho oddělilo.

    Světlý text dostane tmavší halo než pozadí, tmavý světlejší — čistá barva pozadí
    by na pestrém podkladu (krajina) text neoddělila.
    """
    bg = tuple(bg_rgb[:3])
    # Posun se zvětšuje, dokud halo nemá s textem kontrast MIN_CONTRAST (tmavý svah pod
    # modrou řekou: zesvětlení o 60 % dalo jen 2,8 : 1); začíná se co nejblíž pozadí.
    if luminance(hex_to_rgb(text_color)) > luminance(bg):
        steps = [rgb_to_hex(tuple(v * k for v in bg)) for k in (0.45, 0.3, 0.15, 0.0)]
    else:
        steps = [rgb_to_hex(tuple(v + (255 - v) * k for v in bg)) for k in (0.6, 0.75, 0.9, 1.0)]
    return next((c for c in steps if contrast(text_color, c) >= MIN_CONTRAST), steps[-1])


# Geograph má při stejné velikosti větší oko než NeoGothic/Caption v názvech, proto rezerva
SCALE_TO_LABEL = 0.85


def scale_text_size(labels: list) -> float:
    """Velikost čísel měřítka (px při display_width): nikdy větší než nejmenší název na mapě.

    Operátor 2026-10-20: „písmo měřítka nemůže být větší než velikost písma v názvech na mapě“.
    NG Resource Guide: čísla měřítka 5 pt proti 7–8 pt u sídel.
    """
    sizes = []
    for lab in labels or []:
        if not isinstance(lab, dict):
            continue
        try:
            sizes.append(float(lab.get("size") or feature(lab.get("kind", "site")).size))
        except (TypeError, ValueError):
            continue
    base = FEATURES["scale"].size
    return round(min([base] + [s * SCALE_TO_LABEL for s in sizes if s > 0]), 2)
