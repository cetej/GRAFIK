# The six Velsen scenes put together: a calm painted place + cut-out groups of people that nothing repaints, with their own floor shadow.
# So the gear stays what the studio picture shows (the operator accepted the figures, the repainted scenes were "přetažené").
#   python scripts/plakaty/velsen_skladba.py LIB OUT [--jen 3]    LIB = library/plakaty/velsen
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage as ndi

W, H = 1536, 936
VYBAVA = {"gladius": (0.19, 1800), "dyka": (0.135, 2400), "pugio": (0.14, 1800), "chochol": (0.11, 1800)}   # top of the render above the anchor (metres), pixels per metre
# the people's light: colour multiplied, contrast from the middle, a glow (x, y, radius as parts of the picture, rgb, strength)
LOOK = {
    1: ((0.98, 0.92, 0.84), 0.94, None),
    2: ((0.34, 0.42, 0.62), 0.9, (0.7, 0.62, 0.3, (255, 170, 90), 0.55)),
    3: ((0.93, 0.95, 0.98), 0.94, None),
    4: ((0.46, 0.44, 0.46), 0.95, (0.1, 0.32, 0.62, (255, 165, 90), 0.5)),
    5: ((0.68, 0.76, 0.88), 0.9, None),
    6: ((0.72, 0.69, 0.74), 0.93, None),
}
# (file, x of the group's middle, y of its feet, height, all as parts of the picture, flip); the boxes give back what stands in front of the people
LAYERS = {
    1: [("g1-s92.png", 0.5, 0.95, 0.76, False)],
    2: [("g2-s92.png", 0.5, 0.82, 0.72, False)],
    3: [("rady-s92.png", 0.3, 0.685, 0.27, False), ("rady-s92.png", 0.8, 0.685, 0.27, True),
        ("g3-s92.png", 0.62, 0.95, 0.68, False), ("centurion3-s102.png", 0.17, 0.985, 0.9, False)],
    4: [("g4-s92.png", 0.53, 0.97, 0.76, False)],
    5: [("g5-s91.png", 0.5, 0.95, 0.68, False)],
    6: [("g6-s91.png", 0.3, 0.9, 0.62, False)],
}
COVER = {2: [(0.283, 0.625, 0.735, 1.0)], 6: [(0.385, 0.66, 0.62, 0.98)]}
# per group picture: (model-yaw, x, y of the anchor in the picture's pixels, pixels per metre of that man, rotation in degrees, flip); "!" = only below the anchor, for a blade in a fist
GEAR = {
    "g3-s92.png": [("gladius-70", 190, 272, 345, -6, False), ("gladius-70", 688, 272, 345, -6, False), ("dyka-60", 338, 318, 345, 5, False), ("dyka-60", 824, 318, 345, 5, False)],
    "g4-s92.png": [("pugio-0!", 590, 76, 337, 12, False), ("dyka-35", 612, 342, 337, 6, False)],
}


def gear(fig: Image.Image, lib: Path, items) -> Image.Image:
    """Models on the man, each with a thin soft shadow on what it lies on. The anchor: sword and dagger at the mouth of the sheath, the crest at the top of the helmet."""
    out = fig.copy()
    for name, x, y, ppm, rot, flip in items:
        im = Image.open(lib / "vybava" / f"{name.rstrip('!')}.png").convert("RGBA")
        top, res = VYBAVA[name.split("-")[0]]
        k = ppm / res
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
        ax, ay = im.width / 2, top * ppm
        if name.endswith("!"):
            im.paste((0, 0, 0, 0), (0, 0, im.width, round(ay)))
        if flip:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        pad = Image.new("RGBA", (im.width * 3, im.height * 3), (0, 0, 0, 0))
        pad.alpha_composite(im, (im.width, im.height))
        turned = pad.rotate(rot, Image.BICUBIC, center=(im.width + ax, im.height + ay))
        at = (round(x - im.width - ax), round(y - im.height - ay))
        layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
        layer.paste(turned, at)
        sh = Image.new("RGBA", out.size, (18, 14, 10, 0))
        sh.putalpha(layer.getchannel("A").point(lambda v: int(v * 0.45)).filter(ImageFilter.GaussianBlur(max(1.5, ppm / 300))))
        offset = Image.new("RGBA", out.size, (0, 0, 0, 0))
        offset.paste(sh, (round(ppm / 200), round(ppm / 120)))
        # the shadow only falls on the man himself
        offset.putalpha(Image.fromarray(np.minimum(np.asarray(offset.getchannel("A")), np.asarray(out.getchannel("A")))))
        out.alpha_composite(offset)
        out.alpha_composite(layer)
    return out


def cut(src: Path, cache: Path) -> tuple[Image.Image, Image.Image]:
    """The group without its grey wall (u2net), and its own shadow on the grey floor as a black layer. The shadow is measured, not made up."""
    cache.mkdir(parents=True, exist_ok=True)
    fig, sh = cache / f"{src.stem}-vyrez.png", cache / f"{src.stem}-stin.png"
    if not fig.exists():
        from rembg import new_session, remove
        rgb = Image.open(src).convert("RGB")
        a = remove(rgb, session=new_session("u2net"), alpha_matting=True, alpha_matting_foreground_threshold=240, alpha_matting_background_threshold=12, alpha_matting_erode_size=6).getchannel("A")
        grey = np.asarray(rgb.convert("L"), dtype=np.float32)
        rows = np.median(np.concatenate((grey[:, :24], grey[:, -24:]), axis=1), axis=1)[:, None]
        dark = ndi.binary_opening(grey < rows * 0.55, iterations=2)
        solid = ndi.binary_fill_holes(dark | (np.asarray(a) > 128))
        keyed = np.where(ndi.binary_dilation(dark, iterations=1), 255, 0).astype(np.uint8)
        a = Image.fromarray(np.maximum(np.asarray(a), np.where(solid, keyed, 0)).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
        out = rgb.copy()
        out.putalpha(a)
        out.save(fig)
        mask = np.asarray(a.filter(ImageFilter.MaxFilter(5)), dtype=np.float32) / 255
        # the empty floor: the median of each row outside the people, smoothed
        floor = np.empty_like(grey)
        for y in range(grey.shape[0]):
            free = grey[y][mask[y] < 0.05]
            floor[y] = np.median(free) if free.size > 8 else np.nan
        ys = np.where(~np.isnan(floor[:, 0]))[0]
        floor = np.interp(np.arange(grey.shape[0]), ys, floor[ys, 0])[:, None]
        shade = np.clip(1 - grey / np.maximum(floor, 1), 0, 1)
        shade[: int(grey.shape[0] * 0.55)] = 0      # only on the floor
        dark = np.where(shade < 0.03, 0, shade) * (1 - mask)
        s = Image.new("RGBA", rgb.size, (20, 16, 12, 0))
        s.putalpha(Image.fromarray(np.uint8(np.clip(dark * 2.4, 0, 0.85) * 255)).filter(ImageFilter.GaussianBlur(2)))
        s.save(sh)
    return Image.open(fig), Image.open(sh)


def place(canvas: Image.Image, fig: Image.Image, shadow: Image.Image, x: float, y: float, h: float, flip: bool):
    box = fig.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    k = h * H / (box[3] - box[1])
    size = (round(fig.width * k), round(fig.height * k))
    f, s = fig.resize(size, Image.LANCZOS), shadow.resize(size, Image.LANCZOS)
    if flip:
        f, s = f.transpose(Image.FLIP_LEFT_RIGHT), s.transpose(Image.FLIP_LEFT_RIGHT)
        cx = (fig.width - (box[0] + box[2]) / 2) * k
    else:
        cx = (box[0] + box[2]) / 2 * k
    at = (round(x * W - cx), round(y * H - box[3] * k))
    canvas.alpha_composite(s, (max(at[0], 0), max(at[1], 0)), (max(-at[0], 0), max(-at[1], 0)))
    canvas.alpha_composite(f, (max(at[0], 0), max(at[1], 0)), (max(-at[0], 0), max(-at[1], 0)))


def look(people: Image.Image, n: int) -> Image.Image:
    """The light of the hour on the people; the place is already painted in it. No generator."""
    tint, contrast, glow = LOOK[n]
    rgba = np.asarray(people, dtype=np.float32) / 255
    a = rgba[..., :3]
    a = np.clip((a - 0.5) * contrast + 0.5, 0, 1) * np.array(tint, dtype=np.float32)
    if glow:
        gx, gy, r, rgb, st = glow
        yy, xx = np.mgrid[0:H, 0:W]
        d = np.exp(-(((xx / W - gx) ** 2 + ((yy / H - gy) * H / W) ** 2) / (r * r)))[..., None]
        a = a + a * d * st * np.array(rgb, dtype=np.float32) / 255 * 2.2
    return Image.fromarray(np.uint8(np.clip(np.dstack((a, rgba[..., 3])), 0, 1) * 255), "RGBA")


def main() -> int:
    lib, out = Path(sys.argv[1]), Path(sys.argv[2])
    only = [int(v) for v in sys.argv[sys.argv.index("--jen") + 1].split(",")] if "--jen" in sys.argv else sorted(LAYERS)
    out.mkdir(parents=True, exist_ok=True)
    for n in only:
        place_bg = Image.open(lib / "pozadi" / f"pozadi-{n}.png").convert("RGBA").resize((W, H), Image.LANCZOS)
        people = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for name, x, y, h, flip in LAYERS[n]:
            fig, shadow = cut(lib / "skupiny" / name, lib / "skupiny" / "vyrezy")
            place(people, gear(fig, lib, GEAR.get(name, [])), shadow, x, y, h, flip)
        canvas = place_bg.copy()
        canvas.alpha_composite(look(people, n))
        for x0, y0, x1, y1 in COVER.get(n, []):
            box = (round(x0 * W), round(y0 * H), round(x1 * W), round(y1 * H))
            canvas.paste(place_bg.crop(box), box)
        canvas.convert("RGB").save(out / f"scena-{n}.png")
        print(out / f"scena-{n}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
