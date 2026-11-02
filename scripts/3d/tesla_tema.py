# Own pictures of the topic Nikola Tesla for series of pages (engine/serie.py), free: library/tema/Q9036/obrazy.json and obrazy/<id>/obraz.png + body.json.
#   python scripts/3d/tesla_tema.py RENDERS POSTAVA.png LIBRARY        RENDERS: output of scripts/3d/tesla_render.py, POSTAVA: the accepted figure, library/plakaty/tesla/podklady/postava.png, LIBRARY: the Engine's library folder
# Each picture is cropped to the object and its shadow fades out before the frame, a hard cut would show on the page. Part names come from the accepted poster, scripts/plakaty/tesla_kopie.py.
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "shared")]

QID = "Q9036"
FADE = 220              # px of the render, shadow fades out towards the frame
MARGIN = 24
SOLID = 200             # alpha of the object itself, the contact shadow is below it
FIGURE_AI = "Hunyuan 3.1 Pro a FLUX 3 Klein"
SOURCE = {"vez": "vez-tema"}    # picture id -> render folder, where the page needs another render than the poster
SHAFT_M = 37.0
SOIL_M = 5.0            # the ground under the tower fades out within this depth
SHAFT_FADE_M = (9.0, 17.0)      # the shaft goes on below it and disappears here, the label gives the real depth
GROUND_SIDE_M = (-15.0, 48.0, 4.0)      # ground left and right of the tower fades out towards these x, metres from the axis
PICTURES = [
    ("motor", "Střídavý indukční motor, model", {"rotor": "Rotor", "civka0": "Cívka statoru", "svorky": "Svorky", "hridel": "Hřídel"}),
    ("civka", "Teslova cívka, model", {"vrchol": "Vrchol s výbojem", "sekundar": "Sekundár", "primar": "Primár", "jiskriste": "Jiskřiště"}),
    ("vez", "Věž Wardenclyffe v řezu, model", {"kopule": "Kupole", "vez": "Věž", "dilna": "Cihlová dílna", "sachta": "Šachta"}),
    ("turbina", "Teslova turbína, model", {"disky": "Hladké disky", "hridel": "Hřídel", "tryska": "Tryska", "kryt": "Kryt"}),
    ("elektrarna", "Vodní elektrárna v řezu, model", {"generator": "Generátor", "privadec": "Přivaděč", "hridel": "Hřídel", "turbina": "Turbína"}),
    ("prijimac", "Přijímač a telegrafní klíč, model", {"krabice": "Přijímač", "kl": "Telegrafní klíč"}),
    ("lod", "Loď na dálkové ovládání, model", {"lod": "Loď bez posádky"}),
]


def prepared(im: Image.Image) -> tuple[Image.Image, tuple[int, int]]:
    """Výřez na objekt se stínem; stín k okraji výřezu vybledne, objekt zůstane plný. Vrátí i posun souřadnic."""
    rgba = np.asarray(im.convert("RGBA"), dtype=np.float32)
    alpha = rgba[..., 3]
    ys, xs = np.nonzero(alpha > 25)
    x0, y0 = max(0, int(xs.min()) - MARGIN), max(0, int(ys.min()) - MARGIN)
    x1, y1 = min(im.width, int(xs.max()) + MARGIN), min(im.height, int(ys.max()) + MARGIN)
    crop = rgba[y0:y1, x0:x1].copy()
    h, w = crop.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    edge = np.clip(np.minimum(np.minimum(xx, w - 1 - xx), np.minimum(yy, h - 1 - yy)) / FADE, 0, 1)
    edge = edge * edge * (3 - 2 * edge)
    soft = crop[..., 3] < SOLID
    crop[..., 3] = np.where(soft, crop[..., 3] * edge, crop[..., 3])
    return Image.fromarray(crop.astype(np.uint8), "RGBA"), (x0, y0)


def smooth(v):
    v = np.clip(v, 0, 1)
    return v * v * (3 - 2 * v)


def tower_section(im: Image.Image, points: dict) -> tuple[Image.Image, tuple[int, int], dict]:
    """Hlavní je věž. Podloží je jen pás pod povrchem, který vybledne, šachta z něj pokračuje a ztrácí se. Vrátí obraz, posun souřadnic a body, které zůstaly vidět."""
    rgba = np.asarray(im.convert("RGBA"), dtype=np.float32).copy()
    axis, surface = points["pata"]
    metre = (points["dno"][1] - surface) / SHAFT_M
    yy, xx = np.mgrid[0:im.height, 0:im.width]
    depth, across = (yy - surface) / metre, (xx - axis) / metre
    left, right, fade = GROUND_SIDE_M
    soil = (1 - smooth(depth / SOIL_M)) * smooth(np.minimum(across - left, right - across) / fade)
    shaft = 1 - smooth((depth - SHAFT_FADE_M[0]) / (SHAFT_FADE_M[1] - SHAFT_FADE_M[0]))
    below = np.where(np.abs(across) < 2.4, np.maximum(soil, shaft), soil)
    rgba[..., 3] *= np.where(depth > -0.6, below, 1.0)
    ys, xs = np.nonzero(rgba[..., 3] > 12)
    x0, y0, x1, y1 = max(0, int(xs.min()) - MARGIN), max(0, int(ys.min()) - MARGIN), min(im.width, int(xs.max()) + MARGIN), min(im.height, int(ys.max()) + MARGIN)
    kept = dict(points)
    kept["sachta"] = [axis, surface + 7.0 * metre]
    kept = {k: v for k, v in kept.items() if v[1] < y1 and x0 <= v[0] < x1 and k != "zem"}
    return Image.fromarray(rgba[y0:y1, x0:x1].astype(np.uint8), "RGBA"), (x0, y0), kept


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    renders, figure, library = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    root = library / "tema" / QID
    obrazy = []
    for shot, name, labels in PICTURES:
        folder = root / "obrazy" / shot
        folder.mkdir(parents=True, exist_ok=True)
        source = renders / SOURCE.get(shot, shot)
        body = json.loads((source / "body.json").read_text(encoding="utf-8"))
        kept = body["points"]
        with Image.open(source / "obraz.png") as im:
            if shot == "vez":
                picture, (dx, dy), kept = tower_section(im, kept)
            else:
                picture, (dx, dy) = prepared(im)
        picture.save(folder / "obraz.png")
        points = {k: [u - dx, v - dy] for k, (u, v) in kept.items()}
        (folder / "body.json").write_text(json.dumps({"res": list(picture.size), "points": points}, ensure_ascii=False, indent=1), encoding="utf-8")
        obrazy.append({"id": shot, "nazev": name, "slozka": folder.relative_to(library).as_posix(), "popisky": labels})
    folder = root / "obrazy" / "postava"
    folder.mkdir(parents=True, exist_ok=True)
    with Image.open(figure) as im:
        rgba = im.convert("RGBA")
    picture = rgba.crop(rgba.getchannel("A").getbbox())
    picture.save(folder / "obraz.png")
    (folder / "body.json").write_text(json.dumps({"res": list(picture.size), "points": {}}), encoding="utf-8")
    obrazy.append({"id": "postava", "nazev": "Nikola Tesla, 3D figura", "kratce": "Figura", "druh": "osoba", "slozka": folder.relative_to(library).as_posix(), "ai": FIGURE_AI})
    (root / "obrazy.json").write_text(json.dumps({"obrazy": obrazy}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(root, len(obrazy))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
