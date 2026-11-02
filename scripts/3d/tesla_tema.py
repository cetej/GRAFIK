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


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    renders, figure, library = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    root = library / "tema" / QID
    obrazy = []
    for shot, name, labels in PICTURES:
        folder = root / "obrazy" / shot
        folder.mkdir(parents=True, exist_ok=True)
        body = json.loads((renders / shot / "body.json").read_text(encoding="utf-8"))
        with Image.open(renders / shot / "obraz.png") as im:
            picture, (dx, dy) = prepared(im)
        picture.save(folder / "obraz.png")
        points = {k: [u - dx, v - dy] for k, (u, v) in body["points"].items()}
        (folder / "body.json").write_text(json.dumps({"res": list(picture.size), "points": points}, ensure_ascii=False, indent=1), encoding="utf-8")
        obrazy.append({"id": shot, "nazev": name, "slozka": folder.relative_to(library).as_posix(), "popisky": labels})
    folder = root / "obrazy" / "postava"
    folder.mkdir(parents=True, exist_ok=True)
    with Image.open(figure) as im:
        rgba = im.convert("RGBA")
    picture = rgba.crop(rgba.getchannel("A").getbbox())
    picture.save(folder / "obraz.png")
    (folder / "body.json").write_text(json.dumps({"res": list(picture.size), "points": {}}), encoding="utf-8")
    obrazy.append({"id": "postava", "nazev": "Nikola Tesla, 3D figura", "kratce": "Figura", "slozka": folder.relative_to(library).as_posix(), "ai": FIGURE_AI})
    (root / "obrazy.json").write_text(json.dumps({"obrazy": obrazy}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(root, len(obrazy))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
