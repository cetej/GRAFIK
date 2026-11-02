# The infographic of the well of Velsen: one tall section after the book's fig. 2.1 in 3D, labels at its side; the bones with the stabs. Text is vector, layers for VectorCraft.
# Facts with pages: docs/spikes/2026-11-01-velsen.md. Models: scripts/3d/velsen_studna.py, velsen_kostra.py. The overlay on the book's section: velsen_srovnani.py.
#   python scripts/plakaty/velsen_studna_stranka.py LIB OUT [--knihovna http://127.0.0.1:8300]
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).parent))
from sazba import FONT, crop_alpha, group, image_tag, para, text, write_poster  # noqa: E402

W, H = 1800, 2400
BG, GOLD, WHITE, DIM = "#340d11", "#dcb66e", "#f0e8da", "#b9a99a"
HEAD, BODY = 30, 26
SECTION = 36
CLOAK = "skupiny/plast-s403-cut.png"


def man(lib: Path) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """The prepared figure as it is: the FLUX picture without its grey wall, a little of the water's colour over it. Returns the RGBA and the frame of the figure."""
    rgb = Image.open(lib / "skupiny/sedici-s123.png").convert("RGB")
    alpha = Image.open(lib / "render/muz/maska.png").convert("L").filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    a = np.asarray(rgb, dtype=np.float32) / 255
    a = np.clip((a - 0.5) * 0.92 + 0.5, 0, 1) * np.array((0.9, 0.95, 0.9), dtype=np.float32)
    im = Image.fromarray(np.uint8(a * 255))
    im.putalpha(alpha)
    return im, alpha.point(lambda v: 255 if v > 32 else 0).getbbox()


def compose(lib: Path, name: str) -> tuple[Image.Image, dict, tuple[float, float, float]]:
    """Back of the well, the man, the stake and the stones in front of him. Returns also the man's place: x, y of the corner of his picture and its scale."""
    d = lib / "render" / name
    back = Image.open(d / "zadni.png").convert("RGBA")
    front = Image.open(d / "predni.png").convert("RGBA")
    data = json.loads((d / "body.json").read_text(encoding="utf-8"))
    points = data["points"]
    fig, frame = man(lib)
    (x0, y0), (_, y1) = points["muz0"], points["muz1"]
    k = (y0 - y1) / (frame[3] - frame[1])
    size = (round(fig.width * k), round(fig.height * k))
    place = (x0 + 0.02 * (y0 - y1) / 1.23 - (frame[0] + frame[2]) / 2 * k, y0 - frame[3] * k)
    layer = Image.new("RGBA", back.size, (0, 0, 0, 0))
    layer.paste(fig.resize(size, Image.LANCZOS), (round(place[0]), round(place[1])))
    out = back.copy()
    inside = Image.new("L", back.size, 0)
    ImageDraw.Draw(inside).polygon([tuple(q) for q in data["sud2"]], fill=255)
    shade = ImageChops.multiply(layer.getchannel("A").filter(ImageFilter.GaussianBlur(back.height * 0.03)).point(lambda v: min(255, round(v * 1.5))), inside)
    out.paste(Image.new("RGBA", back.size, (6, 8, 5, 255)), (0, 0), shade)
    out.putalpha(back.getchannel("A"))
    cloak, _ = crop_alpha(Image.open(lib / CLOAK).convert("RGBA"))
    (cx0, cy0), (cx1, cy1) = points["plast0"], points["plast1"]
    scaled = cloak.resize((round(cx1 - cx0), round(cy0 - cy1)), Image.LANCZOS)
    tint = np.asarray(scaled, dtype=np.float32).copy()
    tint[..., :3] *= (0.62, 0.66, 0.62)
    piece = Image.new("RGBA", back.size, (0, 0, 0, 0))
    piece.paste(Image.fromarray(np.uint8(tint), "RGBA"), (round(cx0), round(cy1)))
    piece.putalpha(ImageChops.multiply(piece.getchannel("A"), inside))
    out.alpha_composite(piece)
    out.alpha_composite(layer)
    out.alpha_composite(front)
    return out, points, (place[0], place[1], k)


def torn(im: Image.Image, z_start: float) -> Image.Image:
    """The block frays at the sides and the bottom below z_start (a share of its height), as in the drawing; the top stays cut straight."""
    a = np.asarray(im.getchannel("A"), dtype=np.float32) / 255
    h, w = a.shape
    rng = np.random.default_rng(1977)

    def noise(cell):
        small = Image.fromarray(np.uint8(rng.random((h // cell + 2, w // cell + 2)) * 255))
        return np.asarray(small.resize((w, h), Image.BICUBIC), dtype=np.float32) / 255 - 0.5

    wob = noise(70) * 1.6 + noise(24) * 0.9 + noise(8) * 0.5
    row = np.arange(h, dtype=np.float32) / h
    amp = np.clip((row - z_start) / (1 - z_start), 0, 1) ** 0.6 * 42
    yy, xx = np.mgrid[0:h, 0:w]
    opaque = a > 0.5
    rows = np.where(opaque.any(axis=1))[0]
    mid = opaque[int(h * 0.6)]
    x0, x1, y1 = np.where(mid)[0][0], np.where(mid)[0][-1], rows[-1]
    edge = np.minimum(np.minimum(xx - x0, x1 - xx), y1 - yy).astype(np.float32)
    keep = edge > amp[:, None] * (0.55 + wob)
    # the block only: never the head above the surface
    keep[: int(h * z_start)] = True
    out = im.copy()
    out.putalpha(Image.fromarray(np.uint8(a * keep * 255)).filter(ImageFilter.GaussianBlur(0.7)))
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    lib, out = Path(sys.argv[1]), Path(sys.argv[2])
    knihovna = sys.argv[sys.argv.index("--knihovna") + 1] if "--knihovna" in sys.argv else None

    # the well, left, the whole height of the page
    raw, body, _ = compose(lib, "celek")
    block, (ox, oy) = crop_alpha(torn(raw, 0.42))
    bk = 2200 / raw.height
    bw, bh = block.width * bk, block.height * bk
    bx, by = 30, 30

    def at(name):
        return bx + (body[name][0] - ox) * bk, by + (body[name][1] - oy) * bk

    grafika = group("Studna", image_tag(block, bx, by, bw, bh, "PNG"))

    # the labels stand well clear of the block, on the height of their thing: a heading and at most one line
    lx = bx + bw + 62

    def tag(name, head, line="", via=None):
        ax, ay = at(name)
        y = ay if via is None else via
        s = text(lx, y + 10, head, HEAD, GOLD, 600) + text(lx, y + 46, line, BODY, WHITE)
        s += f'<polyline points="{ax:.1f},{ay:.1f} {ax:.1f},{y:.1f} {lx - 12:.1f},{y:.1f}" fill="none" stroke="{GOLD}" stroke-width="1.5"/><circle cx="{ax:.1f}" cy="{ay:.1f}" r="4" fill="{GOLD}"/>'
        return group(head, s)

    t = group("Titulek", text(lx, 134, "MUŽ NA DNĚ STUDNY", 118, GOLD, 700)
              + text(lx, 192, "Římská pevnost Velsen, dnešní Nizozemsko, léta 28–38 n. l.", 34, WHITE)
              + text(lx, 238, "Někdo ho spustil pod vodu a zatížil, aby nevyplaval. Kdo a proč, se neví.", 34, WHITE))
    t += tag("hladina", "Nejméně metr vody nad hlavou", "Hladina asi −0,5 až −0,75 m")
    t += tag("sud1", "Tři sudy nad sebou", "Horní je odhad, zbyly z něj zlomky obruče")
    t += tag("kul", "Kůl asi 1,5 m, šikmo k hrudi")
    t += tag("kameny", "60 kg žernovů, 19 kg kamenů", "Aby tělo nevyplavalo", via=at("kameny_nad")[1])
    t += tag("muz", "Voják, 184–191 cm, asi 25 let", "Bez zbroje, vešel se jen skrčený")
    t += tag("bota", "Jediná bota", "Levá caliga", via=at("bota_pod")[1])
    t += tag("sud3", "Spodní sud plný písku", "Tělo proto nekleslo níž")

    # the depth on the block's left edge, a metre bar beside it
    scale = ""
    for name, value in (("povrch", "0 m"), ("ret", "−2,41 m"), ("floor", "−4,0 m"), ("dno", "−5,8 m")):
        ax, ay = at(name)
        scale += f'<line x1="{bx + 4:.1f}" y1="{ay:.1f}" x2="{bx + 82:.1f}" y2="{ay:.1f}" stroke="{WHITE}" stroke-width="1.5"/>' + text(bx + 6, ay - 7, value, 23, WHITE, 500)
    (mx, my0), (_, my1) = at("metr0"), at("metr1")
    scale += f'<polyline points="{mx + 7:.1f},{my0:.1f} {mx:.1f},{my0:.1f} {mx:.1f},{my1:.1f} {mx + 7:.1f},{my1:.1f}" fill="none" stroke="{WHITE}" stroke-width="2"/>' + text(mx + 13, (my0 + my1) / 2 + 8, "1 m", 23, WHITE, 500)
    t += group("Hloubka", scale)

    # the right column: one pelvis with all the wounds
    rx = 1205
    t += group("Kostra nadpis", text(rx, 370, "KAM HO BODALI", SECTION, GOLD, 600)
               + "".join(text(rx, 416 + i * 34, line, BODY, WHITE) for i, line in enumerate(("Úhly ran jsou podobné, muž se nejspíš nehýbal:", "spoutaný, držený, v bezvědomí, nebo už mrtvý.", "Forenzní specialisté v tom vidí spíš ponížení než boj."))))
    d = lib / "kostra/hotovo"
    bones = Image.open(d / "panev.png").convert("RGBA")
    ghost = Image.open(d / "panev-duch.png").convert("RGBA")
    ghost.putalpha(ghost.getchannel("A").point(lambda v: round(v * 0.62)))
    bones.alpha_composite(ghost)
    marks = json.loads((d / "body.json").read_text(encoding="utf-8"))["panev"]
    bones, (kx, ky) = crop_alpha(bones)
    zoom, vy = 0.885, 810
    vw, vh = bones.width * zoom, bones.height * zoom
    vx = 1775 - vw
    grafika += group("Kostra", image_tag(bones, vx, vy, vw, vh, "PNG"))

    def on_bones(name):
        return vx + (marks[name][0] - kx) * zoom, vy + (marks[name][1] - ky) * zoom

    def callout(x, name, head, lines):
        ax, ay = on_bones(name)
        y0 = 660
        s = text(x, y0, head, HEAD, GOLD, 600) + "".join(text(x, y0 + 36 + i * 32, line, BODY, WHITE) for i, line in enumerate(lines))
        top = y0 + 36 + (len(lines) - 1) * 32 + 12
        s += f'<line x1="{ax:.1f}" y1="{top:.1f}" x2="{ax:.1f}" y2="{ay:.1f}" stroke="{GOLD}" stroke-width="1.5"/><circle cx="{ax:.1f}" cy="{ay:.1f}" r="4" fill="{GOLD}"/>'
        return group(head, s)

    t += callout(rx, "pravy", "Pravá strana", ("3 větší a 4 menší zepředu",))
    t += callout(1530, "levy", "Levá strana", ("Nejméně 14 zezadu", "Čepel v největším z nich"))

    t += group("Zdroj", para(bx, 2286, "Zdroj: Driessen, van Driel-Murray (eds.), Victims of Violence from the early Roman fort Velsen 1, Sidestone 2026, CC BY-NC-ND 4.0: řez a muž podle kreseb F. Marschalla (obr. 2.1, 11.1), vpichy podle skenu pánve. "
                                  "Studna a kosti: 3D model, render v Blenderu, bez AI. Postava muže a plášť: FLUX 3 Klein (AI) podle obr. 11.1. Kosti: BodyParts3D, © 2008 Life Science Integrated Database Center, CC BY-SA 2.1 JP, obecný model, ne kosti oběti. "
                                  "Nadzemní část a horní sud jsou rekonstrukce, ne nález. Vpichy zezadu jsou zakreslené přes kost. Výšky jsou vůči hladině moře (NAP).", 20, DIM, 225, 1.3))

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}" font-stretch="semi-condensed">'
           f'<rect id="Pozadí" width="{W}" height="{H}" fill="{BG}"/>' + group("Grafika", grafika) + group("Texty", t) + "</svg>")
    write_poster(svg, out, "velsen-studna", W, H, "Muž na dně studny", knihovna, True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
