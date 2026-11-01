# Large infographic of the Pantheon from the renders of scripts/3d/lod_pantheon.py (free):
#   python scripts/3d/pantheon_plakat.py DIR OUT_DIR [--knihovna http://127.0.0.1:8300]
# DIR holds <shot>/rez.png, <shot>/body.json and, for rez and rozklad, <shot>/vrstva-*.png (lod_pantheon.py --vrstvy).
# All text is vector (one family, two weights, docs/infografiky-zasady.md); Chromium makes the PNG and the PDF.
# Top-level <g id> = layer in VectorCraft, <g id> inside it = named group: Grafika holds every object on its own,
# Texty every label on its own. pantheon-vectorcraft-<time>.svg is the copy for the window; it is never overwritten,
# because the operator may have edited it.
# --knihovna: the PNG also goes to the Knihovna tab of the Studio, labelled as a render without AI.
import base64
import io
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "shared")]

W, H = 1600, 2400
BG, INK, MUTED, ACCENT, LINE, FOOT = "#1d2532", "#f1ede4", "#a7b1bf", "#dcb062", "#fff6de", "#8b95a4"
FONT = "Bahnschrift, 'Roboto Condensed', 'Arial Narrow', sans-serif"
AI_NOTE = "Model a render: Blender, bez AI; schéma a popisky redakčně."
SOURCES = ("Zdroj: Moore, Constructor 9/2002; Mark a Hutchison, Art Bulletin 1986 (podle citací); Wikipedia: Pantheon, Rome; "
           "2nd-century Roman domes; Roman concrete (Lancaster). Okulus 8,2–9,1 m podle zdroje. Hranice vrstev betonu jsou schematické, "
           "zrno zvětšené, rozměry bez zdroje jsou ve skriptu označené jako odhad.")

# name, explanation, target (point in body.json or (x, y, z) in metres), label position, side of the leader
HERO_LABELS = [
    ("Okulus", "asi 9 m, stále otevřený", "okulus", (1045, 72), "left"),
    ("Tuf a pemza", "asi 1 350 kg/m³", (15.6, 0, 38.4), (1212, 142), "left"),
    ("140 kazet", "ubírají méně než 5 % hmoty", (-10.36, 13.26, 35.27), (690, 208), "right"),
    ("7 prstenců", "přitěžují patu kupole", "stupne", (1308, 300), "left"),
    ("Kusy cihel", "střední vrstva betonu", (25.5, 0, 27.0), (1308, 372), "left"),
    ("Koule 43,3 m", "vejde se přesně", "pata_p", (1308, 444), "left"),
    ("Dutiny ve zdi", "tíhu nesou cihlové oblouky", "komora", (1308, 516), "left"),
    ("Travertin v základu", "asi 2 200 kg/m³", "zaklad", (1308, 742), "left"),
    ("Když prší", "voda steče do odpadů", "podlaha", (998, 730), "left"),
    ("Agrippův nápis", "Hadrián ho ponechal", "napis", (284, 520), "right"),
]
FACTS = [
    ("43,3 m", "průměr i výška"),
    ("6,4→1,2 m", "tloušťka kupole"),
    ("4 535 t", "hmotnost kupole"),
    ("60 t", "jeden sloup z Egypta"),
    ("609", "z chrámu kostel"),
]
WHY = [
    ("Lehčí beton nahoře", "Se stejně těžkým betonem by napětí v kupoli bylo asi o 80 % vyšší."),
    ("14 trhlin", "Vedou od paty asi do 54°. Kupole pak funguje jako řada oblouků."),
    ("Prstence a pilíře", "Prstence přitěžují patu, cihlové oblouky vedou tíhu na 8 pilířů."),
]
HERO_LAYERS = {"zem": "Zem a základ", "podlaha": "Podlaha", "rotunda": "Rotunda v řezu", "portik": "Portik", "postavy": "Postavy"}
EXPLODED_LAYERS = {"zaklad": "Základ", "podlaha": "Podlaha", "stena": "Stěna", "kupole": "Kupole", "prstenec": "Bronzový prstenec"}


def place_of(d: Path, shot: str, box: tuple[int, int, int, int]) -> dict:
    info = json.loads((d / shot / "body.json").read_text(encoding="utf-8"))
    x, y, w, h = box
    k = min(w / info["res"][0], h / info["res"][1])
    return {"x": x + (w - info["res"][0] * k) / 2, "y": y + (h - info["res"][1] * k) / 2, "k": k, "info": info}


def image_tag(im: Image.Image, fmt: str, x: float, y: float, w: float, h: float) -> str:
    buf = io.BytesIO()
    if fmt == "JPEG":
        im.save(buf, fmt, quality=92)
    else:
        im.save(buf, fmt, optimize=True)
    uri = f"data:image/{fmt.lower()};base64," + base64.b64encode(buf.getvalue()).decode()
    return f'<image href="{uri}" x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}"/>'


def flat_picture(d: Path, shot: str, box: tuple[int, int, int, int]) -> str:
    """One piece, flattened on the page colour."""
    p = place_of(d, shot, box)
    im = Image.open(d / shot / "rez.png").convert("RGBA")
    flat = Image.alpha_composite(Image.new("RGBA", im.size, tuple(int(BG[i:i + 2], 16) for i in (1, 3, 5)) + (255,)), im).convert("RGB")
    return image_tag(flat, "JPEG", p["x"], p["y"], im.width * p["k"], im.height * p["k"])


def object_layers(d: Path, shot: str, p: dict, names: dict[str, str]) -> str:
    """Every object cropped to itself: in VectorCraft it can be picked, moved or hidden on its own. Where two objects
    share an edge both are part transparent and the page would show through, so the edge alpha is raised a little."""
    out = []
    for key, title in names.items():
        im = Image.open(d / shot / f"vrstva-{key}.png").convert("RGBA")
        box = im.getchannel("A").getbbox()
        if box is None:
            continue
        im = im.crop(box)
        r, g, b, a = im.split()
        im = Image.merge("RGBA", (r, g, b, a.point(lambda v: 255 - (255 - v) * (255 - v) // 255)))
        tag = image_tag(im, "PNG", p["x"] + box[0] * p["k"], p["y"] + box[1] * p["k"], im.width * p["k"], im.height * p["k"])
        out.append(f'<g id="{title}">{tag}</g>')
    return "".join(out)


def to_page(place: dict, where) -> tuple[float, float]:
    info = place["info"]
    if isinstance(where, str):
        u, v = info["points"][where]
    else:
        ox, oy = info["origin"]
        b = info["basis"]
        u = ox + b["x"][0] * where[0] + b["y"][0] * where[1] + b["z"][0] * where[2]
        v = oy + b["x"][1] * where[0] + b["y"][1] * where[1] + b["z"][1] * where[2]
    return place["x"] + u * place["k"], place["y"] + v * place["k"]


def text(x, y, s, size, fill=INK, weight=400, anchor="start", halo=False, spacing=0.0) -> str:
    extra = f' stroke="#000" stroke-width="{size * 0.16:.1f}" stroke-linejoin="round" paint-order="stroke"' if halo else ""
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}"{ls}{extra}>{s}</text>'


def label(place, where, name, smalls, pos, align, size=23) -> tuple[str, str]:
    """(leader for Grafika, name and explanation for Texty), each its own group."""
    ax, ay = to_page(place, where)
    px, py = pos
    end = px - 8 if align == "left" else px + 8
    ly = py + size * 0.72
    pts = [(ax, ay), (end, ly)] if abs(ay - ly) < 8 or abs(ax - end) < 8 else [(ax, ay), (ax, ly), (end, ly)]
    poly = " ".join(f"{a:.1f},{b:.1f}" for a, b in pts)
    anchor = "start" if align == "left" else "end"
    lead = (f'<g id="Vodítko {name}"><polyline points="{poly}" fill="none" stroke="#fff" stroke-opacity=".8" stroke-width="1.3"/>'
            f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="3.6" fill="#fff"/></g>')
    words = text(px, py + size * 0.9, name, size, ACCENT, 700, anchor, True)
    for i, small in enumerate(smalls):
        words += text(px, py + size * (1.95 + 1.1 * i), small, size * 0.86, INK, 400, anchor, True)
    return lead, f'<g id="{name}">{words}</g>'


def heading(x, y, s) -> str:
    return f'<g id="Nadpis {s}">{text(x, y, s.upper(), 25, ACCENT, 700, spacing=1.2)}</g>'


def sphere(place) -> str:
    """The sphere that fits inside: dashed, exactly from the projection of the model, with its two 43.3 m dimensions."""
    k, ox, oy = place["k"], place["x"], place["y"]
    pts = [(ox + u * k, oy + v * k) for u, v in place["info"]["kruh"]]
    d = "M" + " L".join(f"{a:.1f} {b:.1f}" for a, b in pts) + " Z"
    out = (f'<path d="{d}" fill="none" stroke="#0f141e" stroke-opacity=".65" stroke-width="5.4" stroke-dasharray="14 12"/>'
           f'<path d="{d}" fill="none" stroke="{LINE}" stroke-width="2.6" stroke-dasharray="14 12"/>')
    for a, b in (("pata_l", "pata_p"), ("podlaha_stred", "vrchol_koule")):
        (ax, ay), (bx, by) = to_page(place, a), to_page(place, b)
        out += (f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="#0f141e" stroke-opacity=".6" stroke-width="4"/>'
                f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="{LINE}" stroke-width="1.8"/>')
        for px, py in ((ax, ay), (bx, by)):
            out += f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.2" fill="{LINE}"/>'
    return f'<g id="Koule">{out}</g>'


def wrap(s: str, n: int) -> list[str]:
    lines, cur = [], ""
    for w in s.split(" "):
        if cur and len(cur) + 1 + len(w) > n:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + [cur] if cur else lines


def plan(dim: dict, x0: float, y0: float) -> tuple[str, str]:
    """Floor plan from the same numbers as the model: eight piers and where the cut runs. (drawing, its texts)"""
    s = 3.1
    cx, cy = x0 + 48.5 * s + 6, y0 + 28.5 * s
    x = lambda m: round(cx + m * s, 1)
    y = lambda m: round(cy + m * s, 1)
    r_i = dim["inner_d"] / 2
    r_o = r_i + dim["wall"]
    e_w, e_d = dim["exedra_w"] / 2, dim["exedra_d"]
    x_wall = -(r_o + dim["block_d"])
    x_col = x_wall - dim["portico_d"]
    w = dim["portico_w"] / 2
    wall = "#d9cdb4"
    o = [f'<rect x="{x(x_wall)}" y="{y(-w - 1)}" width="{round((-r_i + 2 - x_wall) * s, 1)}" height="{round((2 * w + 2) * s, 1)}" fill="{wall}"/>',
         f'<circle cx="{x(0)}" cy="{y(0)}" r="{round(r_o * s, 1)}" fill="{wall}"/>',
         f'<circle cx="{x(0)}" cy="{y(0)}" r="{round(r_i * s, 1)}" fill="{BG}"/>',
         f'<rect x="{x(x_wall - 0.5)}" y="{y(-4)}" width="{round((-r_i - x_wall + 1) * s, 1)}" height="{round(8 * s, 1)}" fill="{BG}"/>']
    for deg, kind in ((0, "semi"), (45, "rect"), (90, "semi"), (135, "rect"), (-45, "rect"), (-90, "semi"), (-135, "rect")):
        rot = f'rotate({deg} {x(0)} {y(0)})'
        if kind == "rect":
            o.append(f'<rect x="{x(r_i - 0.6)}" y="{y(-e_w)}" width="{round((e_d + 0.6) * s, 1)}" height="{round(2 * e_w * s, 1)}" fill="{BG}" transform="{rot}"/>')
        else:
            o.append(f'<path d="M{x(r_i - 0.6)} {y(-e_w)} L{x(r_i + e_d - e_w)} {y(-e_w)} A{round(e_w * s, 1)} {round(e_w * s, 1)} 0 0 1 {x(r_i + e_d - e_w)} {y(e_w)} '
                     f'L{x(r_i - 0.6)} {y(e_w)} Z" fill="{BG}" transform="{rot}"/>')
    ys = [-w + dim["portico_w"] * i / 7 for i in range(8)]
    for cxx, cyy in [(x_col, c) for c in ys] + [(x_col + d, ys[i]) for d in (4.8, 9.6) for i in (0, 2, 5, 7)]:
        o.append(f'<circle cx="{x(cxx)}" cy="{y(cyy)}" r="{round(dim["col_d"] / 2 * s, 1)}" fill="{wall}"/>')
    o.append(f'<line x1="{x(x_wall + 1.4)}" y1="{y(0)}" x2="{x(r_o + 1)}" y2="{y(0)}" stroke="{ACCENT}" stroke-width="2.6" stroke-dasharray="9 6"/>')
    left = x(x_col)
    o.append(f'<line x1="{left}" y1="{y(27)}" x2="{left + 20 * s}" y2="{y(27)}" stroke="{INK}" stroke-width="2"/>')
    return "".join(o), text(x(0), y(0) - 8, "řez", 18, ACCENT, 700, "middle") + text(left, y(27) - 8, "20 m", 17)


def poster(d: Path) -> str:
    gfx, txt = [f'<g id="Pozadí"><rect width="{W}" height="{H}" fill="{BG}"/></g>'], []
    # main picture: the cut building, across the whole width
    hero = place_of(d, "rez", (0, 30, W, 900))
    gfx.append(f'<g id="Hlavní řez">{object_layers(d, "rez", hero, HERO_LAYERS)}</g>')
    gfx.append(sphere(hero))
    txt.append('<g id="Nadpis">' + text(50, 118, "PANTHEON", 88, ACCENT, 700, spacing=2)
               + text(50, 162, "Největší kupole z nevyztuženého betonu", 31, MUTED) + text(50, 200, "Řím, asi 114–126 n. l.", 31, MUTED) + "</g>")
    leads, words = [], []
    for name, small, where, pos, align in HERO_LABELS:
        a, b = label(hero, where, name, [small], pos, align)
        leads.append(a)
        words.append(b)
    gfx.append(f'<g id="Vodítka řezu">{"".join(leads)}</g>')
    txt.append(f'<g id="Popisky řezu">{"".join(words)}</g>')

    # what the main picture cannot show: how it comes apart
    txt.append(heading(50, 980, "Z čeho se skládá"))
    ex = place_of(d, "rozklad", (0, 992, 620, 1046))
    gfx.append(f'<g id="Rozložení">{object_layers(d, "rozklad", ex, EXPLODED_LAYERS)}</g>')
    info = ex["info"]
    r_o = info["dim"]["inner_d"] / 2 + info["dim"]["wall"]
    up = info["explode"]
    leads, words = [], []
    for name, small, where, pos in (
        ("Bronzový prstenec", ["lemuje okulus"], (4.7, 0, 44.0 + up["lip"]), (560, 1030)),
        ("Kupole", ["jedna skořepina: 7 prstenců", "venku, kazety uvnitř"], (r_o * 0.45, r_o * 0.1, 40 + up["dome_low"]), (560, 1200)),
        ("Stěna", ["8 pilířů, 7 výklenků a vchod"], (r_o * 0.75, r_o * 0.55, 10), (560, 1480)),
        ("Podlaha", ["mírně vypouklá, s odtoky"], (10, 12, up["floor"]), (560, 1700)),
        ("Základ", ["prstenec 7,2 × 4,7 m na jílu"], (24.0, 3.0, -2.5 + up["found"]), (560, 1860)),
    ):
        a, b = label(ex, where, name, small, pos, "left", 22)
        leads.append(a)
        words.append(b)
    gfx.append(f'<g id="Vodítka rozložení">{"".join(leads)}</g>')
    txt.append(f'<g id="Popisky rozložení">{"".join(words)}</g>')

    # the room from the inside
    txt.append(heading(860, 980, "Pohled k okulu"))
    gfx.append(f'<g id="Pohled k okulu">{flat_picture(d, "interier", (860, 992, 710, 592))}</g>')

    # the concrete, bottom to top
    txt.append(heading(860, 1636, "Beton: čím výš, tím lehčí"))
    samples, words = [], []
    for i, (shot, name, small) in enumerate((("beton_dolni", "Dole travertin", "asi 2 200 kg/m³"),
                                             ("beton_stred", "Uprostřed kusy cihel", "hustota nedoložená"),
                                             ("beton_horni", "Nahoře tuf a pemza", "asi 1 350 kg/m³"))):
        x = 860 + i * 240
        samples.append(f'<g id="{name}">{flat_picture(d, shot, (x, 1652, 230, 144))}</g>')
        words.append(f'<g id="Popisek {name}">{text(x, 1826, name, 22, ACCENT, 700)}{text(x, 1852, small, 20)}</g>')
    gfx.append(f'<g id="Vzorky betonu">{"".join(samples)}</g>')
    txt.append(f'<g id="Popisky betonu">{"".join(words)}</g>')

    # why it stands, plan and the numbers along the bottom
    txt.append(heading(860, 1912, "Proč stojí"))
    words = []
    for i, (value, small) in enumerate(WHY):
        y = 1952 + i * 104
        lines = "".join(text(860, y + 28 + j * 25, line, 21) for j, line in enumerate(wrap(small, 44)))
        words.append(f'<g id="{value}">{text(860, y, value, 26, ACCENT, 700)}{lines}</g>')
    txt.append(f'<g id="Proč stojí">{"".join(words)}</g>')
    txt.append(heading(50, 2076, "Čísla"))
    words = []
    for x, (value, small) in zip((50, 190, 372, 530, 668), FACTS):
        lines = "".join(text(x, 2162 + j * 25, line, 21) for j, line in enumerate(wrap(small, 15)))
        words.append(f'<g id="Číslo {value}">{text(x, 2130, value, 36, ACCENT, 700)}{lines}</g>')
    txt.append(f'<g id="Čísla">{"".join(words)}</g>')
    drawing, words_plan = plan(info["dim"], 1270, 2010)
    gfx.append(f'<g id="Půdorys">{drawing}</g>')
    txt.append(f'<g id="Popisky půdorysu">{words_plan}</g>')
    y = 2306
    lines = []
    for line in wrap(f"{SOURCES} {AI_NOTE}", 188):
        lines.append(text(50, y, line, 17, FOOT))
        y += 22
    txt.append(f'<g id="Patička">{"".join(lines)}</g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}" font-stretch="semi-condensed">'
            f'<g id="Grafika">{"".join(gfx)}</g><g id="Texty">{"".join(txt)}</g></svg>')


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from engine.infographics import for_vectorcraft, rasterize

    d, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    svg = poster(d)
    (out / "pantheon.svg").write_text(svg, encoding="utf-8")
    copy = out / f"pantheon-vectorcraft-{datetime.now():%Y%m%d-%H%M%S}.svg"
    copy.write_text(for_vectorcraft(svg), encoding="utf-8")
    for fmt in ("png", "pdf"):
        (out / f"pantheon.{fmt}").write_bytes(rasterize(svg, W, H, fmt))
    print(copy)
    print({p.name: p.stat().st_size for p in out.iterdir()})
    if "--knihovna" in sys.argv:
        engine = sys.argv[sys.argv.index("--knihovna") + 1]
        body = {"b64": base64.b64encode((out / "pantheon.png").read_bytes()).decode(), "name": "pantheon.png",
                "title": "Pantheon: infografika z modelu v Blenderu", "blender_render": True}
        req = urllib.request.Request(engine + "/api/v2/library/upload", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            print(r.read().decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
