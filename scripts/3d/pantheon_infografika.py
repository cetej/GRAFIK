# Infographic of the Pantheon from the render of scripts/3d/lod_pantheon.py (free):
#   python scripts/3d/pantheon_infografika.py kompozit DIR     rez.png + background + exact sphere = hero.png, no text
#   python scripts/3d/pantheon_infografika.py doc DIR [--id ID] [--engine http://127.0.0.1:8300]
# doc uploads hero.png as a new base image and writes the document; labels sit on the points from body.json, so they
# stay on the model when the camera changes. Export it in the Studio editor (one renderer, docs/infografiky-zasady.md).
import argparse
import base64
import json
import math
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

BG = (29, 37, 50)        # template "dark" of the editor
GLOW = (58, 68, 86)
LINE = (255, 246, 222)   # light line with a dark under-stroke: holds on the warm room and on the dark background
UNDER = (15, 20, 30)
WALL = "#d9cdb4"
ACCENT = "#dcb062"

TITLE = "Pantheon"
SUBTITLE = "Největší kupole z nevyztuženého betonu na světě. Řím, stavba asi 114–126 n. l."
FACTS = [
    ("43,3 m", "průměr i výška rotundy"),
    ("6,4 → 1,2 m", "tloušťka kupole od paty k okulu"),
    ("4 535 t", "hmotnost kupole"),
    ("60 t", "jeden žulový sloup z Egypta"),
]
# point from body.json, name, explanation, label position on the 1920 x 1080 canvas, side the leader comes from
LABELS = [
    ("okulus", "Okulus", "asi 9 m, jediné okno, stále otevřené", (1010, 58), "right"),
    ("vrchol_rez", "Nahoře tuf a pemza", "nejlehčí beton, asi 1 350 kg/m³", (1345, 58), "left"),
    ("kazeta_vlevo", "140 kazet", "5 řad po 28, ubírají méně než 5 % hmoty", (760, 196), "right"),
    ("stupne", "7 prstenců", "přitěžují patu kupole", (1510, 322), "left"),
    ("stred_rez", "Uprostřed kusy cihel", "střední vrstva, lehčí než základ", (1510, 402), "left"),
    ("pata_p", "Koule 43,3 m", "vejde se přesně: výška = průměr", (1510, 482), "left"),
    ("komora", "Dutiny ve zdi", "šetří hmotu, tíhu nesou cihlové oblouky", (1510, 562), "left"),
    ("zaklad", "Dole travertin", "asi 2 200 kg/m³, základ 4,7 m na jílu", (1510, 880), "left"),
    ("podlaha", "Když prší", "vypouklá podlaha svede vodu do odpadů", (1050, 852), "left"),
    ("napis", "Cizí jméno na průčelí", "Agrippa; Hadrián jeho nápis ponechal", (420, 420), "right"),
]
SOURCES = ("Moore, Constructor 9/2002; Mark a Hutchison, Art Bulletin 1986 (podle citací); Wikipedia: Pantheon, Rome; "
           "2nd-century Roman domes; Roman concrete (Lancaster). Okulus 8,2–9,1 m podle zdroje. Hranice vrstev betonu jsou "
           "schematické, zrno zvětšené, rozměry bez zdroje označené ve skriptu jako odhad.")


def kompozit(d: Path, koule: bool = True, name: str = "hero.png") -> Path:
    rez = Image.open(d / "rez.png").convert("RGBA")
    info = json.loads((d / "body.json").read_text(encoding="utf-8"))
    w, h = rez.size
    k, ss = w / info["res"][0], 3
    # a faint glow behind the building, so the background is not one flat band
    mask = Image.new("L", (w // 4, h // 4), 0)
    draw = ImageDraw.Draw(mask)
    cx, cy = (v * k / 4 for v in info["points"]["stred_koule"])
    for r in range(60, 0, -1):
        rad = r * w / 400
        draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=int((60 - r) * 0.42))
    out = Image.composite(Image.new("RGBA", (w, h), GLOW + (255,)), Image.new("RGBA", (w, h), BG + (255,)),
                          mask.resize((w, h), Image.Resampling.BICUBIC))
    out = Image.alpha_composite(out, rez)
    if koule:
        over = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
        dr = ImageDraw.Draw(over)
        u = w / 1920 * ss
        pts = [(x * k * ss, y * k * ss) for x, y in info["kruh"]]
        n = len(pts)
        for col, width in ((UNDER + (170,), 5.8), (LINE + (255,), 2.6)):   # dashed: 3 degrees on, 3 off
            for i in range(0, n, 6):
                dr.line([pts[(i + j) % n] for j in range(4)], fill=col, width=round(width * u), joint="curve")

        def dimension(a, b):
            (ax, ay), (bx, by) = [(p[0] * k * ss, p[1] * k * ss) for p in (a, b)]
            ang = math.atan2(by - ay, bx - ax)
            for col, width in ((UNDER + (150,), 4.4), (LINE + (240,), 1.8)):
                dr.line([(ax, ay), (bx, by)], fill=col, width=round(width * u))
                for (px, py), sign in (((ax, ay), 1), ((bx, by), -1)):
                    for da in (0.42, -0.42):
                        dr.line([(px, py), (px + sign * 11 * u * math.cos(ang + da), py + sign * 11 * u * math.sin(ang + da))],
                                fill=col, width=round(width * u))

        p = info["points"]
        dimension(p["pata_l"], p["pata_p"])
        dimension(p["podlaha_stred"], p["vrchol_koule"])
        out = Image.alpha_composite(out, over.resize((w, h), Image.Resampling.LANCZOS))
    path = d / name
    out.convert("RGB").save(path)
    return path


def plan_svg(dim: dict) -> str:
    """Floor plan from the same numbers as the model: what the section does not show, eight piers and where the cut runs."""
    vb_w, vb_h, s = 730.0, 238.0, 3.55
    ox, oy = vb_w - 28.5 * s, 112.0     # the drawing keeps to the right end of the inset box, the rest stays see-through
    x = lambda m: round(ox + m * s, 1)
    y = lambda m: round(oy + m * s, 1)
    r_i, wall = dim["inner_d"] / 2, dim["wall"]
    r_o = r_i + wall
    e_w, e_d = dim["exedra_w"] / 2, dim["exedra_d"]
    x_wall = -(r_o + dim["block_d"])
    x_col = x_wall - dim["portico_d"]
    w = dim["portico_w"] / 2
    bg = "#%02x%02x%02x" % BG
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{vb_w:g}" height="{vb_h:g}" viewBox="0 0 {vb_w:g} {vb_h:g}">']
    out.append(f'<rect x="{x(x_wall)}" y="{y(-w - 1)}" width="{round((-r_i + 2 - x_wall) * s, 1)}" height="{round((2 * w + 2) * s, 1)}" fill="{WALL}"/>')
    out.append(f'<circle cx="{x(0)}" cy="{y(0)}" r="{round(r_o * s, 1)}" fill="{WALL}"/>')
    out.append(f'<circle cx="{x(0)}" cy="{y(0)}" r="{round(r_i * s, 1)}" fill="{bg}"/>')
    out.append(f'<rect x="{x(x_wall - 0.5)}" y="{y(-4)}" width="{round((-r_i - x_wall + 1) * s, 1)}" height="{round(8 * s, 1)}" fill="{bg}"/>')
    for deg, kind in ((0, "semi"), (45, "rect"), (90, "semi"), (135, "rect"), (-45, "rect"), (-90, "semi"), (-135, "rect")):
        rot = f'rotate({deg} {x(0)} {y(0)})'
        if kind == "rect":
            out.append(f'<rect x="{x(r_i - 0.6)}" y="{y(-e_w)}" width="{round((e_d + 0.6) * s, 1)}" height="{round(2 * e_w * s, 1)}" fill="{bg}" transform="{rot}"/>')
        else:
            out.append(f'<path d="M{x(r_i - 0.6)} {y(-e_w)} L{x(r_i + e_d - e_w)} {y(-e_w)} A{round(e_w * s, 1)} {round(e_w * s, 1)} 0 0 1 {x(r_i + e_d - e_w)} {y(e_w)} '
                       f'L{x(r_i - 0.6)} {y(e_w)} Z" fill="{bg}" transform="{rot}"/>')
    ys = [-w + dim["portico_w"] * i / 7 for i in range(8)]
    cols = [(x_col, c) for c in ys] + [(x_col + d, ys[i]) for d in (4.8, 9.6) for i in (0, 2, 5, 7)]
    for cx, cy in cols:
        out.append(f'<circle cx="{x(cx)}" cy="{y(cy)}" r="{round(dim["col_d"] / 2 * s, 1)}" fill="{WALL}"/>')
    # the section line runs through the rotunda and the block, the portico stays whole
    cut = x_wall + 1.4
    out.append(f'<line x1="{x(cut)}" y1="{y(0)}" x2="{x(r_o + 2)}" y2="{y(0)}" stroke="{ACCENT}" stroke-width="2.2" stroke-dasharray="8 5"/>')
    bar = 20 * s
    left = x(x_col) - 150
    out.append(f'<text x="{left:g}" y="{y(-16)}" fill="#f1ede4" font-size="19" text-anchor="start">8 pilířů,</text>')
    out.append(f'<text x="{left:g}" y="{y(-16) + 23}" fill="#f1ede4" font-size="19">mezi nimi 7 výklenků</text>')
    out.append(f'<text x="{left:g}" y="{y(-16) + 46}" fill="#f1ede4" font-size="19">a vchod</text>')
    out.append(f'<text x="{left:g}" y="{y(-16) + 82}" fill="{ACCENT}" font-size="19" font-weight="700">čárkovaně: řez</text>')
    out.append(f'<line x1="{left:g}" y1="{y(19)}" x2="{left + bar:g}" y2="{y(19)}" stroke="#f1ede4" stroke-width="2"/>')
    out.append(f'<text x="{left:g}" y="{y(19) - 7}" fill="#f1ede4" font-size="17">20 m</text>')
    out.append("</svg>")
    return "".join(out)


def call(engine: str, method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(engine + path, method=method, data=None if body is None else json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def document(d: Path, engine: str, info_id: str | None) -> dict:
    info = json.loads((d / "body.json").read_text(encoding="utf-8"))
    w, h = info["res"]
    with Image.open(d / "hero.png") as im:
        if im.size != (1920, 1080):
            raise SystemExit(f"hero.png je {im.size}, editor čeká 1920 x 1080")
    b64 = base64.b64encode((d / "hero.png").read_bytes()).decode()
    new = call(engine, "POST", "/api/v2/infographics/upload", {"b64": b64, "name": "pantheon-rez-blender.png", "blender_render": True})
    if info_id:   # next version of the same document, the upload only brought the new base image
        doc = call(engine, "GET", f"/api/v2/infographics/{info_id}")
        doc["base"] = new["base"]
        call(engine, "DELETE", f"/api/v2/infographics/{new['id']}")
    else:
        doc = new
    labels = []
    for key, text, small, pos, align in LABELS:
        ax, ay = info["points"][key]
        labels.append({"text": text, "small": small, "anchor": [round(ax / w * 1000), round(ay / h * 1000)],
                       "pos": [round(pos[0] / 1920 * 1000, 1), round(pos[1] / 1080 * 1000, 1)], "align": align})
    doc.update(title=TITLE, subtitle=SUBTITLE, template="dark", layout="pruh", size="1920x1080", accent=ACCENT, labels=labels,
               facts=[{"value": v, "text": t} for v, t in FACTS], sources=SOURCES,
               schema={"title": "Půdorys", "svg": plan_svg(info["dim"])})
    return call(engine, "PUT", f"/api/v2/infographics/{doc['id']}", doc)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("krok", choices=("kompozit", "doc"))
    ap.add_argument("dir", type=Path)
    ap.add_argument("--id", help="next version of an existing document")
    ap.add_argument("--engine", default="http://127.0.0.1:8300")
    a = ap.parse_args()
    if a.krok == "kompozit":
        print(kompozit(a.dir))
        print(kompozit(a.dir, koule=False, name="bez-koule.png"))
    else:
        doc = document(a.dir, a.engine, a.id)
        print(doc["id"], doc["base"], doc["ai_note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
