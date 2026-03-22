"""FastAPI backend for GRAFIK."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from grafik.api.models import (
    CreateProjectRequest,
    DecomposeRequest,
    LayerResponse,
    OpacityRequest,
    ProjectListItem,
    ProjectResponse,
    TransformRequest,
)
from grafik.core.composer import compose, compose_and_save
from grafik.core.project import LayerProject

load_dotenv()

app = FastAPI(title="GRAFIK API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECTS_DIR = Path("projects")


def _projects_dir() -> Path:
    PROJECTS_DIR.mkdir(exist_ok=True)
    return PROJECTS_DIR


def _find_project(project_id: str) -> Path:
    """Find a .grafik directory by project ID."""
    for p in _projects_dir().iterdir():
        if p.is_dir() and p.suffix == ".grafik":
            manifest = p / "project.json"
            if manifest.exists():
                data = json.loads(manifest.read_text(encoding="utf-8"))
                if data.get("id") == project_id:
                    return p
    raise HTTPException(404, f"Project {project_id} not found")


def _load_project(project_id: str) -> tuple[LayerProject, Path]:
    path = _find_project(project_id)
    return LayerProject.load(path), path


# --- Projects ---


@app.get("/api/projects")
def list_projects() -> list[ProjectListItem]:
    result = []
    for p in _projects_dir().iterdir():
        if p.is_dir() and p.suffix == ".grafik":
            manifest = p / "project.json"
            if manifest.exists():
                data = json.loads(manifest.read_text(encoding="utf-8"))
                result.append(ProjectListItem(
                    id=data.get("id", ""),
                    name=data.get("name", p.stem),
                    path=str(p),
                    layer_count=len(data.get("layers", [])),
                ))
    return result


@app.post("/api/projects")
def create_project(req: CreateProjectRequest) -> ProjectResponse:
    project = LayerProject.new(req.name, req.canvas_width, req.canvas_height)
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in req.name)
    path = _projects_dir() / f"{safe_name or project.id}.grafik"
    project.save(path)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        canvas_width=project.canvas_width,
        canvas_height=project.canvas_height,
        layer_count=0,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> ProjectResponse:
    project, _ = _load_project(project_id)
    return ProjectResponse(
        id=project.id,
        name=project.name,
        canvas_width=project.canvas_width,
        canvas_height=project.canvas_height,
        layer_count=len(project.layers),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict:
    import shutil
    path = _find_project(project_id)
    shutil.rmtree(path)
    return {"deleted": project_id}


# --- Decompose ---


@app.post("/api/projects/{project_id}/decompose")
def decompose(project_id: str, req: DecomposeRequest) -> list[LayerResponse]:
    from grafik.fal.client import FalClient

    project, path = _load_project(project_id)
    client = FalClient()
    layers = client.decompose(
        req.image_url,
        req.num_layers,
        project=project,
        project_dir=path,
    )
    project.source_image_url = req.image_url
    project.save(path)
    return [
        LayerResponse(
            id=l.id, name=l.name, z_order=l.z_order, visible=l.visible,
            opacity=l.opacity, blend_mode=l.blend_mode, x=l.x, y=l.y,
            width=l.width, height=l.height, source=l.source, tags=l.tags,
        )
        for l in layers
    ]


# --- Layers ---


@app.get("/api/projects/{project_id}/layers")
def list_layers(project_id: str) -> list[LayerResponse]:
    project, _ = _load_project(project_id)
    return [
        LayerResponse(
            id=l.id, name=l.name, z_order=l.z_order, visible=l.visible,
            opacity=l.opacity, blend_mode=l.blend_mode, x=l.x, y=l.y,
            width=l.width, height=l.height, source=l.source, tags=l.tags,
        )
        for l in project.layers
    ]


@app.get("/api/projects/{project_id}/layers/{layer_id}/png")
def get_layer_png(project_id: str, layer_id: str) -> Response:
    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")
    try:
        img = layer.load_image(path)
    except FileNotFoundError:
        raise HTTPException(404, "Layer PNG not found on disk")
    buf = BytesIO()
    img.save(buf, "PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@app.post("/api/projects/{project_id}/layers")
async def add_layer(project_id: str, file: UploadFile = File(...)) -> LayerResponse:
    from grafik.core.layer import Layer
    from PIL import Image

    project, path = _load_project(project_id)
    img_data = await file.read()
    img = Image.open(BytesIO(img_data)).convert("RGBA")

    layer = Layer(
        name=file.filename or "uploaded",
        source="file",
    )
    layer.save_image(img, path)
    project.add_layer(layer)
    project.save(path)

    return LayerResponse(
        id=layer.id, name=layer.name, z_order=layer.z_order, visible=layer.visible,
        opacity=layer.opacity, blend_mode=layer.blend_mode, x=layer.x, y=layer.y,
        width=layer.width, height=layer.height, source=layer.source, tags=layer.tags,
    )


@app.delete("/api/projects/{project_id}/layers/{layer_id}")
def delete_layer(project_id: str, layer_id: str) -> dict:
    project, path = _load_project(project_id)
    removed = project.remove_layer(layer_id)
    if not removed:
        raise HTTPException(404, f"Layer {layer_id} not found")
    # Delete PNG file
    png = path / removed.png_path
    if png.exists():
        png.unlink()
    project.save(path)
    return {"deleted": layer_id}


# --- Layer operations ---


@app.post("/api/projects/{project_id}/layers/{layer_id}/visibility")
def toggle_visibility(project_id: str, layer_id: str) -> LayerResponse:
    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")
    layer.visible = not layer.visible
    project.save(path)
    return LayerResponse(
        id=layer.id, name=layer.name, z_order=layer.z_order, visible=layer.visible,
        opacity=layer.opacity, blend_mode=layer.blend_mode, x=layer.x, y=layer.y,
        width=layer.width, height=layer.height, source=layer.source, tags=layer.tags,
    )


@app.post("/api/projects/{project_id}/layers/{layer_id}/opacity")
def set_opacity(project_id: str, layer_id: str, req: OpacityRequest) -> LayerResponse:
    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")
    layer.opacity = req.opacity
    project.save(path)
    return LayerResponse(
        id=layer.id, name=layer.name, z_order=layer.z_order, visible=layer.visible,
        opacity=layer.opacity, blend_mode=layer.blend_mode, x=layer.x, y=layer.y,
        width=layer.width, height=layer.height, source=layer.source, tags=layer.tags,
    )


@app.post("/api/projects/{project_id}/layers/{layer_id}/transform")
def transform_layer(project_id: str, layer_id: str, req: TransformRequest) -> LayerResponse:
    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")
    if req.x is not None:
        layer.x = req.x
    if req.y is not None:
        layer.y = req.y
    if req.width is not None:
        layer.width = req.width
    if req.height is not None:
        layer.height = req.height
    if req.rotation is not None:
        layer.rotation = req.rotation
    project.save(path)
    return LayerResponse(
        id=layer.id, name=layer.name, z_order=layer.z_order, visible=layer.visible,
        opacity=layer.opacity, blend_mode=layer.blend_mode, x=layer.x, y=layer.y,
        width=layer.width, height=layer.height, source=layer.source, tags=layer.tags,
    )


# --- Composite ---


@app.get("/api/projects/{project_id}/composite")
def get_composite(project_id: str) -> Response:
    project, path = _load_project(project_id)
    if not project.layers:
        raise HTTPException(400, "No layers in project")
    composite = compose(project, path)
    buf = BytesIO()
    composite.save(buf, "PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@app.post("/api/projects/{project_id}/export/png")
def export_png(project_id: str) -> Response:
    project, path = _load_project(project_id)
    output = compose_and_save(project, path)
    return Response(
        content=output.read_bytes(),
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{project.name}_composite.png"'},
    )
