"""Deterministic MotionSpec -> prompt compiler. No LLM, no network calls.

Compiles per-layer trajectory/static/description plus global camera intent
into one structured English prompt for prompt-only I2V providers (current
fal schemas — kling v2.6/v3 pro, seedance-2.5 — accept {prompt, image_url,
duration}; nothing mask-shaped exists on a verified endpoint today). See
docs/plans/2026-08-14-phase1-gate.md (A3 amendment) for why this replaced
the originally-planned Kling dynamic_masks payload mapper.
"""

from __future__ import annotations

import math

from grafik.core.layer import Layer
from grafik.core.motion import CameraMove, CameraSpec, LayerMotion, MotionSpec, TrajectoryPoint
from grafik.core.project import LayerProject

# 8-way compass words for the first->last trajectory vector, in image/canvas
# coordinates (y grows downward). Index 0 = right (0 deg), then +45 deg steps.
_DIRECTIONS = ["right", "down-right", "down", "down-left", "left", "up-left", "up", "up-right"]

_DIRECTION_PHRASE = {
    "right": "to the right",
    "left": "to the left",
    "up": "upward",
    "down": "downward",
    "up-right": "to the upper right",
    "up-left": "to the upper left",
    "down-right": "to the lower right",
    "down-left": "to the lower left",
}

_CAMERA_PHRASE = {
    CameraMove.PAN_LEFT: "pans left",
    CameraMove.PAN_RIGHT: "pans right",
    CameraMove.TILT_UP: "tilts up",
    CameraMove.TILT_DOWN: "tilts down",
    CameraMove.ZOOM_IN: "zooms in",
    CameraMove.ZOOM_OUT: "zooms out",
}

# Distance relative to canvas diagonal below which movement reads as "mildly".
_MILD_DISTANCE_RATIO = 0.15


def estimate_direction(points: list[TrajectoryPoint]) -> str:
    """8-way compass word for the vector from the first to the last point.

    Returns "" when there are fewer than 2 points, or the first and last
    point coincide (no vector to derive a direction from).
    """
    if len(points) < 2:
        return ""
    dx = points[-1].x - points[0].x
    dy = points[-1].y - points[0].y
    if dx == 0 and dy == 0:
        return ""
    angle = math.degrees(math.atan2(dy, dx)) % 360
    idx = round(angle / 45) % 8
    return _DIRECTIONS[idx]


def _trajectory_distance(points: list[TrajectoryPoint]) -> float:
    if len(points) < 2:
        return 0.0
    return math.hypot(points[-1].x - points[0].x, points[-1].y - points[0].y)


def _distance_word(distance: float, diagonal: float) -> str:
    ratio = (distance / diagonal) if diagonal > 0 else 0.0
    return "mildly" if ratio < _MILD_DISTANCE_RATIO else "strongly"


def _camera_adverb(magnitude: float) -> str:
    if magnitude < 1 / 3:
        return "slowly"
    if magnitude < 2 / 3:
        return "moderately"
    return "quickly"


def _compile_camera(camera: CameraSpec) -> str:
    if camera.move == CameraMove.NONE:
        return ""
    if camera.move == CameraMove.CUSTOM:
        return camera.prompt.strip()
    adverb = _camera_adverb(camera.magnitude)
    return f"the camera {adverb} {_CAMERA_PHRASE[camera.move]}"


def _layer_phrase(layer: Layer, motion: LayerMotion, diagonal: float) -> str:
    name = layer.name or "element"
    if motion.static:
        return f"{name} remains still"
    if motion.description:
        return f"{name} {motion.description}".strip()
    direction = estimate_direction(motion.trajectory)
    if not direction:
        return f"{name} moves subtly"
    distance = _trajectory_distance(motion.trajectory)
    word = _distance_word(distance, diagonal)
    return f"{name} moves {word} {_DIRECTION_PHRASE[direction]}"


def compile_motion_prompt(project: LayerProject, spec: MotionSpec) -> str:
    """Compile a MotionSpec into one fluent English prompt.

    Deterministic: the same (project, spec) always yields the same string.
    Only layers present in spec.layer_motions are mentioned; layers are
    visited in z_order (bottom to top) so output order never depends on
    dict insertion order.
    """
    diagonal = math.hypot(project.canvas_width, project.canvas_height)
    phrases: list[str] = []
    for layer in sorted(project.layers, key=lambda l: l.z_order):
        motion = spec.layer_motions.get(layer.id)
        if motion is None:
            continue
        phrases.append(_layer_phrase(layer, motion, diagonal))

    camera_phrase = _compile_camera(spec.camera)
    if camera_phrase:
        phrases.append(camera_phrase)

    if not phrases:
        return "The scene remains still."

    sentences = [p[0].upper() + p[1:] if p else p for p in phrases]
    return ". ".join(sentences) + "."


def build_video_payload(endpoint: str, image_url: str, prompt: str, duration: str) -> dict:
    """Minimal prompt-based I2V payload.

    Current fal I2V schemas (kling v2.6/pro, seedance-2.5) accept exactly
    these three fields — no mask/camera fields exist on any verified I2V
    endpoint today (docs/capabilities/kling-versions.md). `endpoint` is
    accepted for call-site symmetry (the caller already routes on it) but
    does not change the payload shape — do NOT add mask/camera fields here.
    """
    return {"prompt": prompt, "image_url": image_url, "duration": duration}
