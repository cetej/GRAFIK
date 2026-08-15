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


class ElementVerdict(BaseModel):
    """Pixel-diff verdict for one layer's intended motion within a clip
    (grafik.motion.verify.verify_clip) -- ideal-state criterion #8, "hybalo
    se to, co melo".
    """

    layer_id: str
    layer_name: str
    wanted: str  # "move" | "still"
    in_motion: float
    out_motion: float
    ratio: float
    verdict: str  # "yes" | "weak" | "no"


class ClipVerification(BaseModel):
    """Result of grafik.motion.verify.verify_clip for one ClipRecord.

    M5 additions (camera compensation) all default to the pre-M5 behaviour, so
    a verification persisted by M3 code reloads without migration.
    """

    verified_at: str  # ISO UTC timestamp
    frame_size: list[int]
    frames_sampled: int
    # RAW (uncompensated) mean frame-to-frame diff. Semantics deliberately
    # UNCHANGED across M5 so numbers stay comparable with M3 verifications --
    # the post-compensation figure is residual_global_motion.
    global_motion: float
    elements: list[ElementVerdict] = Field(default_factory=list)
    summary: str  # human-readable summary (Czech)
    # True when at least one sampled frame was successfully aligned to frame 0
    # by grafik.motion.verify (ECC affine estimate on the background).
    camera_compensated: bool = False
    compensated_frames: int = 0
    # Mean background diff AFTER alignment; None when nothing was compensated.
    # residual << global_motion is the signal that the camera (not the scene)
    # produced most of the raw motion.
    residual_global_motion: float | None = None
    # "submit" = every element mask came from ClipRecord.mask_paths (the layer
    # footprint AT SUBMIT TIME); "current" = at least one was re-rendered from
    # the layer's present state, so a layer moved since submit is measured in
    # the wrong place.
    mask_source: str = "current"


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
    verification: ClipVerification | None = None
    # layer_id -> path (relative to the project dir) of the layer's full-canvas
    # footprint mask, rendered AT SUBMIT TIME by grafik.motion.jobs. Verification
    # runs minutes later, by which time the user may have moved/scaled/deleted
    # the layer -- re-deriving the mask from the layer's present state would
    # then measure the wrong region of the clip. Empty dict = pre-M5 record;
    # verify falls back to the layer's current footprint.
    mask_paths: dict[str, str] = Field(default_factory=dict)
