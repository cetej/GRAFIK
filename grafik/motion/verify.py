"""Post-generation pixel-diff verification for motion clips.

Ideal-state criterion #8, "hybalo se to, co melo" (docs/plans/ideal-state-unified-editor.md):
the closed-loop check docs/plans/2026-08-14-phase1-gate.md (A3 amendment)
proposed in place of API-level per-element motion control. Since no fal.ai
I2V endpoint accepts a mask/trajectory payload, the only way to confirm a
generated clip actually moved (or held still) the intended element is to
diff its frames against that element's mask after the fact.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image

from grafik.core.composer import compose
from grafik.core.layer import Layer
from grafik.core.motion import ClipRecord, ClipVerification, ElementVerdict
from grafik.core.project import LayerProject

# sample_frames: fractions of the clip's estimated total frame count to keep.
_SAMPLE_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 0.98)
# Fallback total-frame guess, used only when fps/duration can't be read from
# the ffmpeg meta header (imageio_ffmpeg docs: both "can be zero if it could
# not be detected").
_FALLBACK_TOTAL_FRAMES = 150

# Verdict thresholds on grayscale 0-255 mean absolute diff. Tunable constants
# (module-level, not magic numbers) -- calibrated against synthetic
# move/still fixtures (tests/test_motion_verify.py), not real generated
# clips, so treat these as a starting point to retune once real footage
# exists.
_IN_MOTION_HIGH = 6.0
_IN_MOTION_LOW = 2.5
_RATIO_STRONG = 1.2

_VERDICT_PHRASES = {
    ("move", "yes"): "hýbal se, jak měl",
    ("move", "weak"): "hýbal se jen slabě",
    ("move", "no"): "zůstal nehybný, ačkoliv se měl hýbat",
    ("still", "yes"): "zůstal klidný, jak měl",
    ("still", "weak"): "mírně se pohnul, ačkoliv měl zůstat klidný",
    ("still", "no"): "hýbal se, ačkoliv měl zůstat klidný",
}


def sample_frames(video_path: Path, count: int = 5) -> list[Image.Image]:
    """Sample up to `count` frames spread across a clip, without holding the
    whole decoded stream in memory.

    imageio-ffmpeg bundles its own ffmpeg binary (pyproject.toml dependency
    -- plain `ffmpeg` is NOT required on PATH). `read_frames` is a generator
    whose first yield is a meta dict (`size`, `fps`, `duration`, ...); every
    yield after that is one raw RGB frame (bytes, length width*height*3).
    fps*duration estimates the total frame count up front, which turns the
    fixed fractions in _SAMPLE_FRACTIONS into target frame INDICES before any
    frame is decoded -- only the `count` selected frames are ever kept, the
    rest stream past and get discarded immediately. A stream that ends up
    shorter than estimated just ends the loop early; whatever was already
    collected is returned (this is the normal, non-error path for a short
    clip, not something callers need to special-case).
    """
    if count == len(_SAMPLE_FRACTIONS):
        fractions = _SAMPLE_FRACTIONS
    elif count <= 1:
        fractions = (0.0,)
    else:
        fractions = [i / (count - 1) for i in range(count)]

    gen = imageio_ffmpeg.read_frames(str(video_path))
    meta = next(gen)
    width, height = meta["size"]
    fps = meta.get("fps") or 0
    duration = meta.get("duration") or 0
    est_total = int(fps * duration) if fps and duration else _FALLBACK_TOTAL_FRAMES
    est_total = max(est_total, count)

    target_indices = sorted({min(est_total - 1, round(f * (est_total - 1))) for f in fractions})
    target_set = set(target_indices)
    last_target = target_indices[-1]

    frames: list[Image.Image] = []
    for idx, raw in enumerate(gen):
        if idx in target_set:
            arr = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
            frames.append(Image.fromarray(arr, mode="RGB"))
        if idx >= last_target:
            break
    return frames


def layer_mask_on_canvas(project: LayerProject, project_dir: Path, layer: Layer) -> Image.Image:
    """Full-canvas "L" mask of one layer's footprint, in the SAME transform
    space the renderer uses.

    LEARNINGS 2026-08-14 (hit-test finding): recomputing a layer's geometry
    independently of compose() drifted from what the client actually
    rendered. To avoid that class of bug here too, this deep-copies the
    project, hides every layer except the target one, and reuses compose()
    itself -- so width/height stretch and rotation match the renderer for
    free instead of being re-derived.
    """
    project_copy = project.model_copy(deep=True)
    for l in project_copy.layers:
        l.visible = l.id == layer.id
    composite = compose(project_copy, project_dir)
    alpha = composite.split()[-1]
    return alpha.point(lambda a: 255 if a > 127 else 0)


def _verdict_for(wanted: str, in_motion: float, ratio: float) -> str:
    if wanted == "move":
        if in_motion >= _IN_MOTION_HIGH and ratio >= _RATIO_STRONG:
            return "yes"
        if in_motion >= _IN_MOTION_LOW:
            return "weak"
        return "no"
    # wanted == "still"
    if in_motion < _IN_MOTION_LOW:
        return "yes"
    if in_motion < _IN_MOTION_HIGH:
        return "weak"
    return "no"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_clip(project: LayerProject, project_dir: Path, clip: ClipRecord) -> ClipVerification:
    """Pixel-diff a completed clip's frames against each moving/static
    layer's mask (ideal-state criterion #8) -- grayscale mean absolute diff
    from the first sampled frame, inside vs. outside the layer's mask.

    NOTE: the sampled frame size is the PROVIDER's output resolution, which
    commonly differs from the project canvas (providers resize/crop the
    input image). layer_mask_on_canvas is resized onto each frame's actual
    size rather than regenerated at that size, so this is an approximation,
    not a pixel-exact mapping -- good enough for a "did roughly the right
    thing move" signal, not a precise measurement.
    """
    frames = sample_frames(project_dir / clip.path)

    if len(frames) < 2:
        return ClipVerification(
            verified_at=_now_iso(),
            frame_size=list(frames[0].size) if frames else [0, 0],
            frames_sampled=len(frames),
            global_motion=0.0,
            elements=[],
            summary="Nedostatek snímků pro verifikaci (video se nepodařilo přečíst).",
        )

    frame_size = list(frames[0].size)
    gray = [np.asarray(f.convert("L"), dtype=np.float64) for f in frames]
    diffs = [np.abs(g - gray[0]) for g in gray[1:]]
    global_motion = float(np.mean([d.mean() for d in diffs]))

    layer_motions = clip.motion.layer_motions if clip.motion else {}
    elements: list[ElementVerdict] = []
    lines: list[str] = []

    for layer_id, motion in layer_motions.items():
        layer = project.get_layer(layer_id)
        if layer is None:
            lines.append(f"vrstva {layer_id} nenalezena v projektu, přeskočeno")
            continue

        wanted = "still" if motion.static else "move"
        mask_canvas = layer_mask_on_canvas(project, project_dir, layer)
        mask_resized = mask_canvas.resize((frame_size[0], frame_size[1]), Image.LANCZOS)
        mask_arr = np.asarray(mask_resized.point(lambda a: 255 if a > 127 else 0)) > 0

        if not mask_arr.any():
            elements.append(ElementVerdict(
                layer_id=layer_id, layer_name=layer.name, wanted=wanted,
                in_motion=0.0, out_motion=0.0, ratio=0.0, verdict="no",
            ))
            lines.append(f"{layer.name}: prázdná maska, nelze ověřit")
            continue

        in_motion = float(np.mean([d[mask_arr].mean() for d in diffs]))
        out_motion = float(np.mean([d[~mask_arr].mean() for d in diffs]))
        ratio = in_motion / (out_motion + 1e-6)
        verdict = _verdict_for(wanted, in_motion, ratio)

        elements.append(ElementVerdict(
            layer_id=layer_id, layer_name=layer.name, wanted=wanted,
            in_motion=in_motion, out_motion=out_motion, ratio=ratio, verdict=verdict,
        ))
        lines.append(f"{layer.name}: {_VERDICT_PHRASES[(wanted, verdict)]}")

    lines.append(f"celkový pohyb v obraze: {global_motion:.2f}")
    summary = "; ".join(lines) + "."

    return ClipVerification(
        verified_at=_now_iso(),
        frame_size=frame_size,
        frames_sampled=len(frames),
        global_motion=global_motion,
        elements=elements,
        summary=summary,
    )
