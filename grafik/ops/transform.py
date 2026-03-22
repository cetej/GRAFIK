"""Transform operations — resize, rotate, flip, crop on RGBA layers."""

from __future__ import annotations

from PIL import Image


def resize(img: Image.Image, width: int, height: int) -> Image.Image:
    """Resize image to exact dimensions."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img.resize((width, height), Image.LANCZOS)


def scale(img: Image.Image, factor: float) -> Image.Image:
    """Scale image by a factor (e.g. 0.5 = half, 2.0 = double)."""
    new_w = max(1, int(img.width * factor))
    new_h = max(1, int(img.height * factor))
    return resize(img, new_w, new_h)


def rotate(img: Image.Image, angle: float, expand: bool = True) -> Image.Image:
    """Rotate image by angle in degrees (counter-clockwise)."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img.rotate(angle, expand=expand, resample=Image.BICUBIC)


def flip_horizontal(img: Image.Image) -> Image.Image:
    """Mirror image horizontally."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img.transpose(Image.FLIP_LEFT_RIGHT)


def flip_vertical(img: Image.Image) -> Image.Image:
    """Mirror image vertically."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img.transpose(Image.FLIP_TOP_BOTTOM)


def crop(img: Image.Image, left: int, top: int, right: int, bottom: int) -> Image.Image:
    """Crop image to a bounding box."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img.crop((left, top, right, bottom))
