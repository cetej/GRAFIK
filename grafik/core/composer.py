"""Compose layers into a single image."""

from __future__ import annotations

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

        # Rotation
        if layer.rotation:
            img = img.rotate(-layer.rotation, expand=True, resample=Image.BICUBIC)

        # Blend onto canvas at position
        _blend_layer(canvas, img, layer)

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


def _blend_layer(canvas: Image.Image, img: Image.Image, layer: Layer) -> None:
    """Paste layer onto canvas using blend mode."""
    # Position the layer image on a full-size temp canvas
    temp = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    temp.paste(img, (layer.x, layer.y))

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
