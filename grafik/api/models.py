"""Pydantic request/response models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from grafik.core.layer import BlendMode
from grafik.core.motion import LayerMotion, MotionSpec
from grafik.providers.base import Capabilities, ProviderKind


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
    rotation: float = 0.0
    source: str
    tags: list[str]
    motion: LayerMotion | None = None


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


# --- Task 1.7: per-element AI edit, segmentation, video jobs ---


class AiEditRequest(BaseModel):
    prompt: str
    provider: str = "qwen-inpaint"
    dilate_px: int = Field(default=4, ge=0)
    feather_px: int = Field(default=2, ge=0)
    # Optional brush mask, base64 PNG (no data: prefix), canvas coords, white=edit.
    # When set, the edit MERGES into the layer instead of replacing it -- see
    # ai_edit_layer in grafik/api/app.py.
    mask_b64: str | None = None


class AiEditResponse(BaseModel):
    layer: LayerResponse
    provider: str
    elapsed_s: float


class InpaintBehindRequest(BaseModel):
    prompt: str = ""  # empty -> DEFAULT_BEHIND_PROMPT (grafik/api/app.py)
    provider: str = "qwen-inpaint"
    dilate_px: int = Field(default=4, ge=0)
    feather_px: int = Field(default=2, ge=0)


class InpaintBehindResponse(BaseModel):
    layer: LayerResponse  # the background layer that received the fill
    provider: str
    elapsed_s: float


class ReorderRequest(BaseModel):
    z_order: int


class ProviderListItem(BaseModel):
    id: str
    endpoint: str
    kind: ProviderKind
    capabilities: Capabilities
    price_note: str = ""
    has_impl: bool
    image_field: str = "image_url"
    payload_defaults: dict = Field(default_factory=dict)
    duration_choices: list[str] = Field(default_factory=lambda: ["5", "10"])
    est_cost_usd_per_second: float | None = None


class SegmentRequest(BaseModel):
    text: str
    provider: str = "sam-3"
    create_layers: bool = True


class SegmentResponse(BaseModel):
    layers: list[LayerResponse] = Field(default_factory=list)
    mask_count: int = 0


class VideoJobRequest(BaseModel):
    motion: MotionSpec = Field(default_factory=MotionSpec)
    provider: str = "kling-26-pro"
    # Non-empty (after stripping) -> used INSTEAD of the compiled prompt, e.g.
    # a user hand-edited the /video/compile preview. See submit_video_job.
    prompt_override: str = ""


class CompileVideoRequest(BaseModel):
    motion: MotionSpec
    provider: str = "kling-26-pro"


class CompileVideoResponse(BaseModel):
    prompt: str
    provider: str
    endpoint: str
    duration: str
    est_cost_usd: float | None
    price_note: str
    payload_preview: dict
