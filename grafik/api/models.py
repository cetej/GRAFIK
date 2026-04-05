"""Pydantic request/response models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from grafik.core.layer import BlendMode


class CreateProjectRequest(BaseModel):
    name: str = "untitled"
    canvas_width: int = 0
    canvas_height: int = 0


class DecomposeRequest(BaseModel):
    image_url: str
    num_layers: int = Field(default=4, ge=1, le=10)


class GenerateRequest(BaseModel):
    prompt: str
    num_layers: int = Field(default=4, ge=1, le=10)


class RecolorRequest(BaseModel):
    hue_shift: float = 0.0
    saturation_scale: float = 1.0
    lightness_shift: float = 0.0


class TransformRequest(BaseModel):
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None
    rotation: float | None = None


class OpacityRequest(BaseModel):
    opacity: float = Field(ge=0.0, le=1.0)


class BlendModeRequest(BaseModel):
    blend_mode: BlendMode


class LayerResponse(BaseModel):
    id: str
    name: str
    z_order: int
    visible: bool
    opacity: float
    blend_mode: BlendMode
    x: int
    y: int
    width: int | None
    height: int | None
    source: str
    tags: list[str]


class ProjectResponse(BaseModel):
    id: str
    name: str
    canvas_width: int
    canvas_height: int
    layer_count: int
    created_at: str
    updated_at: str


class ProjectListItem(BaseModel):
    id: str
    name: str
    path: str
    layer_count: int


class MaskRequest(BaseModel):
    operation: str = "feather"  # feather, threshold, set_opacity
    radius: int = 5
    threshold: int = 128
    opacity: float = 1.0


class FlipRequest(BaseModel):
    direction: str = "horizontal"  # horizontal, vertical


class ScaleRequest(BaseModel):
    factor: float = 1.0


class CropRequest(BaseModel):
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0


class WorkflowRequest(BaseModel):
    workflow: str  # map_localization, hero_edit
    image_url: str = ""
    num_layers: int = Field(default=4, ge=1, le=10)
    params: dict = Field(default_factory=dict)


class WorkflowStepResponse(BaseModel):
    name: str
    success: bool
    data: dict = Field(default_factory=dict)
    error: str = ""


class HistoryResponse(BaseModel):
    undo_count: int
    redo_count: int


class HitTestRequest(BaseModel):
    x: int
    y: int


class HitTestResponse(BaseModel):
    layer_id: str | None = None
    layer_name: str | None = None
    z_order: int | None = None
