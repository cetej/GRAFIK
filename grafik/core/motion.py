"""Motion domain models — per-layer trajectories, camera intent, clip records.

Captures UI motion intent (trajectory + static flag + camera) for the
image-to-video axis (sc-2). As of 2026-08-14 no current fal.ai I2V endpoint
accepts per-element mask+trajectory as API input — see
docs/plans/2026-08-14-phase1-gate.md (A3 amendment). These models compile to
a STRUCTURED TEXT PROMPT (grafik.motion.compiler), not a Kling dynamic_masks
payload. Trajectory data is retained on LayerMotion/ClipRecord for
post-generation verification (pixel-diff against the intended region), not
because any provider consumes it directly today.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class TrajectoryPoint(BaseModel):
    """A single point on a layer's motion path, in full-resolution canvas coordinates."""

    x: int
    y: int


class LayerMotion(BaseModel):
    """Motion intent for a single layer within a MotionSpec."""

    trajectory: list[TrajectoryPoint] = Field(default_factory=list)
    static: bool = False
    # Optional user hint of the element's motion, e.g. "pták letí doprava".
    # Used verbatim by the compiler (no translation/paraphrasing — deterministic, no LLM).
    description: str = ""


class CameraMove(str, Enum):
    NONE = "none"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT_UP = "tilt_up"
    TILT_DOWN = "tilt_down"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    CUSTOM = "custom"


class CameraSpec(BaseModel):
    """Global camera intent for a clip. `prompt` is used when move=custom."""

    move: CameraMove = CameraMove.NONE
    magnitude: float = Field(default=0.5, ge=0.0, le=1.0)
    prompt: str = ""


class MotionSpec(BaseModel):
    """Per-clip motion intent: camera + per-layer trajectories, keyed by layer id."""

    camera: CameraSpec = Field(default_factory=CameraSpec)
    duration: str = "5"
    layer_motions: dict[str, LayerMotion] = Field(default_factory=dict)


class ClipRecord(BaseModel):
    """A single video generation job/result, attached to a LayerProject."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provider_id: str
    endpoint: str
    status: str = "pending"  # pending | running | completed | failed
    request_id: str = ""
    path: str = ""  # relative to project dir, e.g. "clips/xxx.mp4"
    prompt: str = ""
    motion: MotionSpec | None = None
    cost_note: str = ""
    error: str = ""
