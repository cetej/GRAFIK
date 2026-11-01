# Poster of the axolotl in the manner of National Geographic: the realistic animal from the 3D model on clean paper, short labels on thin leaders, data panels instead of icons.
# UNFINISHED: the operator paused this version on 2026-11-01, nobody has seen its output yet, see docs/STAV.md.
#   python scripts/plakaty/axolotl_ng.py ASSETS OUT_DIR [--knihovna http://127.0.0.1:8300]
# ASSETS: hero-cut.png (animal, RGBA, 1536 x 1120), divoky-cut.png (the wild form, RGBA). Fonts and colours: shared/ngm_shared/textlayer/style.py. Facts: docs/spikes/2026-11-01-plakaty-osoba-zvire.md.
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sazba import crop_alpha, cutout, fit, group, text, wrap, write_poster  # noqa: E402

W, H = 1500, 2000
GEO, BUM = "'Geograph Edit', 'Bahnschrift', sans-serif", "'NatGeo Bumstead', Georgia, serif"
PAPER, INK, MUTED, GOLD, RULE = "#f6f3ec", "#1a1a1a", "#5b5a54", "#c9a227", "#b9b4a6"
SKIN, BUD, GREEN = "#efcfc4", "#e39a98", "#636d38"
NB = " "
HERO = (20, 235, 0.92)
FACTS = (("Vnější žábry", "Tři páry stvolů s vlákny. Dýchá i plícemi a kůží.", 70, 408, (690, 470), (300, 402)),
         ("Ocasní lem", "Ploutev se táhne od hlavy po kloaku.", 70, 590, (300, 690), (200, 650)),
         ("Neotenie", "Dospívá a rozmnožuje se jako larva, bez přeměny.", 1168, 408, (1139, 476), (1160, 402)),
         ("Oči bez víček", "Víčka se objeví až po přeměně, tu v laboratoři vyvolá hormon štítné žlázy.", 1168, 560, (1074, 557), (1160, 554)),
         ("Prsty", f"Vpředu čtyři, vzadu pět.", 70, 1105, (250, 860), (150, 1078)),
         ("Loví sáním", "Rychle otevře tlamu a kořist nasaje.", 1130, 1120, (1200, 649), (1180, 1092)))


def para(x, y, s, size, fill, n, leading=1.3, weight=400, anchor="start") -> str:
    return "".join(text(x, y + i * size * leading, line, size, fill, weight, anchor) for i, line in enumerate(wrap(s, n)))


def rule(x0, y0, x1, y1, color=RULE, width=1.4) -> str:
    return f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y1}" stroke="{color}" stroke-width="{width}"/>'


def header() -> str:
    o = f'<rect x="70" y="62" width="64" height="9" fill="{GOLD}"/>' + text(70, 112, "OHROŽENÉ DRUHY", 25, GOLD, 700, spacing=3)
    o += text(66, 262, "AXOLOTL", 164, INK, 700, spacing=2)
    o += f'<g font-family="{BUM}">' + text(760, 262, "Ambystoma mexicanum", 50, INK, 400, italic=True) + "</g>"
    o += para(70, 316, "Celý život zůstává larvou a umí si nechat dorůst končetinu. Ve volné přírodě přežívá už jen na třech místech na jihu Mexico City.", 30, INK, 88, 1.28)
    return group("Záhlaví", o)


def stage(x, y, name, days, k) -> str:
    """One step of the regrowth: a forearm cut at the dashed line and what has grown from it; k = 0..4."""
    arm = f'<path d="M{x - 26} {y} L{x - 21} {y + 62} L{x + 21} {y + 62} L{x + 26} {y} Z" fill="{SKIN}" stroke="{INK}" stroke-width="1.3"/>'
    t, b = y + 62, y + 62
    grown = (f'<path d="M{x - 21} {t} Q{x} {b + 13} {x + 21} {t} Z" fill="{BUD}" stroke="{INK}" stroke-width="1.3"/>',
             f'<path d="M{x - 21} {t} Q{x - 16} {b + 38} {x} {b + 40} Q{x + 16} {b + 38} {x + 21} {t} Z" fill="{BUD}" stroke="{INK}" stroke-width="1.3"/>',
             f'<path d="M{x - 21} {t} Q{x - 24} {b + 66} {x} {b + 72} Q{x + 24} {b + 66} {x + 21} {t} Z" fill="{BUD}" stroke="{INK}" stroke-width="1.3"/>',
             f'<path d="M{x - 21} {t} L{x - 18} {b + 30} Q{x - 42} {b + 58} {x - 28} {b + 88} Q{x} {b + 104} {x + 28} {b + 88} Q{x + 42} {b + 58} {x + 18} {b + 30} L{x + 21} {t} Z" fill="{BUD}" stroke="{INK}" stroke-width="1.3"/>',
             f'<path d="M{x - 21} {t} L{x - 18} {b + 34} Q{x - 40} {b + 50} {x - 40} {b + 92} L{x - 31} {b + 93} L{x - 25} {b + 62} L{x - 19} {b + 110} L{x - 10} {b + 110} L{x - 7} {b + 68} '
             f'L{x + 2} {b + 114} L{x + 11} {b + 112} L{x + 11} {b + 68} L{x + 22} {b + 100} L{x + 31} {b + 96} Q{x + 38} {b + 54} {x + 18} {b + 34} L{x + 21} {t} Z" fill="{SKIN}" stroke="{INK}" stroke-width="1.3"/>')[k]
    cut = f'<line x1="{x - 38}" y1="{t}" x2="{x + 38}" y2="{t}" stroke="{INK}" stroke-width="1.2" stroke-dasharray="5 4"/>'
    return arm + grown + cut + text(x, y + 212, name, 22, INK, 500, "middle") + text(x, y + 240, days, 20, MUTED, 400, "middle")


def regrowth(x, y) -> str:
    o = text(x, y, "DORŮSTÁNÍ KONČETINY", 25, INK, 700, spacing=1) + rule(x, y + 14, x + 610, y + 14, INK, 1.6)
    for k, (name, days) in enumerate((("Hojení", "1 den"), ("Blastém", "6–12 dní"), ("Pupen", "10–24 dní"), ("Paletka", "24–28 dní"), ("Prsty", "dál roste"))):
        o += stage(x + 62 + k * 121, y + 44, name, days, k)
    o += para(x, y + 328, f"Larvám doroste 98{NB}% končetiny za 66 dní, mladým dospělým za stejnou dobu 56{NB}%. Dorůstá i ocas, mícha, srdce a sítnice. Čočka ne.", 23, INK, 56)
    return group("Dorůstání", o)


def density(x, y) -> str:
    o = text(x, y, "MIZÍ Z XOCHIMILKA", 25, INK, 700, spacing=1) + rule(x, y + 14, x + 340, y + 14, INK, 1.6)
    o += text(x, y + 46, "jedinci na km²", 21, MUTED)
    base, top = y + 270, 190
    for k, (year, value, tag) in enumerate(((1998, 6000, f"6{NB}000"), (2004, 1000, f"1{NB}000"), (2008, 100, "100"), (2014, 35, "asi 35"))):
        bx = x + 6 + k * 84
        h = max(3, top * value / 6000)
        o += f'<rect x="{bx}" y="{base - h:.1f}" width="62" height="{h:.1f}" fill="{GREEN}"/>' + text(bx + 31, base - h - 9, tag, 22, INK, 500, "middle") + text(bx + 31, base + 28, str(year), 20, MUTED, 400, "middle")
    o += rule(x, base, x + 340, base, INK, 1.2)
    o += para(x, y + 328, f"Volně žije 50 až 1{NB}000 dospělých. IUCN: kriticky ohrožený.", 23, INK, 31)
    return group("Hustota", o)


def forms(x, y, assets: Path) -> str:
    o = text(x, y, "DIVOKÝ A CHOVNÝ", 25, INK, 700, spacing=1) + rule(x, y + 14, x + 340, y + 14, INK, 1.6)
    wild, _ = crop_alpha(Image.open(assets / "divoky-cut.png").convert("RGBA"), 0)
    k = min(340 / wild.width, 215 / wild.height)
    o += fit(wild, x + (340 - wild.width * k) / 2, y + 40, wild.width * k, wild.height * k)
    o += para(x, y + 288, f"Divoký typ je tmavý a skvrnitý. Růžová forma je známá jen z chovů, nese mutaci genu edn3.", 23, INK, 31)
    return group("Formy", o)


def hero(assets: Path) -> tuple[str, str]:
    cut = Image.open(assets / "hero-cut.png").convert("RGBA")
    im, shift = crop_alpha(cut, 0)
    hx, hy, k = HERO
    on = lambda p: (hx + p[0] * k, hy + p[1] * k)
    picture = group("Axolotl", fit(im, hx + shift[0] * k, hy + shift[1] * k, im.width * k, im.height * k))
    lines, words = "", ""
    for title, body, tx, ty, target, start in FACTS:
        ax, ay = on(target)
        lines += rule(start[0], start[1], round(ax, 1), round(ay, 1), INK, 1.3) + f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="3.6" fill="{INK}"/>'
        words += text(tx, ty, title, 27, INK, 700) + para(tx, ty + 32, body, 23, INK, 24)
    return picture + group("Vodítka", lines), group("Popisky", words)


def poster(assets: Path) -> str:
    gfx = [group("Papír", f'<rect width="{W}" height="{H}" fill="{PAPER}"/>')]
    picture, words = hero(assets)
    gfx.append(picture)
    txt = [header(), words, regrowth(70, 1290), density(730, 1290), forms(1090, 1290, assets)]
    gfx.append(group("Dělicí linka", rule(70, 1250, W - 70, 1250, INK, 2.2)))
    txt.append(group("Patička", para(70, 1848, "ZDROJE: IUCN Red List 2020-3; Voss a kol. 2015; Monaghan a kol. 2014; Joven a kol. 2019; Crowner a kol. 2019; Woodcock a kol. 2017; Khattak a kol. 2014; Toussaint-Lardé a kol. 2025. "
                                        "ILUSTRACE: zvíře z 3D modelu Hunyuan, vzhled lokální FLUX (AI). Sazba a grafy GRAFIK.", 19, MUTED, 150, 1.34)))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{GEO}">'
            f'<g id="Grafika">{"".join(gfx)}</g><g id="Texty">{"".join(txt)}</g></svg>')


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    assets, out = Path(sys.argv[1]), Path(sys.argv[2])
    if not (assets / "divoky-cut.png").exists():
        cutout(assets / "divoky.png", assets / "divoky-cut.png", shadow=0.4)
    knihovna = sys.argv[sys.argv.index("--knihovna") + 1] if "--knihovna" in sys.argv else None
    write_poster(poster(assets), out, "axolotl-ng", W, H, "Axolotl: plakát ve stylu National Geographic", knihovna, ai=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
