"""Compose layers into a single image."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image

from grafik.core.layer import BlendMode, Layer
from grafik.core.project import LayerProject


def compose(project: LayerProject, project_dir: Path | None = None) -> Image.Image:
    """Flatten all visible layers into a composite RGBA image."""
    w = project.canvas_width
    h = project.canvas_height

    # Auto-detect canvas size from layers if not set
    if not w or not h:
        for layer in project.layers:
            lw = (layer.width or 0) + layer.x
            lh = (layer.height or 0) + layer.y
            w = max(w, lw)
            h = max(h, lh)
    if not w or not h:
        w, h = 1920, 1080

    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    for layer in project.visible_layers():
        if not layer.png_path or project_dir is None:
            continue
        try:
            img = layer.load_image(project_dir)
        except FileNotFoundError:
            continue

        # Apply opacity
        if layer.opacity < 1.0:
            img = _apply_opacity(img, layer.opacity)

        # Resize if layer dimensions differ from image on disk
        target_w = layer.width or img.width
        target_h = layer.height or img.height
        if (target_w, target_h) != img.size:
            img = img.resize((target_w, target_h), Image.LANCZOS)

        # Rotation -- Konva rotates a layer clockwise (y-down canvas coords)
        # around its own (x, y) anchor; PIL's expand=True instead re-centers
        # the rotated content in a new bounding box, so the paste position
        # must be corrected by _rotation_offset to keep the anchor fixed.
        paste_pos = None
        if layer.rotation:
            pre_w, pre_h = img.size
            img = img.rotate(-layer.rotation, expand=True, resample=Image.BICUBIC)
            offset_x, offset_y = _rotation_offset(pre_w, pre_h, layer.rotation)
            paste_pos = (round(layer.x + offset_x), round(layer.y + offset_y))

        # Blend onto canvas at position
        _blend_layer(canvas, img, layer, paste_pos)

    return canvas


def compose_and_save(
    project: LayerProject, project_dir: Path, output: Path | None = None
) -> Path:
    """Compose and save the composite PNG."""
    composite = compose(project, project_dir)
    if output is None:
        output = project_dir / "composites" / "latest.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    composite.save(output, "PNG")
    return output


def _apply_opacity(img: Image.Image, opacity: float) -> Image.Image:
    """Multiply alpha channel by opacity factor."""
    r, g, b, a = img.split()
    a = a.point(lambda x: int(x * opacity))
    return Image.merge("RGBA", (r, g, b, a))


def _rotation_offset(w: int, h: int, rotation_deg: float) -> tuple[float, float]:
    """Offset of the rotate(expand=True) result's top-left corner from the
    layer's (x, y) anchor, for a clockwise rotation by rotation_deg around
    that anchor (Konva convention, y-down canvas coords).

    Rotates the unrotated image's 4 corners -- (0,0), (w,0), (0,h), (w,h) --
    around (0, 0) and returns the resulting bounding box's top-left. Adding
    this to (x, y) gives the correct paste position for the PIL-rotated
    image, independent of how PIL itself centers the expanded bounding box.
    """
    theta = math.radians(rotation_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    corners = ((0, 0), (w, 0), (0, h), (w, h))
    rotated_x = [cx * cos_t - cy * sin_t for cx, cy in corners]
    rotated_y = [cx * sin_t + cy * cos_t for cx, cy in corners]
    return min(rotated_x), min(rotated_y)


def _blend_layer(
    canvas: Image.Image, img: Image.Image, layer: Layer, paste_pos: tuple[int, int] | None = None
) -> None:
    """Paste layer onto canvas using blend mode.

    `paste_pos` overrides (layer.x, layer.y) -- needed when `img` was
    rotated, since the rotated (expand=True) image's own top-left no longer
    coincides with the layer's anchor point.
    """
    x, y = paste_pos if paste_pos is not None else (layer.x, layer.y)
    # Position the layer image on a full-size temp canvas
    temp = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    temp.paste(img, (x, y))

    if layer.blend_mode == BlendMode.NORMAL:
        canvas.alpha_composite(temp)
    else:
        from grafik.ops.blend import BLEND_FUNCTIONS
        blend_fn = BLEND_FUNCTIONS.get(layer.blend_mode.value)
        if blend_fn:
            result = blend_fn(canvas, temp)
            canvas.paste(result)
        else:
            canvas.alpha_composite(temp)
