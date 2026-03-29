"""GRAFIK CLI — Typer-based command-line interface."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

app = typer.Typer(name="grafik", help="Modular layered image editor.")


@app.command()
def decompose(
    image: str = typer.Argument(help="Image path or URL to decompose"),
    layers: int = typer.Option(4, "--layers", "-l", help="Number of layers (1-10)"),
    project: str = typer.Option(None, "--project", "-p", help="Path to .grafik project dir"),
    name: str = typer.Option("untitled", "--name", "-n", help="Project name (if creating new)"),
):
    """Decompose an image into RGBA layers."""
    from dotenv import load_dotenv
    load_dotenv()

    from grafik.core.project import LayerProject
    from grafik.fal.client import FalClient

    # Determine image URL
    image_path = Path(image)
    is_local = image_path.exists()

    # Setup project
    if project:
        proj_path = Path(project)
        if proj_path.exists():
            proj = LayerProject.load(proj_path)
        else:
            proj = LayerProject.new(name)
            proj_path = proj.save(proj_path)
    else:
        proj = LayerProject.new(name)
        safe = "".join(c if c.isalnum() or c in "-_ " else "" for c in name)
        proj_path = Path("projects") / f"{safe or proj.id}.grafik"
        proj_path = proj.save(proj_path)

    typer.echo(f"Project: {proj_path}")
    typer.echo(f"Decomposing into {layers} layers...")

    client = FalClient()

    if is_local:
        result_layers = client.decompose_file(
            image_path, layers, project=proj, project_dir=proj_path
        )
    else:
        result_layers = client.decompose(
            image, layers, project=proj, project_dir=proj_path
        )

    proj.save(proj_path)

    typer.echo(f"Done! {len(result_layers)} layers created:")
    for l in result_layers:
        typer.echo(f"  [{l.z_order}] {l.name} ({l.width}x{l.height}) → {l.png_path}")


@app.command("composite")
def export_composite(
    project: str = typer.Argument(help="Path to .grafik project"),
    output: str = typer.Option(None, "--output", "-o", help="Output PNG path"),
):
    """Export composite PNG from a project."""
    from grafik.core.project import LayerProject
    from grafik.core.composer import compose_and_save

    proj_path = Path(project)
    proj = LayerProject.load(proj_path)

    out = Path(output) if output else None
    result = compose_and_save(proj, proj_path, out)
    typer.echo(f"Composite saved: {result}")


@app.command("layers")
def list_layers(
    project: str = typer.Argument(help="Path to .grafik project"),
):
    """List all layers in a project."""
    from grafik.core.project import LayerProject

    proj_path = Path(project)
    proj = LayerProject.load(proj_path)

    if not proj.layers:
        typer.echo("No layers.")
        return

    typer.echo(f"Project: {proj.name} ({proj.canvas_width}x{proj.canvas_height})")
    typer.echo(f"Layers ({len(proj.layers)}):")
    for l in proj.layers:
        vis = "👁" if l.visible else "  "
        typer.echo(f"  {vis} [{l.z_order}] {l.id} {l.name} "
                    f"({l.width}x{l.height}) opacity={l.opacity} {l.source}")


@app.command()
def serve(
    port: int = typer.Option(8100, "--port", "-p", help="API port"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on changes"),
):
    """Start the FastAPI server."""
    import uvicorn
    typer.echo(f"Starting GRAFIK API on port {port}...")
    uvicorn.run("grafik.api.app:app", host="127.0.0.1", port=port, reload=reload)


@app.command()
def ui(
    port: int = typer.Option(8501, "--port", "-p", help="Streamlit port"),
):
    """Start the Streamlit UI."""
    import subprocess
    ui_path = Path(__file__).parent.parent.parent / "ui" / "app.py"
    if not ui_path.exists():
        typer.echo(f"UI not found at {ui_path}", err=True)
        raise typer.Exit(1)
    subprocess.run([
        sys.executable, "-m", "streamlit", "run", str(ui_path),
        "--server.port", str(port),
        "--server.headless", "true",
    ])


if __name__ == "__main__":
    app()
