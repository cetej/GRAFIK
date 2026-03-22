"""Replace layer content — swap pixel data while preserving metadata."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from grafik.core.layer import Layer


def replace_content(
    layer: Layer,
    new_image: Image.Image,
    project_dir: Path,
    fit: str = "cover",
) -> None:
    """Replace a layer's pixel data with a new image.

    Args:
        layer: Target layer.
        new_image: New RGBA image to use.
        project_dir: Path to .grafik directory.
        fit: How to fit new image into layer dimensions.
            "cover" — resize to fill, crop excess.
            "contain" — resize to fit inside, pad transparent.
            "stretch" — resize to exact dimensions.
            "none" — use as-is, update layer dimensions.
    """
    if new_image.mode != "RGBA":
        new_image = new_image.convert("RGBA")

    if fit == "none" or layer.width is None or layer.height is None:
        layer.save_image(new_image, project_dir)
        layer.width = new_image.width
        layer.height = new_image.height
        return

    tw, th = layer.width, layer.height

    if fit == "stretch":
        result = new_image.resize((tw, th), Image.LANCZOS)
    elif fit == "contain":
        new_image.thumbnail((tw, th), Image.LANCZOS)
        result = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        ox = (tw - new_image.width) // 2
        oy = (th - new_image.height) // 2
        result.paste(new_image, (ox, oy))
    else:  # cover
        ratio = max(tw / new_image.width, th / new_image.height)
        scaled = new_image.resize(
            (int(new_image.width * ratio), int(new_image.height * ratio)),
            Image.LANCZOS,
        )
        ox = (scaled.width - tw) // 2
        oy = (scaled.height - th) // 2
        result = scaled.crop((ox, oy, ox + tw, oy + th))

    layer.save_image(result, project_dir)
