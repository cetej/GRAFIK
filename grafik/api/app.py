"""FastAPI backend for GRAFIK."""

from __future__ import annotations

import json
import math
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from grafik.api.models import (
    AiEditRequest,
    AiEditResponse,
    BlendModeRequest,
    CompileVideoRequest,
    CompileVideoResponse,
    CreateProjectRequest,
    CropRequest,
    DecomposeRequest,
    FlipRequest,
    HistoryResponse,
    HitTestRequest,
    HitTestResponse,
    InpaintBehindRequest,
    InpaintBehindResponse,
    LayerResponse,
    MaskRequest,
    OpacityRequest,
    ProjectListItem,
    ProjectResponse,
    ProviderListItem,
    RecolorRequest,
    RenameRequest,
    ReorderRequest,
    ScaleRequest,
    SegmentRequest,
    SegmentResponse,
    TransformRequest,
    VideoJobRequest,
    WorkflowRequest,
    WorkflowStepResponse,
)
from grafik.core.composer import compose, compose_and_save
from grafik.core.motion import ClipRecord, LayerMotion
from grafik.core.project import LayerProject

from grafik.core.history import History

load_dotenv()
load_dotenv("key.env")

app = FastAPI(title="GRAFIK API", version="0.2.0")

# In-memory history per project (stateless API, but history lives in session)
_histories: dict[str, History] = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8300", "http://localhost:8501", "http://127.0.0.1:8300", "http://127.0.0.1:8501", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
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
        width=l.width, height=l.height, rotation=l.rotation,
        source=l.source, tags=l.tags, motion=l.motion,
    )


def _boxes_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    """True if two (left, top, right, bottom) boxes overlap with positive area."""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


# --- Providers ---


@app.get("/api/providers")
def list_providers_route(kind: str | None = None) -> list[ProviderListItem]:
    from grafik.providers.registry import list_providers

    return [
        ProviderListItem(
            id=e.info.id,
            endpoint=e.info.endpoint,
            kind=e.info.kind,
            capabilities=e.info.capabilities,
            price_note=e.info.price_note,
            has_impl=e.impl is not None,
            image_field=e.info.image_field,
            payload_defaults=e.info.payload_defaults,
            duration_choices=e.info.duration_choices,
            est_cost_usd_per_second=e.info.est_cost_usd_per_second,
        )
        for e in list_providers(kind)
    ]


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
                    created_at=data.get("created_at", ""),
                    updated_at=data.get("updated_at", ""),
                ))
    # Most recently touched first; ISO-8601 UTC strings sort lexicographically.
    result.sort(key=lambda r: r.updated_at, reverse=True)
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


@app.patch("/api/projects/{project_id}")
def rename_project(project_id: str, req: RenameRequest) -> ProjectResponse:
    project, path = _load_project(project_id)
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "Project name must not be empty")
    project.name = name
    project.save(path)
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
    _histories.pop(project_id, None)
    return {"deleted": project_id}


@app.post("/api/projects/{project_id}/duplicate")
def duplicate_project(project_id: str) -> ProjectResponse:
    import shutil
    import uuid
    from datetime import datetime, timezone

    src = _find_project(project_id)
    dst = src.with_name(f"{src.stem}-kopie.grafik")
    n = 2
    while dst.exists():
        dst = src.with_name(f"{src.stem}-kopie-{n}.grafik")
        n += 1
    shutil.copytree(src, dst)
    # Undo snapshots embed the SOURCE project id -- an undo inside the copy
    # would restore it and leave two directories with the same id, so the
    # copy starts with no history.
    (dst / "history.json").unlink(missing_ok=True)

    copy = LayerProject.load(dst)
    copy.id = uuid.uuid4().hex[:12]
    copy.name = f"{copy.name} (kopie)"
    copy.created_at = datetime.now(timezone.utc).isoformat()
    copy.save(dst)
    return ProjectResponse(
        id=copy.id,
        name=copy.name,
        canvas_width=copy.canvas_width,
        canvas_height=copy.canvas_height,
        layer_count=len(copy.layers),
        created_at=copy.created_at,
        updated_at=copy.updated_at,
    )


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
        _layer_response(l)
        for l in layers
    ]


@app.post("/api/projects/{project_id}/decompose/file")
async def decompose_file(
    project_id: str,
    file: UploadFile = File(...),
    num_layers: int = 4,
) -> list[LayerResponse]:
    """Upload a file and decompose it into layers in one step."""
    from grafik.fal.client import FalClient
    from grafik.fal.upload import upload_image
    from PIL import Image

    project, path = _load_project(project_id)

    # Read uploaded image. A file that is not a decodable image must come back
    # as a readable 400, not an unhandled 500 -- unhandled exceptions bypass
    # CORSMiddleware, so the browser would only see "Failed to fetch"
    # (E2E finding, M2.5 drag&drop).
    img_data = await file.read()
    try:
        img = Image.open(BytesIO(img_data)).convert("RGBA")
    except Exception as exc:
        raise HTTPException(400, f"Soubor nejde přečíst jako obrázek: {exc}")

    # Upload to fal CDN
    image_url = upload_image(img)

    # Auto-set canvas
    if not project.canvas_width or not project.canvas_height:
        project.canvas_width = img.width
        project.canvas_height = img.height

    # Decompose
    client = FalClient()
    layers = client.decompose(
        image_url, num_layers,
        project=project, project_dir=path,
    )
    project.source_image_url = image_url
    project.save(path)
    return [_layer_response(l) for l in layers]


# --- Layers ---


@app.get("/api/projects/{project_id}/layers")
def list_layers(project_id: str) -> list[LayerResponse]:
    project, _ = _load_project(project_id)
    return [
        _layer_response(l)
        for l in project.layers
    ]


@app.get("/api/projects/{project_id}/layers/{layer_id}/png")
def get_layer_png(project_id: str, layer_id: str, checker: bool = False) -> Response:
    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")
    try:
        img = layer.load_image(path)
    except FileNotFoundError:
        raise HTTPException(404, "Layer PNG not found on disk")

    if checker:
        img = _add_checker_bg(img)

    buf = BytesIO()
    img.save(buf, "PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


def _add_checker_bg(img: Image.Image, cell: int = 16) -> Image.Image:
    """Render RGBA image on a checkerboard background to visualize transparency."""
    import numpy as np
    from PIL import Image
    w, h = img.size
    # Build checker pattern with numpy
    rows = np.arange(h) // cell
    cols = np.arange(w) // cell
    grid = (rows[:, None] + cols[None, :]) % 2
    dark = np.array([220, 220, 220, 255], dtype=np.uint8)
    light = np.array([245, 245, 245, 255], dtype=np.uint8)
    checker_arr = np.where(grid[:, :, None] == 0, dark, light)
    checker = Image.fromarray(checker_arr, "RGBA")
    checker.alpha_composite(img)
    return checker


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
    # Auto-set canvas size from first image if not set
    if not project.canvas_width or not project.canvas_height:
        project.canvas_width = img.width
        project.canvas_height = img.height
    project.save(path)

    return _layer_response(layer)


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
    return _layer_response(layer)


@app.post("/api/projects/{project_id}/layers/{layer_id}/opacity")
def set_opacity(project_id: str, layer_id: str, req: OpacityRequest) -> LayerResponse:
    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")
    layer.opacity = req.opacity
    project.save(path)
    return _layer_response(layer)


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
    _snapshot(project_id, project, path)
    project.save(path)
    return _layer_response(layer)


@app.post("/api/projects/{project_id}/layers/{layer_id}/rename")
def rename_layer(project_id: str, layer_id: str, req: RenameRequest) -> LayerResponse:
    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")
    name = req.name.strip()
    if not name:
        raise HTTPException(400, "Layer name must not be empty")
    layer.name = name
    _snapshot(project_id, project, path)
    project.save(path)
    return _layer_response(layer)


@app.post("/api/projects/{project_id}/layers/{layer_id}/reorder")
def reorder_layer(project_id: str, layer_id: str, req: ReorderRequest) -> list[LayerResponse]:
    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")
    project.reorder(layer_id, req.z_order)
    _snapshot(project_id, project, path)
    project.save(path)
    return [_layer_response(l) for l in project.layers]


# --- Motion (M3, per-layer trajectory persistence -- ideal-state criterion #6) ---


@app.post("/api/projects/{project_id}/layers/{layer_id}/motion")
def set_layer_motion(project_id: str, layer_id: str, req: LayerMotion) -> LayerResponse:
    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")
    layer.motion = req
    _snapshot(project_id, project, path)
    project.save(path)
    return _layer_response(layer)


@app.delete("/api/projects/{project_id}/layers/{layer_id}/motion")
def clear_layer_motion(project_id: str, layer_id: str) -> LayerResponse:
    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")
    layer.motion = None
    _snapshot(project_id, project, path)
    project.save(path)
    return _layer_response(layer)


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


@app.post("/api/projects/{project_id}/hittest")
def hittest(project_id: str, req: HitTestRequest) -> HitTestResponse:
    """Find topmost visible layer at canvas (x, y) by checking alpha > 0.

    Iterates layers top-to-bottom (highest z_order first).
    Returns the first layer where the pixel at (x, y) has alpha > 0.

    Shares the renderer's transform model (composer + Konva client): the
    native PNG is stretched to layer.width/height, then rotated clockwise
    around the (x, y) anchor. The canvas point is mapped back to native
    pixels by inverting those steps, so the answer matches the client's
    alpha hit-test on the rendered layer.
    """
    project, proj_dir = _load_project(project_id)
    # Check layers from top to bottom
    for layer in sorted(project.visible_layers(), key=lambda l: l.z_order, reverse=True):
        img = layer.load_image(proj_dir)
        if img is None:
            continue
        # Canvas -> layout space: un-translate, then undo the clockwise
        # rotation around the anchor (y-down coords, Konva convention).
        dx = req.x - layer.x
        dy = req.y - layer.y
        if layer.rotation:
            theta = math.radians(layer.rotation)
            cos_t, sin_t = math.cos(theta), math.sin(theta)
            dx, dy = dx * cos_t + dy * sin_t, -dx * sin_t + dy * cos_t
        # Layout -> native PNG pixels: layer.width/height may differ from
        # the PNG on disk (scaled in editor, or set by decompose).
        lx = math.floor(dx * img.width / (layer.width or img.width))
        ly = math.floor(dy * img.height / (layer.height or img.height))
        if 0 <= lx < img.width and 0 <= ly < img.height:
            pixel = img.getpixel((lx, ly))
            # RGBA — check alpha channel
            alpha = pixel[3] if len(pixel) == 4 else 255
            if alpha > 0:
                return HitTestResponse(
                    layer_id=layer.id,
                    layer_name=layer.name,
                    z_order=layer.z_order,
                )
    return HitTestResponse()


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


# --- AI edit (per-element, task 1.7) ---


@app.post("/api/projects/{project_id}/layers/{layer_id}/ai-edit")
def ai_edit_layer(project_id: str, layer_id: str, req: AiEditRequest) -> AiEditResponse:
    """Prompt-edit one layer inside a mask -- either its own alpha, or an
    explicit brush mask from the request.

    Default (mask_b64 unset): the mask is the layer's own alpha (>127 =
    editable), pasted into a canvas-size black frame at (layer.x, layer.y)
    -- layers in this repo are canvas-sized already (decompose output), but
    this also positions smaller/offset layers correctly. The result is
    cropped back to the layer's own box and its alpha replaced outright by a
    freshly dilated+feathered copy of the mask (dilate_px/feather_px from
    the request), so the edit REPLACES the layer's content in place
    (ideal-state: "vysledek nahradi obsah vrstvy") without resizing or
    repositioning the layer.

    Brush mode (mask_b64 set): the mask is a canvas-sized brush stroke drawn
    by the user (base64 PNG, white=edit) instead of the layer's own alpha.
    The result is MERGED into the layer's existing content instead of
    replacing it -- new_rgb = original*(1-f) + edited*f, new_alpha =
    max(original_alpha, feathered_mask) -- so pixels outside the feathered
    brush stay bit-identical and the edit can only add opaque area, never
    remove it.

    Either way, the provider edits the full composite inside that mask
    (mandatory paste-back happens inside the provider, e.g.
    QwenInpaintProvider).
    """
    import base64
    import time

    import numpy as np
    from PIL import Image, ImageFilter

    from grafik.providers.registry import get_provider

    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")

    try:
        entry = get_provider(req.provider)
    except KeyError:
        raise HTTPException(404, f"Unknown provider: {req.provider}")
    if not entry.info.capabilities.supports_mask:
        raise HTTPException(
            400, f"Provider {req.provider!r} does not support mask-based edit (supports_mask=False)"
        )
    if entry.impl is None:
        raise HTTPException(400, f"Provider {req.provider!r} has no implementation available yet")

    layer_img = layer.load_image(path)  # RGBA, layer-local size
    composite = compose(project, path)

    if req.mask_b64 is None:
        hard_mask_local = layer_img.split()[-1].point(lambda a: 255 if a > 127 else 0)
        hard_mask_canvas = Image.new("L", composite.size, 0)
        hard_mask_canvas.paste(hard_mask_local, (layer.x, layer.y))
    else:
        brush_mask = Image.open(BytesIO(base64.b64decode(req.mask_b64))).convert("L")
        if brush_mask.size != composite.size:
            raise HTTPException(
                400,
                f"mask_b64 size {brush_mask.size} does not match composite size {composite.size}",
            )
        hard_mask_canvas = brush_mask.point(lambda a: 255 if a > 127 else 0)

    provider = entry.impl()
    start = time.monotonic()
    try:
        edited = provider.edit(composite, hard_mask_canvas, req.prompt)
    except Exception as exc:
        raise HTTPException(502, f"AI edit failed ({req.provider}): {exc}")
    elapsed = time.monotonic() - start

    feathered_canvas = hard_mask_canvas
    if req.dilate_px > 0:
        feathered_canvas = feathered_canvas.filter(ImageFilter.MaxFilter(2 * req.dilate_px + 1))
    if req.feather_px > 0:
        feathered_canvas = feathered_canvas.filter(ImageFilter.GaussianBlur(req.feather_px))

    box = (layer.x, layer.y, layer.x + layer_img.width, layer.y + layer_img.height)
    new_rgb_local = edited.crop(box)
    new_alpha_local = feathered_canvas.crop(box)

    if req.mask_b64 is None:
        new_layer_img = Image.merge("RGBA", (*new_rgb_local.split(), new_alpha_local))
    else:
        # Merge into the existing layer instead of replacing it: pixels
        # where the feathered brush mask is 0 must stay bit-identical.
        orig_rgb = np.array(layer_img.convert("RGB"), dtype=np.float64)
        orig_alpha = np.array(layer_img.split()[-1])
        f = np.array(new_alpha_local, dtype=np.float64)[..., None] / 255.0
        merged_rgb = np.clip(
            orig_rgb * (1 - f) + np.array(new_rgb_local, dtype=np.float64) * f, 0, 255
        ).astype(np.uint8)
        merged_alpha = np.maximum(orig_alpha, np.array(new_alpha_local))
        new_layer_img = Image.merge(
            "RGBA",
            (*Image.fromarray(merged_rgb, "RGB").split(), Image.fromarray(merged_alpha, "L")),
        )

    layer.save_image(new_layer_img, path)
    _snapshot(project_id, project, path)
    project.save(path)

    return AiEditResponse(layer=_layer_response(layer), provider=req.provider, elapsed_s=elapsed)


# --- Inpaint behind (fill background left by a removed/edited element) ---


DEFAULT_BEHIND_PROMPT = "seamless continuation of the surrounding background, no objects, no text"


@app.post("/api/projects/{project_id}/layers/{layer_id}/inpaint-behind")
def inpaint_behind_layer(project_id: str, layer_id: str, req: InpaintBehindRequest) -> InpaintBehindResponse:
    """Fill in the background behind one layer (e.g. after cutting out a subject).

    The target layer's own (thresholded) alpha is the edit mask; the
    provider edits a composite of the project with the target layer removed
    (so it never sees the element it's meant to paint over). The result is
    merged -- same dilate+feather+merge math as ai-edit's mask_b64 path --
    into the lowest z-order OTHER visible layer, so the hole left behind
    becomes opaque background instead of a hard cutout.
    """
    import time

    import numpy as np
    from PIL import Image, ImageFilter

    from grafik.providers.registry import get_provider

    project, path = _load_project(project_id)
    layer = project.get_layer(layer_id)
    if not layer:
        raise HTTPException(404, f"Layer {layer_id} not found")

    try:
        entry = get_provider(req.provider)
    except KeyError:
        raise HTTPException(404, f"Unknown provider: {req.provider}")
    if entry.info.kind != "image_edit":
        raise HTTPException(400, f"Provider {req.provider!r} is kind {entry.info.kind!r}, expected 'image_edit'")
    if not entry.info.capabilities.supports_mask:
        raise HTTPException(
            400, f"Provider {req.provider!r} does not support mask-based edit (supports_mask=False)"
        )
    if entry.impl is None:
        raise HTTPException(400, f"Provider {req.provider!r} has no implementation available yet")

    bg_candidates = [l for l in project.layers if l.visible and l.id != layer_id]
    if not bg_candidates:
        raise HTTPException(400, "no other visible layer to inpaint into")
    bg_layer = min(bg_candidates, key=lambda l: l.z_order)

    composite = compose(project, path)
    layer_img = layer.load_image(path)  # RGBA, layer-local size
    hard_alpha_local = layer_img.split()[-1].point(lambda a: 255 if a > 127 else 0)
    mask_canvas = Image.new("L", composite.size, 0)
    mask_canvas.paste(hard_alpha_local, (layer.x, layer.y))

    bg_img = bg_layer.load_image(path)
    bg_box = (bg_layer.x, bg_layer.y, bg_layer.x + bg_img.width, bg_layer.y + bg_img.height)
    footprint = mask_canvas.getbbox()
    if footprint is None or not _boxes_overlap(footprint, bg_box):
        raise HTTPException(400, "target footprint does not overlap the background layer")

    # Compose the project WITHOUT the target layer -- the provider must not see
    # the element it's meant to paint over.
    project_copy = project.model_copy(deep=True)
    project_copy.remove_layer(layer_id)
    base = compose(project_copy, path)

    prompt = req.prompt or DEFAULT_BEHIND_PROMPT
    provider = entry.impl()
    start = time.monotonic()
    try:
        edited = provider.edit(base, mask_canvas, prompt)
    except Exception as exc:
        raise HTTPException(502, f"AI edit failed ({req.provider}): {exc}")
    elapsed = time.monotonic() - start

    feathered_canvas = mask_canvas
    if req.dilate_px > 0:
        feathered_canvas = feathered_canvas.filter(ImageFilter.MaxFilter(2 * req.dilate_px + 1))
    if req.feather_px > 0:
        feathered_canvas = feathered_canvas.filter(ImageFilter.GaussianBlur(req.feather_px))

    edited_crop = edited.crop(bg_box)
    feathered_crop = feathered_canvas.crop(bg_box)

    orig_rgb = np.array(bg_img.convert("RGB"), dtype=np.float64)
    orig_alpha = np.array(bg_img.split()[-1])
    f = np.array(feathered_crop, dtype=np.float64)[..., None] / 255.0
    merged_rgb = np.clip(
        orig_rgb * (1 - f) + np.array(edited_crop, dtype=np.float64) * f, 0, 255
    ).astype(np.uint8)
    merged_alpha = np.maximum(orig_alpha, np.array(feathered_crop))

    new_bg_img = Image.merge(
        "RGBA",
        (*Image.fromarray(merged_rgb, "RGB").split(), Image.fromarray(merged_alpha, "L")),
    )
    bg_layer.save_image(new_bg_img, path)
    _snapshot(project_id, project, path)
    project.save(path)

    return InpaintBehindResponse(layer=_layer_response(bg_layer), provider=req.provider, elapsed_s=elapsed)


# --- Segmentation (SAM 3, task 1.7) ---


def _segment_remote(image, text: str, endpoint: str, points: list | None = None) -> list:
    """All network I/O for one text- or point-prompted segmentation call:
    upload the image, call the fal segmentation endpoint, download each
    returned mask. Isolated in this one function so tests can monkeypatch
    grafik.api.app._segment_remote and exercise the /segment route fully
    offline -- mirrors QwenInpaintProvider._run_remote.

    `points` are SegmentPoint models in uploaded-image pixel space. The
    payload shape (point_prompts: [{x, y, label}]) comes from the raw fal
    OpenAPI schema for fal-ai/sam-3/image. The `prompt` key is ALWAYS sent,
    as "" for point-only calls: empirically (2026-08-15), omitting it lets
    the schema default "wheel" take over and point_prompts return 0 masks,
    while prompt="" + a point segments the clicked object (part-level
    granularity) -- see docs/capabilities/sam3-point.md.

    Returns a list of "L"-mode (grayscale) PIL masks, one per detection.
    """
    import fal_client

    from grafik.fal.upload import download_url, upload_image

    image_url = upload_image(image)
    arguments: dict = {"image_url": image_url, "prompt": text}
    if points:
        arguments["point_prompts"] = [{"x": p.x, "y": p.y, "label": p.label} for p in points]
    result = fal_client.subscribe(endpoint, arguments=arguments, with_logs=False)
    masks = []
    for m in result.get("masks", []) or []:
        url = m.get("url") if isinstance(m, dict) else m
        if url:
            masks.append(download_url(url).convert("L"))
    return masks


@app.post("/api/projects/{project_id}/segment")
def segment_project(project_id: str, req: SegmentRequest) -> SegmentResponse:
    """Text- or point-prompted segmentation (SAM 3) over the composite. Each
    returned mask (capped at 8) optionally becomes a new tagged layer: the
    composite's RGB masked by that detection's alpha. Registry entry sam-3
    has no concrete impl class (unlike qwen-inpaint) -- this route calls its
    fal endpoint directly via _segment_remote instead of a provider.segment().
    """
    from PIL import Image

    from grafik.core.layer import Layer
    from grafik.providers.registry import get_provider

    project, path = _load_project(project_id)

    text = req.text.strip()
    if not text and not req.points:
        raise HTTPException(400, "Provide text or points for segmentation")

    try:
        entry = get_provider(req.provider)
    except KeyError:
        raise HTTPException(404, f"Unknown provider: {req.provider}")
    if entry.info.kind != "segment":
        raise HTTPException(400, f"Provider {req.provider!r} is kind {entry.info.kind!r}, expected 'segment'")

    composite = compose(project, path)
    try:
        masks = _segment_remote(composite, text, entry.info.endpoint, points=req.points)
    except Exception as exc:
        raise HTTPException(502, f"Segmentation failed ({req.provider}): {exc}")
    mask_count = len(masks)  # informational: how many SAM found, even if capped below
    masks = masks[:8]

    if not req.create_layers:
        return SegmentResponse(mask_count=mask_count)

    if text:
        layer_name = f"sam: {text}"
    else:
        p0 = req.points[0]
        layer_name = f"sam: bod ({p0.x},{p0.y})"

    created: list[LayerResponse] = []
    rgb = composite.convert("RGB")
    for mask in masks:
        if mask.size != rgb.size:
            mask = mask.resize(rgb.size, Image.LANCZOS)
        r, g, b = rgb.split()
        layer_img = Image.merge("RGBA", (r, g, b, mask))
        layer = Layer(name=layer_name, source="sam", tags=["sam"])
        layer.save_image(layer_img, path)
        project.add_layer(layer)
        created.append(_layer_response(layer))

    project.save(path)
    return SegmentResponse(layers=created, mask_count=mask_count)


# --- Video jobs (async, task 1.7, architecture A4) ---


@app.post("/api/projects/{project_id}/video/compile")
def compile_video_route(project_id: str, req: CompileVideoRequest) -> CompileVideoResponse:
    """Preview a MotionSpec's compiled prompt + provider payload without
    submitting a job (ideal-state criterion #7) -- lets the UI show the
    prompt and an approximate cost before spending money. `payload_preview`
    uses the placeholder "<composite>" in place of a real uploaded image URL.
    """
    from grafik.motion.compiler import build_video_payload, compile_motion_prompt
    from grafik.providers.registry import get_provider

    project, _ = _load_project(project_id)
    try:
        entry = get_provider(req.provider)
    except KeyError:
        raise HTTPException(404, f"Unknown provider: {req.provider}")
    if entry.info.kind != "video":
        raise HTTPException(400, f"Provider {req.provider!r} is kind {entry.info.kind!r}, expected 'video'")

    prompt = compile_motion_prompt(project, req.motion)
    try:
        payload_preview = build_video_payload(entry, "<composite>", prompt, req.motion.duration)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    est_cost_usd = None
    if entry.info.est_cost_usd_per_second is not None:
        try:
            est_cost_usd = entry.info.est_cost_usd_per_second * float(req.motion.duration)
        except ValueError:
            est_cost_usd = None

    return CompileVideoResponse(
        prompt=prompt,
        provider=req.provider,
        endpoint=entry.info.endpoint,
        duration=req.motion.duration,
        est_cost_usd=est_cost_usd,
        price_note=entry.info.price_note,
        payload_preview=payload_preview,
    )


@app.post("/api/projects/{project_id}/video/jobs")
def submit_video_job_route(project_id: str, req: VideoJobRequest) -> ClipRecord:
    from grafik.motion.jobs import submit_video_job

    project, path = _load_project(project_id)
    try:
        return submit_video_job(project, path, req.motion, req.provider, req.prompt_override)
    except KeyError:
        raise HTTPException(404, f"Unknown provider: {req.provider}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/projects/{project_id}/video/jobs")
def list_video_jobs(project_id: str) -> list[ClipRecord]:
    project, _ = _load_project(project_id)
    return project.clips


@app.get("/api/projects/{project_id}/video/jobs/{clip_id}")
def get_video_job(project_id: str, clip_id: str) -> ClipRecord:
    from grafik.motion.jobs import refresh_video_job

    project, path = _load_project(project_id)
    try:
        return refresh_video_job(project, path, clip_id)
    except ValueError:
        raise HTTPException(404, f"Clip {clip_id} not found")


@app.get("/api/projects/{project_id}/clips/{clip_id}/video")
def get_clip_video(project_id: str, clip_id: str) -> FileResponse:
    """Serve a completed clip's mp4 file from disk.

    FileResponse (not Response with the whole body) so Range requests get
    206 partial responses — Chromium's <video> pipeline stalls at
    readyState 0 on servers that answer every media Range probe with a
    full 200 body (M3 E2E finding).
    """
    project, path = _load_project(project_id)
    clip = next((c for c in project.clips if c.id == clip_id), None)
    if clip is None:
        raise HTTPException(404, f"Clip {clip_id} not found")
    if clip.status != "completed" or not clip.path:
        raise HTTPException(400, f"Clip {clip_id} is not completed yet (status={clip.status})")
    video_path = path / clip.path
    if not video_path.exists():
        raise HTTPException(404, "Clip video file not found on disk")
    return FileResponse(video_path, media_type="video/mp4")


@app.post("/api/projects/{project_id}/clips/{clip_id}/verify")
def verify_clip_route(project_id: str, clip_id: str) -> ClipRecord:
    """Pixel-diff verify one completed clip against its per-layer motion
    intent (ideal-state criterion #8) and persist the result onto its
    ClipRecord.
    """
    from grafik.motion.verify import verify_clip

    project, path = _load_project(project_id)
    clip = next((c for c in project.clips if c.id == clip_id), None)
    if clip is None:
        raise HTTPException(404, f"Clip {clip_id} not found")
    if clip.status != "completed" or not clip.path:
        raise HTTPException(400, f"Clip {clip_id} is not completed yet (status={clip.status})")
    video_path = path / clip.path
    if not video_path.exists():
        raise HTTPException(400, "Clip video file not found on disk")

    clip.verification = verify_clip(project, path, clip)
    project.save(path)
    return clip
