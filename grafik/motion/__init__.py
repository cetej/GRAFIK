"""grafik.motion — MotionSpec prompt compilation for image-to-video providers.

No current fal I2V endpoint accepts per-element mask+trajectory input (see
docs/plans/2026-08-14-phase1-gate.md, A3 amendment, 2026-08-14). MotionSpec
(grafik.core.motion) still captures per-layer trajectory/static/description
and camera intent from the UI; this package compiles that into a structured
English prompt instead of a Kling dynamic_masks payload. Mask/trajectory
data persists on LayerMotion/ClipRecord for post-generation verification,
not for provider input.
"""

from __future__ import annotations

from grafik.motion.compiler import build_video_payload, compile_motion_prompt, estimate_direction
from grafik.motion.jobs import refresh_video_job, submit_video_job

__all__ = [
    "compile_motion_prompt",
    "estimate_direction",
    "build_video_payload",
    "submit_video_job",
    "refresh_video_job",
]
