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
