# Infographic of the Pantheon from the render of scripts/3d/lod_pantheon.py (free):
#   python scripts/3d/pantheon_infografika.py kompozit DIR     rez.png + background + exact sphere = hero.png, no text
#   python scripts/3d/pantheon_infografika.py doc DIR [--id ID [--novy-podklad]] [--engine http://127.0.0.1:8300]
# doc writes the document (without --id: uploads hero.png as a new one); labels sit on points of the model, so they
# stay in place when the camera changes. Export it in the Studio editor (one renderer, docs/infografiky-zasady.md).
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
SUBTITLE = "Největší kupole z nevyztuženého betonu. Řím, asi 114–126 n. l."
FACTS = [
    ("43,3 m", "průměr i výška"),
    ("6,4 → 1,2 m", "tloušťka kupole"),
    ("4 535 t", "hmotnost kupole"),
    ("60 t", "jeden sloup z Egypta"),
]
# where it points, name, explanation, label position on the 1920 x 1080 canvas, side the leader comes from.
# Where: a point from body.json, or (x, y, z) in metres on the model. Name + explanation at most 40 characters (editor check).
LABELS = [
    ("okulus", "Okulus", "asi 9 m, stále otevřený", (1245, 38), "left"),
    ((15.6, 0, 38.4), "Tuf a pemza", "asi 1 350 kg/m³", (1455, 122), "left"),
    ((-10.36, 13.26, 35.27), "140 kazet", "ubírají méně než 5 % hmoty", (808, 160), "right"),
    ("stupne", "7 prstenců", "přitěžují patu kupole", (1570, 282), "left"),
    ((25.5, 0, 27.0), "Kusy cihel", "střední vrstva betonu", (1570, 345), "left"),
    ("pata_p", "Koule 43,3 m", "vejde se přesně", (1570, 420), "left"),
    ("komora", "Dutiny ve zdi", "tíhu nesou cihlové oblouky", (1570, 495), "left"),
    ("zaklad", "Travertin v základu", "asi 2 200 kg/m³", (1570, 832), "left"),
    ("podlaha", "Když prší", "voda steče do odpadů", (1198, 812), "left"),
    ("napis", "Agrippův nápis", "Hadrián ho ponechal", (340, 545), "right"),
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
    vb_w, vb_h, s = 730.0, 176.0, 2.9
    ox, oy = vb_w - 28.5 * s, 86.0      # the drawing keeps to the right end of the inset box, the rest stays see-through
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
    out.append(f'<line x1="{x(x_wall + 1.4)}" y1="{y(0)}" x2="{x(r_o + 1)}" y2="{y(0)}" stroke="{ACCENT}" stroke-width="2.4" stroke-dasharray="8 5"/>')
    left, bar = x(x_col) - 3, 20 * s
    out.append(f'<line x1="{left:g}" y1="{vb_h - 3:g}" x2="{left + bar:g}" y2="{vb_h - 3:g}" stroke="#f1ede4" stroke-width="2"/>')
    out.append(f'<text x="{left:g}" y="{vb_h - 9:g}" fill="#f1ede4" font-size="17">20 m</text>')
    out.append(f'<text x="{x(0)}" y="{y(0) - 6}" fill="{ACCENT}" font-size="17" font-weight="700" text-anchor="middle">řez</text>')
    out.append("</svg>")
    return "".join(out)


def call(engine: str, method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(engine + path, method=method, data=None if body is None else json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def canvas_point(info: dict, where) -> tuple[float, float]:
    """Canvas position of a named point, or of metres on the model: orthographic, so it is linear in x, y, z."""
    p = info["points"]
    if isinstance(where, str):
        return tuple(p[where])
    x, y, z = where
    o, right, top = p["podlaha_stred"], p["pata_p"], p["vrchol_koule"]
    r = info["dim"]["inner_d"] / 2
    ux, vx = (right[0] - p["pata_l"][0]) / (2 * r), (right[1] - p["pata_l"][1]) / (2 * r)   # per metre along x
    vz = (top[1] - o[1]) / (2 * r)                                                         # per metre up
    # the axes x and y lie square on the ground: y turns by the same angle as x, with the tilt of the camera in v
    px_m = info["m_px"]
    cos_x = ux / px_m
    sin_x = math.sqrt(max(0.0, 1 - cos_x ** 2))
    tilt = vx / (px_m * sin_x) if sin_x else 0.0
    return o[0] + ux * x - px_m * sin_x * y, o[1] + vx * x + px_m * cos_x * tilt * y + vz * z


def document(d: Path, engine: str, info_id: str | None, new_base: bool) -> dict:
    info = json.loads((d / "body.json").read_text(encoding="utf-8"))
    w, h = info["res"]
    if info_id:
        doc = call(engine, "GET", f"/api/v2/infographics/{info_id}")
    if not info_id or new_base:
        with Image.open(d / "hero.png") as im:
            if im.size != (1920, 1080):
                raise SystemExit(f"hero.png je {im.size}, editor čeká 1920 x 1080")
        b64 = base64.b64encode((d / "hero.png").read_bytes()).decode()
        new = call(engine, "POST", "/api/v2/infographics/upload", {"b64": b64, "name": "pantheon-rez-blender.png", "blender_render": True})
        if info_id:   # the upload only brought the new base image
            doc["base"] = new["base"]
            call(engine, "DELETE", f"/api/v2/infographics/{new['id']}")
        else:
            doc = new
    labels = []
    for where, text, small, pos, align in LABELS:
        ax, ay = canvas_point(info, where)
        labels.append({"text": text, "small": small, "anchor": [round(ax / w * 1000), round(ay / h * 1000)],
                       "pos": [round(pos[0] / 1920 * 1000, 1), round(pos[1] / 1080 * 1000, 1)], "align": align})
    doc.update(title=TITLE, subtitle=SUBTITLE, template="dark", layout="pruh", size="1920x1080", accent=ACCENT, labels=labels,
               facts=[{"value": v, "text": t} for v, t in FACTS], sources=SOURCES,
               schema={"title": "Půdorys: 8 pilířů, 7 výklenků a vchod", "svg": plan_svg(info["dim"])})
    return call(engine, "PUT", f"/api/v2/infographics/{doc['id']}", doc)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("krok", choices=("kompozit", "doc"))
    ap.add_argument("dir", type=Path)
    ap.add_argument("--id", help="next version of an existing document")
    ap.add_argument("--novy-podklad", action="store_true", help="with --id: upload hero.png again")
    ap.add_argument("--engine", default="http://127.0.0.1:8300")
    a = ap.parse_args()
    if a.krok == "kompozit":
        print(kompozit(a.dir))
        print(kompozit(a.dir, koule=False, name="bez-koule.png"))
    else:
        doc = document(a.dir, a.engine, a.id, a.novy_podklad)
        print(doc["id"], doc["base"], doc["ai_note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
