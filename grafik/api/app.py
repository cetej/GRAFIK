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
    BlendModeRequest,
    CreateProjectRequest,
    CropRequest,
    DecomposeRequest,
    FlipRequest,
    HistoryResponse,
    LayerResponse,
    MaskRequest,
    OpacityRequest,
    ProjectListItem,
    ProjectResponse,
    RecolorRequest,
    ScaleRequest,
    TransformRequest,
    WorkflowRequest,
    WorkflowStepResponse,
)
from grafik.core.composer import compose, compose_and_save
from grafik.core.project import LayerProject

from grafik.core.history import History

load_dotenv()
load_dotenv("key.env")

app = FastAPI(title="GRAFIK API", version="0.2.0")

# In-memory history per project (stateless API, but history lives in session)
_histories: dict[str, History] = {}

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


def _get_history(project_id: str, project_dir: Path) -> History:
    if project_id not in _histories:
        hist_path = project_dir / "history.json"
        _histories[project_id] = History.load_from_file(hist_path)
    return _histories[project_id]


def _snapshot(project_id: str, project: LayerProject, project_dir: Path) -> None:
    h = _get_history(project_id, project_dir)
    h.push(project.model_dump_json())
    h.save_to_file(project_dir / "history.json")


def _layer_response(l) -> LayerResponse:
    return LayerResponse(
        id=l.id, name=l.name, z_order=l.z_order, visible=l.visible,
        opacity=l.opacity, blend_mode=l.blend_mode, x=l.x, y=l.y,
        width=l.width, height=l.height, source=l.source, tags=l.tags,
    )


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


@app.post("/api/projects/{project_id}/export/layers")
def export_layers_png(project_id: str) -> dict:
    from grafik.export.png import export_layers
    project, path = _load_project(project_id)
    paths = export_layers(project, path)
    return {"exported": [str(p) for p in paths]}


# --- Recolor ---


@app.post("/api/projects/{project_id}/layers/{layer_id}/recolor")
def recolor_layer(project_id: str, layer_id: str, req: RecolorRequest) -> LayerResponse:
    from grafik.ops.recolor import recolor
    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")
    img = layer.load_image(path)
    result = recolor(img, req.hue_shift, req.saturation_scale, req.lightness_shift)
    layer.save_image(result, path)
    _snapshot(project_id, project, path)
    project.save(path)
    return _layer_response(layer)


# --- Blend mode ---


@app.post("/api/projects/{project_id}/layers/{layer_id}/blend_mode")
def set_blend_mode(project_id: str, layer_id: str, req: BlendModeRequest) -> LayerResponse:
    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")
    layer.blend_mode = req.blend_mode
    _snapshot(project_id, project, path)
    project.save(path)
    return _layer_response(layer)


# --- Flip ---


@app.post("/api/projects/{project_id}/layers/{layer_id}/flip")
def flip_layer(project_id: str, layer_id: str, req: FlipRequest) -> LayerResponse:
    from grafik.ops.transform import flip_horizontal, flip_vertical
    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")
    img = layer.load_image(path)
    if req.direction == "vertical":
        result = flip_vertical(img)
    else:
        result = flip_horizontal(img)
    layer.save_image(result, path)
    _snapshot(project_id, project, path)
    project.save(path)
    return _layer_response(layer)


# --- Scale ---


@app.post("/api/projects/{project_id}/layers/{layer_id}/scale")
def scale_layer(project_id: str, layer_id: str, req: ScaleRequest) -> LayerResponse:
    from grafik.ops.transform import scale
    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")
    img = layer.load_image(path)
    result = scale(img, req.factor)
    layer.save_image(result, path)
    layer.width = result.width
    layer.height = result.height
    _snapshot(project_id, project, path)
    project.save(path)
    return _layer_response(layer)


# --- Mask operations ---


@app.post("/api/projects/{project_id}/layers/{layer_id}/mask")
def mask_layer(project_id: str, layer_id: str, req: MaskRequest) -> LayerResponse:
    from grafik.ops.mask import feather_edges, threshold_alpha, set_opacity
    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")
    img = layer.load_image(path)
    if req.operation == "feather":
        result = feather_edges(img, req.radius)
    elif req.operation == "threshold":
        result = threshold_alpha(img, req.threshold)
    elif req.operation == "set_opacity":
        result = set_opacity(img, req.opacity)
    else:
        raise HTTPException(400, f"Unknown mask operation: {req.operation}")
    layer.save_image(result, path)
    _snapshot(project_id, project, path)
    project.save(path)
    return _layer_response(layer)


# --- History (undo/redo) ---


@app.get("/api/projects/{project_id}/history")
def get_history(project_id: str) -> HistoryResponse:
    _, path = _load_project(project_id)
    h = _get_history(project_id, path)
    return HistoryResponse(undo_count=h.undo_count, redo_count=h.redo_count)


@app.post("/api/projects/{project_id}/undo")
def undo(project_id: str) -> dict:
    project, path = _load_project(project_id)
    h = _get_history(project_id, path)
    state = h.undo()
    if state is None:
        raise HTTPException(400, "Nothing to undo")
    # Restore project.json from snapshot
    (path / "project.json").write_text(state, encoding="utf-8")
    h.save_to_file(path / "history.json")
    return {"undone": True, "undo_remaining": h.undo_count, "redo_available": h.redo_count}


@app.post("/api/projects/{project_id}/redo")
def redo(project_id: str) -> dict:
    project, path = _load_project(project_id)
    h = _get_history(project_id, path)
    state = h.redo()
    if state is None:
        raise HTTPException(400, "Nothing to redo")
    (path / "project.json").write_text(state, encoding="utf-8")
    h.save_to_file(path / "history.json")
    return {"redone": True, "undo_available": h.undo_count, "redo_remaining": h.redo_count}


# --- Workflows ---


@app.post("/api/projects/{project_id}/workflows/run")
def run_workflow(project_id: str, req: WorkflowRequest) -> list[WorkflowStepResponse]:
    from grafik.workflows import WORKFLOWS
    project, path = _load_project(project_id)

    wf_class = WORKFLOWS.get(req.workflow)
    if not wf_class:
        raise HTTPException(400, f"Unknown workflow: {req.workflow}. Available: {list(WORKFLOWS.keys())}")

    wf = wf_class(project, path)
    params = {**req.params}
    if req.image_url:
        params["image_url"] = req.image_url
    if req.num_layers:
        params["num_layers"] = req.num_layers

    results = wf.run(**params)
    _snapshot(project_id, project, path)

    return [
        WorkflowStepResponse(name=r.name, success=r.success, data=r.data, error=r.error)
        for r in results
    ]
