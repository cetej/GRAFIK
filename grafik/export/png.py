"""PNG export — composite and individual layer export."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from grafik.core.composer import compose
from grafik.core.project import LayerProject


def export_composite(project: LayerProject, project_dir: Path, output: Path | None = None) -> Path:
    """Export the flattened composite as PNG."""
    composite = compose(project, project_dir)
    if output is None:
        output = project_dir / "composites" / "latest.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    composite.save(output, "PNG")
    return output


def export_layers(project: LayerProject, project_dir: Path, output_dir: Path | None = None) -> list[Path]:
    """Export each layer as an individual PNG file."""
    if output_dir is None:
        output_dir = project_dir / "export"
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for layer in project.layers:
        if not layer.png_path:
            continue
        try:
            img = layer.load_image(project_dir)
        except FileNotFoundError:
            continue
        out_path = output_dir / f"{layer.z_order:02d}_{layer.name or layer.id}.png"
        img.save(out_path, "PNG")
        paths.append(out_path)

    return paths


def export_all(project: LayerProject, project_dir: Path, output_dir: Path | None = None) -> dict[str, Path | list[Path]]:
    """Export both composite and individual layers."""
    if output_dir is None:
        output_dir = project_dir / "export"
    output_dir.mkdir(parents=True, exist_ok=True)

    composite_path = export_composite(project, project_dir, output_dir / "composite.png")
    layer_paths = export_layers(project, project_dir, output_dir / "layers")

    return {"composite": composite_path, "layers": layer_paths}
