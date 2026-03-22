"""Compose layers into a single image."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from grafik.core.layer import BlendMode, Layer
from grafik.core.project import LayerProject


def compose(project: LayerProject, project_dir: Path | None = None) -> Image.Image:
    """Flatten all visible layers into a composite RGBA image.

    Args:
        project: The layer project.
        project_dir: Path to the .grafik directory. Required to load layer PNGs.

    Returns:
        Composite RGBA PIL Image.
    """
    w = project.canvas_width or 1920
    h = project.canvas_height or 1080
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

        # Resize if dimensions specified and different from original
        if layer.width and layer.height:
            if (layer.width, layer.height) != img.size:
                img = img.resize((layer.width, layer.height), Image.LANCZOS)

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
    # For MVP, only NORMAL blend mode — others will be added in Phase 2
    if layer.blend_mode == BlendMode.NORMAL:
        # Create a temp canvas same size, paste at offset, alpha_composite
        temp = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        temp.paste(img, (layer.x, layer.y))
        canvas.alpha_composite(temp)
    else:
        # Fallback to normal for now
        temp = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        temp.paste(img, (layer.x, layer.y))
        canvas.alpha_composite(temp)
