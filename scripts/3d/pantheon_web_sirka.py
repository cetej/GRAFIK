# Pantheon for the web, landscape: one big picture, the facts on it, no other panels (operator 2026-11-02).
# Three levels: big figures on the things they measure, one concrete scale on the wall, a few short labels.
# Texts come from the panel document 20261101-202603-9914, nothing new. Render: lod_pantheon.py --shot rez_web, 0 USD.
#   python scripts/3d/pantheon_web_sirka.py           prints the document, nothing is sent
#   python scripts/3d/pantheon_web_sirka.py --poslat  a new document through the running Engine
import argparse
import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image

LIBRARY = Path("C:/Users/stock/Documents/000_NGM/GRAFIK/library")
SOURCE = LIBRARY / "infographics" / "20261101-202603-9914"
RENDER = LIBRARY / "plakaty" / "pantheon-web" / "rez2"
FOLDER = "plakaty/pantheon-web/rez3"
ENGINE = "http://127.0.0.1:8300/api/v2"

W, H = 1920, 1080
CROP = (120, 0, 1920, 1080)     # room on the right for the scale, the portico's stairs may leave the frame
BIG, NAME = 64, 40

SCALE_X = 1640                  # text of the concrete scale
SCALE = [
    ("1 350 kg/m³", ["tuf a pemza"], [19.0, 0.0, 36.0], 322),
    ("Kusy cihel", ["střední vrstva"], [25.5, 0.0, 27.0], 540),
    ("2 200 kg/m³", ["travertin", "v základu", "na jílu"], "zaklad", 770),
]


def trimmed() -> dict:
    """The render without the strip on the left, its points moved along. Layers stay, VectorCraft needs them."""
    out = LIBRARY / FOLDER
    out.mkdir(parents=True, exist_ok=True)
    for file in [RENDER / "rez.png", *RENDER.glob("vrstva-*.png")]:
        with Image.open(file) as im:
            im.crop(CROP).save(out / file.name)
    info = json.loads((RENDER / "body.json").read_text(encoding="utf-8"))
    x, y = CROP[0], CROP[1]
    info["res"] = [CROP[2] - x, CROP[3] - y]
    info["points"] = {k: [v[0] - x, v[1] - y] for k, v in info["points"].items()}
    info["origin"] = [info["origin"][0] - x, info["origin"][1] - y]
    info["kruh"] = [[p[0] - x, p[1] - y] for p in info["kruh"]]
    (out / "body.json").write_text(json.dumps(info), encoding="utf-8")
    return info


def labels() -> list[dict]:
    label = lambda text, small, kotva, pos, align: {"text": text, "small": small, "kotva": kotva, "pos": pos, "align": align, "size": NAME}
    out = [
        label("tloušťka kupole", ["celkem 4 535 t"], "vrchol_rez", [1560, 88], "left"),
        label("Okulus", ["asi 9 m, stále otevřený"], "okulus", [980, 6], "right"),
        label("140 kazet", ["ubírají méně", "než 5 % hmoty"], "kazeta_vlevo", [316, 196], "right"),
        label("průměr i výška", ["vejde se koule"], "pata_l", [316, 412], "right"),
        label("60 t", ["sloup z Egypta"], "sloup", [358, 520], "left"),
    ]
    for value, small, where, top in SCALE:
        out.append(label(value, small, where, [SCALE_X, top], "left"))
    return out


def top_drawing() -> dict:
    """What the labels cannot do: big figures, and an arrow up the wall so that the three labels read as one scale."""
    x = 1618
    top, bottom = 232, 1000
    big = lambda px, y, text, anchor: f'<text x="{px}" y="{y}" font-size="{BIG}" font-weight="700" text-anchor="{anchor}" fill="#dcb062">{text}</text>'
    head = lambda y, text: f'<text x="{x + 22}" y="{y}" font-size="36" font-weight="700" fill="#f1ede4">{text}</text>'
    return {"id": "udaje", "typ": "kresba", "poradi": 2, "nazev": "Velké údaje", "rect": [0, 0, W, H], "viewbox": [0, 0, W, H],
            "kresba": f'<path d="M{x} {bottom} L{x} {top + 16}" stroke="#dcb062" stroke-width="3" fill="none"/><path d="M{x - 11} {top + 20} L{x} {top} L{x + 11} {top + 20} Z" fill="#dcb062"/>',
            "texty": big(1560, 74, "6,4→1,2 m", "start") + big(316, 400, "43,3 m", "end") + head(258, "Čím výš,") + head(300, "tím lehčí")}


def fields() -> dict:
    source = json.loads((SOURCE / "info.json").read_text(encoding="utf-8"))
    original = next(p for p in source["panels"] if p["id"] == "hlavni")
    trimmed()
    return {
        "title": source["title"], "subtitle": source["subtitle"], "size": f"{W}x{H}", "template": source["template"], "accent": source["accent"], "sources": source["sources"],
        "nadpis": {"x": 40, "y": 100, "size": 92, "k": 1.0},
        "panels": [
            {"id": "hlavni", "typ": "obraz", "poradi": 1, "nazev": "Pantheon", "rect": [0, 0, CROP[2] - CROP[0], H], "zdroj": {"slozka": FOLDER}, "vrstvy": original["vrstvy"], "prekryvy": original["prekryvy"], "labels": labels()},
            top_drawing(),
        ],
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--poslat", action="store_true")
    args = parser.parse_args()
    body = fields()
    if not args.poslat:
        print(json.dumps(body, ensure_ascii=False, indent=1))
        return
    request = urllib.request.Request(f"{ENGINE}/infographics/panels", json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request) as response:
        doc = json.load(response)
    print(doc["id"], doc["size"])


if __name__ == "__main__":
    main()
