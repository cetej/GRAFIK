# Maps for the 3D model of the dagger from the Velsen well, from the reconstruction drawing in the book (fig. 4.2, N. Verstraaten, after Morel and Bosman 1989; scale bar 21 px/cm).
# Silver where the drawing is light, dark niello where it is inked (book p. 63: silver, niello, red and yellow enamel); enamel only where the book names it: the rosettes in alternating red and yellow triangles (p. 65), the pelta red.
#   python scripts/plakaty/velsen_dyka_mapy.py POCHVA_REKONSTRUKCE.png OUT_DIR
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as ndi


def main() -> int:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("L")
    w, h = im.size
    d = ImageDraw.Draw(im)
    # away with the belt, the frogs and the scale bar: only the dagger stays
    d.rectangle((0, 0, 214, 283), fill=255)
    d.rectangle((366, 0, w, 283), fill=255)
    d.rectangle((0, 0, 240, 10), fill=255)
    d.rectangle((425, 283, w, h), fill=255)
    d.rectangle((214, 88, 264, 244), fill=255)      # the belt behind the grip
    d.rectangle((316, 88, 366, 244), fill=255)
    d.polygon([(401, 278), (430, 278), (430, 304), (409, 298)], fill=255)
    d.polygon([(214, 283), (214, 262), (150, 262), (180, 300), (205, 290)], fill=255)
    d.polygon([(366, 283), (366, 262), (430, 262), (402, 300), (378, 290)], fill=255)
    a = np.asarray(im, dtype=np.float32) / 255
    # the silhouette: everything the white background cannot reach from outside
    open_bg = ndi.binary_erosion(a > 0.86, iterations=2)     # thin outlines have gaps, the background must not leak into the grip
    labels, _ = ndi.label(open_bg)
    outside = ndi.binary_dilation(labels == labels[2, 2], iterations=2)
    solid = ndi.binary_opening(~outside, iterations=1)
    labels, n = ndi.label(solid)
    biggest = 1 + int(np.argmax(ndi.sum(solid, labels, range(1, n + 1))))
    solid = ndi.binary_fill_holes(labels == biggest)
    # the hilt is drawn with hair lines the flood leaks through: its outline by hand, measured on the drawing
    hilt = Image.new("L", (w, h), 0)
    dh = ImageDraw.Draw(hilt)
    dh.polygon([(247, 25), (330, 25), (330, 50), (322, 70), (306, 88), (306, 137), (316, 152), (306, 167), (306, 245), (362, 245), (362, 270), (218, 270), (218, 245), (272, 245), (272, 167), (264, 152), (272, 137), (272, 88), (256, 70), (247, 50)], fill=255)
    for cx in (258, 289, 319):
        dh.ellipse((cx - 6, 13, cx + 6, 27), fill=255)
    solid = np.where(np.arange(h)[:, None] < 272, np.asarray(hilt) > 0, solid)
    print("silueta", solid.sum(), "pixelu, rozsah", np.where(solid.any(1))[0][[0, -1]], np.where(solid.any(0))[0][[0, -1]])
    # thickness: lens across each part, 2 cm is the widest (a half thickness of about 6 mm at 21 px/cm)
    dist = ndi.distance_transform_edt(solid)
    round_ = 1 - (1 - np.clip(dist / 14, 0, 1)) ** 2
    # colour
    k = 2
    big = np.asarray(Image.fromarray(np.uint8(a * 255)).resize((w * k, h * k), Image.LANCZOS), dtype=np.float32) / 255
    soft = ndi.gaussian_filter(big, 0.8)
    t = np.clip((soft - 0.34) / 0.42, 0, 1)
    t = t * t * (3 - 2 * t)
    niello, silver = np.array((0.022, 0.02, 0.02)), np.array((0.5, 0.48, 0.43))
    alb = niello + (silver - niello) * t[..., None]
    yy, xx = np.mgrid[0:h * k, 0:w * k].astype(np.float32) / k
    # the plate with the inlay; outside it the frames, grip and scrolls are worn iron and dull silver, never white
    half = np.interp(yy, (285, 345, 445, 520, 690, 760), (58, 54, 48, 50, 16, 6))
    panel = ((yy > 285) & (yy < 760) & (np.abs(xx - 292) < half)) | ((yy - 800) ** 2 + (xx - 292) ** 2 < 36 ** 2)
    worn = np.array((0.12, 0.115, 0.105)) + (np.array((0.28, 0.27, 0.25)) - np.array((0.12, 0.115, 0.105))) * t[..., None]
    alb = np.where(panel[..., None], alb, worn)
    # enamel where the book names it, only in the inked ground, not over the silver lines
    def enamel(cx, cy, radius, spokes):
        dx, dy = xx - cx, yy - cy
        inside = dx * dx + dy * dy < radius * radius
        sector = np.floor((np.arctan2(dy, dx) + np.pi) / (2 * np.pi) * spokes).astype(np.int32) % 2
        col = np.where(sector[..., None] == 0, np.array((0.15, 0.02, 0.015)), np.array((0.3, 0.2, 0.05)))
        on = (inside * (1 - t) * 0.8)[..., None]
        return alb * (1 - on) + col * on
    for cx, cy, radius, spokes in ((292, 395, 26, 8), (292, 480, 26, 8), (292, 800, 25, 12)):
        alb = enamel(cx, cy, radius, spokes)
    # the pelta at the foot of the fourth zone
    on = (((np.abs(xx - 292) < 13) & (yy > 612) & (yy < 640)) * (1 - t))[..., None]
    alb = alb * (1 - on) + np.array((0.15, 0.02, 0.015)) * on
    def srgb(c):
        return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.clip(c, 1e-5, 1), 1 / 2.4) - 0.055)
    Image.fromarray(np.uint8(srgb(np.clip(alb, 0, 1)) * 255)).save(out / "dyka-barva.png")
    Image.fromarray(np.uint8((0.55 - 0.25 * t) * 255)).save(out / "dyka-drsnost.png")
    Image.fromarray(np.uint8(ndi.gaussian_filter(big, 0.6) * 255)).save(out / "dyka-relief.png")
    Image.fromarray(np.uint8(solid) * 255).save(out / "dyka-silueta.png")
    # a smooth edge: the mesh runs a little past the silhouette, the alpha cuts it
    alpha = np.asarray(Image.fromarray(np.uint8(solid) * 255).resize((w * k, h * k), Image.BICUBIC).filter(ImageFilter.GaussianBlur(2.4)), dtype=np.float32) / 255
    Image.fromarray(np.uint8(np.clip((alpha - 0.5) * 4 + 0.5, 0, 1) * 255)).save(out / "dyka-alfa.png")
    Image.fromarray(np.uint8(ndi.binary_dilation(solid, iterations=4)) * 255).save(out / "dyka-sit.png")
    np.save(out / "dyka-tloustka.npy", round_.astype(np.float32))
    Image.fromarray(np.uint8(solid[..., None] * np.uint8(srgb(np.clip(alb[::k, ::k], 0, 1)) * 255))).save(out / "dyka-kontrola.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
