"""Recolor operations — hue/saturation/lightness adjustments on RGBA layers."""

from __future__ import annotations

import colorsys

from PIL import Image


def recolor(
    img: Image.Image,
    hue_shift: float = 0.0,
    saturation_scale: float = 1.0,
    lightness_shift: float = 0.0,
) -> Image.Image:
    """Apply HSL adjustments to an RGBA image.

    Args:
        img: Source RGBA image.
        hue_shift: Hue rotation in degrees (-180 to 180).
        saturation_scale: Multiply saturation (0.0 = grayscale, 2.0 = oversaturated).
        lightness_shift: Add to lightness (-1.0 to 1.0).

    Returns:
        New RGBA image with adjustments applied.
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    r, g, b, a = img.split()
    pixels = list(zip(r.getdata(), g.getdata(), b.getdata()))

    hue_norm = (hue_shift % 360) / 360.0

    new_pixels = []
    for pr, pg, pb in pixels:
        h, l, s = colorsys.rgb_to_hls(pr / 255.0, pg / 255.0, pb / 255.0)
        h = (h + hue_norm) % 1.0
        s = max(0.0, min(1.0, s * saturation_scale))
        l = max(0.0, min(1.0, l + lightness_shift))
        nr, ng, nb = colorsys.hls_to_rgb(h, l, s)
        new_pixels.append((int(nr * 255), int(ng * 255), int(nb * 255)))

    new_r = Image.new("L", img.size)
    new_g = Image.new("L", img.size)
    new_b = Image.new("L", img.size)
    new_r.putdata([p[0] for p in new_pixels])
    new_g.putdata([p[1] for p in new_pixels])
    new_b.putdata([p[2] for p in new_pixels])

    return Image.merge("RGBA", (new_r, new_g, new_b, a))


def grayscale(img: Image.Image) -> Image.Image:
    """Convert to grayscale while preserving alpha."""
    return recolor(img, saturation_scale=0.0)


def invert_colors(img: Image.Image) -> Image.Image:
    """Invert RGB channels, preserve alpha."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    r, g, b, a = img.split()
    r = r.point(lambda x: 255 - x)
    g = g.point(lambda x: 255 - x)
    b = b.point(lambda x: 255 - x)
    return Image.merge("RGBA", (r, g, b, a))
