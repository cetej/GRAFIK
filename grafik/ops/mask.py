"""Alpha mask operations on RGBA layers."""

from __future__ import annotations

from PIL import Image, ImageFilter


def set_opacity(img: Image.Image, opacity: float) -> Image.Image:
    """Set global opacity (multiply alpha by factor)."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    r, g, b, a = img.split()
    a = a.point(lambda x: int(x * max(0.0, min(1.0, opacity))))
    return Image.merge("RGBA", (r, g, b, a))


def apply_mask(img: Image.Image, mask: Image.Image) -> Image.Image:
    """Apply a grayscale mask to the alpha channel (white=opaque, black=transparent)."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    mask_l = mask.convert("L").resize(img.size, Image.LANCZOS)
    r, g, b, a = img.split()
    # Multiply existing alpha with mask
    new_a = Image.new("L", img.size)
    new_a_data = [
        int(av * mv / 255) for av, mv in zip(a.getdata(), mask_l.getdata())
    ]
    new_a.putdata(new_a_data)
    return Image.merge("RGBA", (r, g, b, new_a))


def feather_edges(img: Image.Image, radius: int = 5) -> Image.Image:
    """Blur the alpha channel edges for a soft feather effect."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    r, g, b, a = img.split()
    a = a.filter(ImageFilter.GaussianBlur(radius))
    return Image.merge("RGBA", (r, g, b, a))


def threshold_alpha(img: Image.Image, threshold: int = 128) -> Image.Image:
    """Make alpha binary: above threshold = 255, below = 0."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    r, g, b, a = img.split()
    a = a.point(lambda x: 255 if x >= threshold else 0)
    return Image.merge("RGBA", (r, g, b, a))


def extract_alpha(img: Image.Image) -> Image.Image:
    """Extract alpha channel as a grayscale image."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img.split()[3]
