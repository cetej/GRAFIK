# The second Velsen infographic, "Who killed him?": the fort in 3D with the place of each story and the other wells with human bones, six painted scenes with one argument for and one against. Text is vector, layers for VectorCraft.
# Facts with pages: docs/spikes/2026-11-01-velsen.md. Model: scripts/3d/velsen_pevnost.py. Scenes: velsen_scenare.py, velsen_hero.py.
#   python scripts/plakaty/velsen_scenare_stranka.py LIB OUT [--knihovna http://127.0.0.1:8300]
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from shapely.geometry import box, shape
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).parent))
from sazba import FONT, cover, group, image_tag, para, text, write_poster  # noqa: E402

W, H = 1800, 2400
BG, GOLD, WHITE, DIM = "#340d11", "#dcb66e", "#f0e8da", "#b9a99a"
RED, EDITOR = "#e0322f", "#a9c9d8"
SEA, LAND, WATER_INK, PEOPLE = "#26090d", "#6a3a35", "#8fb6c9", "#e0ad97"
LAND_FILE = Path(r"C:/Users/stock/Documents/000_NGM/NG-ROBOT/data/teaser_satmap/ne_10m_land.geojson")     # Natural Earth, read only
HEAD, BODY = 30, 24

# number: picture, title, for, against, who of the book's editors holds it
CARDS = {
    1: ("scenare/s1-613.png", "Padl při útoku Frísů", "střely, kosti v přístavu, spálená mazanice", "pevnost podle Tacita nepadla, proč bez zbroje?", "Váhá Carol van Driel-Murray"),
    2: ("scenare/s2-611.png", "Vražda", "tělo, prsten i dýka zmizely pod vodou", "moc ran, a tělo by uprostřed pevnosti páchlo", ""),
    3: ("scenare/s3-501.png", "Poprava dezertéra", "rány jako součást veřejného ponížení", "odsouzenému by vzali opasek", ""),
    4: ("hero/hero-343-soumrak.png", "Zabili ho vlastní", "slepá zuřivost, jako u centuriona Lucilla", "kukly much: tělo prý leželo dny venku", "Volí Mark Driessen, váhá van Driel-Murray"),
    5: ("scenare/s5-501.png", "Odveta Frísů", "mučení zajatců, domácí nádoba ve studni", "v kraji bez obdoby, v pevnosti po nich stopa není", ""),
    6: ("scenare/s6-621.png", "Oběť při uzavření studny", "mučení, zlomená dýka, neúplná nádoba", "oblečené tělo ve studni nemá obdobu", "Driessen, kdyby nebylo Tacita"),
}


# chimneys the generator painted in spite of the prompt, filled from the sky around them: x0, y0, x1, y1
RETOUCH = {
    "scenare/s1-613.png": ((284, 44, 309, 80), (335, 76, 350, 92), (514, 116, 522, 133)),
    "scenare/s2-611.png": ((814, 70, 836, 106), (840, 84, 860, 105), (775, 93, 795, 113)),
    "scenare/s3-501.png": ((254, 28, 265, 45), (418, 69, 438, 81)),
}


def scene(lib: Path, src: str) -> Image.Image:
    im = Image.open(lib / src).convert("RGB")
    if src not in RETOUCH:
        return im
    mask = np.zeros((im.height, im.width), np.uint8)
    for x0, y0, x1, y1 in RETOUCH[src]:
        mask[y0:y1, x0:x1] = 255
    return Image.fromarray(cv2.inpaint(np.asarray(im), mask, 5, cv2.INPAINT_TELEA))


def path_of(geom, to_xy) -> str:
    def ring(c):
        return "M" + "L".join("%.1f,%.1f" % to_xy(x, y) for x, y in c) + "Z"
    polys = geom.geoms if hasattr(geom, "geoms") else [geom]
    d = ""
    for g in polys:
        if g.geom_type == "Polygon" and not g.is_empty:
            d += ring(g.exterior.coords) + "".join(ring(i.coords) for i in g.interiors)
    return d


def mapka(lib: Path, x: float, y: float, w: float, small: float = 21, big: float = 28, sea: tuple[float, float] = (0.2, 54.0)) -> tuple[str, float]:
    """The place of the garrison on a small map; today's coast and river. Returns the svg and its height."""
    lon0, lon1, lat0, lat1 = -1.5, 15.5, 47.5, 55.5
    ks, kb = small / 21, big / 28
    k = w / ((lon1 - lon0) * 0.63)
    h = (lat1 - lat0) * k

    def to_xy(lon, lat):
        return x + (lon - lon0) * 0.63 * k, y + (lat1 - lat) * k

    frame = box(lon0, lat0, lon1, lat1)
    land = json.loads(LAND_FILE.read_text(encoding="utf-8"))
    near = [shape(f["geometry"]).buffer(0).intersection(frame) for f in land["features"] if shape(f["geometry"]).intersects(frame)]
    area = unary_union(near).simplify(0.015)
    s = f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{SEA}"/><path d="{path_of(area, to_xy)}" fill="{LAND}" fill-rule="evenodd"/>'
    rivers = json.loads((lib / "mapa/ne_10m_rivers.geojson").read_text(encoding="utf-8"))
    for f in rivers["features"]:
        if f["properties"].get("name") in ("Rhein", "Rhin", "Rhine", "Lek"):
            line = shape(f["geometry"]).intersection(frame)
            for part in (line.geoms if hasattr(line, "geoms") else [line]):
                if not part.is_empty:
                    s += '<polyline points="' + " ".join("%.1f,%.1f" % to_xy(a, b) for a, b in part.coords) + f'" fill="none" stroke="{WATER_INK}" stroke-width="2.2"/>'
    vx, vy = to_xy(4.66, 52.46)
    px_, py_ = to_xy(14.42, 50.08)
    s += f'<circle cx="{px_:.1f}" cy="{py_:.1f}" r="{4 * ks:g}" fill="{WHITE}"/>' + text(px_ - 9 * ks, py_ + 7 * ks, "Praha", small, WHITE, 400, "end")
    s += text(*to_xy(*sea), "Severní moře", small, WATER_INK)
    s += text(*to_xy(8.3, 50.75), "Rýn", small, WATER_INK)
    s += text(*to_xy(5.3, 53.45), "Frísové", small, PEOPLE)
    s += f'<circle cx="{vx:.1f}" cy="{vy:.1f}" r="{7 * kb:g}" fill="{GOLD}"/>' + text(vx + 13 * kb, vy + 9 * kb, "Velsen", big, GOLD, 600)
    return s, h


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    lib, out = Path(sys.argv[1]), Path(sys.argv[2])
    knihovna = sys.argv[sys.argv.index("--knihovna") + 1] if "--knihovna" in sys.argv else None

    t = group("Titulek", text(40, 132, "KDO HO ZABIL?", 124, GOLD, 700) + text(40, 188, "Šest vysvětlení z knihy. Ani její editoři se neshodnou.", 36, WHITE))

    # the fort, the width of the page
    fy = 215
    fort = Image.open(lib / "pevnost/hotovo/pevnost.png").convert("RGB")
    points = json.loads((lib / "pevnost/hotovo/body.json").read_text(encoding="utf-8"))["points"]
    k = W / fort.width
    grafika = group("Pevnost", image_tag(fort, 0, fy, W, fort.height * k))

    def at(name):
        return points[name][0] * k, fy + points[name][1] * k

    wells = ""
    for name in ("W.5", "W.8", "W.1", "W.20", "W.24", "W.16", "S221", "S190"):
        x, y = at(name)
        wells += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="{RED}" stroke="{WHITE}" stroke-width="1.5"/>'
    t += group("Studny s kostmi", wells)
    x, y = at("W.2")
    t += group("Studna s mužem", f'<circle cx="{x:.1f}" cy="{y:.1f}" r="12" fill="{RED}" stroke="{WHITE}" stroke-width="3"/><circle cx="{x:.1f}" cy="{y:.1f}" r="21" fill="none" stroke="{WHITE}" stroke-width="2.5"/>' + text(x + 83, y + 22, "Studna s mužem", 28, BG, 600))
    pins = ""
    for n in CARDS:
        x, y = at(f"misto{n}")
        pins += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="21" fill="{GOLD}" stroke="{BG}" stroke-width="2"/>' + text(x, y + 10, str(n), 28, BG, 700, "middle")
    t += group("Místa", pins)
    # the quiet water at the upper right: the bones of the others, the place of the garrison
    tx = 900
    t += group("Nebyl sám", text(tx, fy + 58, "Nebyl sám", 44, WHITE, 700)
               + text(tx, fy + 100, "Kosti nejméně 20 lidí, i žen a dětí.", 28, WHITE)
               + text(tx, fy + 136, "V přístavu a v dalších studních (červeně).", 28, WHITE))
    sv, mh = mapka(lib, W - 375 - 30, 26, 375)
    grafika += group("Mapka", sv)
    t += group("Mapka text", text(W - 30, 26 + mh + 32, "Námořní základna v zemi Frísů", BODY, WHITE, 400, "end"))

    # six scenes
    cw, ch = 560, 367
    xs, ys = (40, 620, 1200), (fy + fort.height * k + 36, fy + fort.height * k + 36 + 534)
    pics = ""
    for n, (src, title, pro, proti, who) in CARDS.items():
        cx, cy = xs[(n - 1) % 3], ys[(n - 1) // 3]
        pics += cover(scene(lib, src), cx, cy, cw, ch)
        y = cy + ch + 38
        s = f'<circle cx="{cx + 17:.1f}" cy="{y - 10:.1f}" r="17" fill="{GOLD}"/>' + text(cx + 17, y - 1, str(n), 24, BG, 700, "middle") + text(cx + 46, y, title, HEAD, GOLD, 600)
        s += text(cx, y + 36, f"Pro: {pro}", BODY, WHITE) + text(cx, y + 66, f"Proti: {proti}", BODY, WHITE)
        if who:
            s += text(cx, y + 96, who, 22, EDITOR, 500)
        t += group(f"Scénář {n}", s)
    grafika += group("Scény", pics)

    y = ys[1] + 534 + 44
    t += group("Zbroj", text(40, y, "A co zbroj?", HEAD, GOLD, 600) + text(205, y, "Rány hlavně pod pasem by seděly na muže ve zbroji, ale vpichy zevnitř pánve se s ní dělají těžko.", 26, WHITE))
    t += group("Zdroj", para(40, y + 50, "Zdroj: Driessen, van Driel-Murray (eds.), Victims of Violence from the early Roman fort Velsen 1, Sidestone 2026, CC BY-NC-ND 4.0: scénáře s. 157–163, plán pevnosti (fáze 3 se studnami). "
                                         "Model pevnosti: Blender podle plánu, bez AI; podoba budov a lodě jsou rekonstrukce, výšky 2× převýšené, místa scénářů jsou ilustrační, kniha je neurčuje. Scény: FLUX 3 Klein (AI), představa, ne nález. Oběť podle obr. 11.1 (F. Marschall). Mapa: Natural Earth, dnešní pobřeží a tok Rýna; poloha podle Livius.org.", 20, DIM, 215, 1.3))

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}" font-stretch="semi-condensed">'
           f'<rect id="Pozadí" width="{W}" height="{H}" fill="{BG}"/>' + group("Grafika", grafika) + group("Texty", t) + "</svg>")
    write_poster(svg, out, "velsen-scenare", W, H, "Kdo ho zabil? Šest vysvětlení", knihovna, True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
