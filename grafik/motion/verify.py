"""Post-generation pixel-diff verification for motion clips.

Ideal-state criterion #8, "hybalo se to, co melo" (docs/plans/ideal-state-unified-editor.md):
the closed-loop check docs/plans/2026-08-14-phase1-gate.md (A3 amendment)
proposed in place of API-level per-element motion control. Since no fal.ai
I2V endpoint accepts a mask/trajectory payload, the only way to confirm a
generated clip actually moved (or held still) the intended element is to
diff its frames against that element's mask after the fact.

M5 -- camera compensation. A naive frame-to-frame diff cannot tell "the
element moved" from "the camera moved, so everything moved". The M3 E2E clip
(docs/spikes/2026-08-14-m3-e2e-sc2.md: camera zoom_in 0.25 + a moving element)
measured in=52.5 / out=55.5 / ratio=0.95 and was scored "hybal se jen slabe"
even though the element did exactly what was asked -- the global zoom drowned
out the per-element signal in BOTH numbers. So before diffing, each sampled
frame is registered back onto frame 0 by an estimate of the global (camera)
transform, and the diff is taken on the aligned frames.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import cv2
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

# --- camera compensation (M5) ----------------------------------------------
# MOTION_AFFINE, not MOTION_EUCLIDEAN: the camera moves we compile prompts for
# include zoom_in/zoom_out, which is a SCALE -- euclidean (rotation+translation)
# cannot represent it, and would leave the whole zoom in the residual, i.e.
# exactly the failure this compensation exists to fix. Affine additionally
# absorbs the mild shear/perspective that generative I2V introduces on a dolly.
_ECC_CRITERIA = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-6)
_ECC_GAUSS_FILT_SIZE = 5
# The element masks are dilated before being cut out of the background, so a
# soft/AA element edge or a slight mask misalignment cannot feed the element's
# own motion into the camera estimate. Scales with frame height, floor 15 px.
_BG_DILATE_MIN_PX = 15
_BG_DILATE_HEIGHT_DIVISOR = 48
# With less background than this there is not enough static structure left to
# estimate a global transform from -- compensation is skipped rather than
# fitted to the moving element itself.
_MIN_BG_FRACTION = 0.20
# Warping frame k back onto frame 0 pulls in undefined pixels at the borders
# (constant 0). A white frame pushed through the same warp marks which output
# pixels are fully covered; anything below this (bilinear edge blend) is
# excluded from every statistic, so the border does not read as "motion".
_VALID_COVERAGE = 250.0

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


class _Element(NamedTuple):
    """One layer's verification input: which region to measure, and where that
    region came from (submit-time snapshot vs. the layer's current state).

    Resolved for EVERY entry in the clip's layer_motions, including the two
    unmeasurable cases, so the summary can be emitted in the original layer
    order after the camera estimate (which needs all masks up front) has run.
    """

    layer_id: str
    layer: Layer | None  # None -- the layer is no longer in the project
    wanted: str  # "move" | "still"
    mask: np.ndarray | None  # bool, frame-sized; None -- empty footprint
    source: str  # "submit" | "current"


def _mask_to_frame(mask_canvas: Image.Image, frame_size: list[int]) -> np.ndarray:
    """Canvas-space "L" mask -> frame-sized boolean array.

    The provider's output resolution routinely differs from the project canvas,
    so the mask is stretched onto the frame instead of being regenerated there
    -- an approximation (see verify_clip's note), applied identically to
    submit-time and current masks so the two paths stay comparable.
    """
    resized = mask_canvas.convert("L").resize((frame_size[0], frame_size[1]), Image.LANCZOS)
    return np.asarray(resized.point(lambda a: 255 if a > 127 else 0)) > 0


def _background_mask(elements: list[_Element], height: int, width: int) -> np.ndarray:
    """uint8 0/255 mask of everything the camera estimate may look at.

    Elements that were asked to MOVE are cut out (dilated) -- fitting a global
    transform to them would partly absorb the very motion we are trying to
    measure. Elements asked to stay STILL are deliberately left in: they are
    rigid with the background and their structure helps the estimate converge.
    """
    union = np.zeros((height, width), dtype=np.uint8)
    for element in elements:
        if element.wanted == "move" and element.mask is not None:
            union[element.mask] = 255
    ksize = max(_BG_DILATE_MIN_PX, height // _BG_DILATE_HEIGHT_DIVISOR)
    dilated = cv2.dilate(union, np.ones((ksize, ksize), dtype=np.uint8))
    return np.where(dilated > 0, np.uint8(0), np.uint8(255))


def _align_to_first(gray: list[np.ndarray], bg_mask: np.ndarray) -> tuple[list[np.ndarray], list[np.ndarray], int]:
    """Register every frame after the first back onto frame 0.

    Returns (aligned frames for k>0, per-frame validity masks, count of frames
    actually compensated).

    findTransformECC yields the warp mapping TEMPLATE (frame 0) coordinates to
    INPUT (frame k) coordinates, so frame k is pulled back with WARP_INVERSE_MAP
    -- the alignment direction used by OpenCV's own ECC sample.

    A frame that cannot be registered (cv2.error "NaN encountered" on
    texture-less footage, non-convergence, or a non-finite warp) is passed
    through UNCHANGED with full validity and is not counted: verification
    degrades to the pre-M5 raw diff for that frame instead of failing.
    """
    height, width = gray[0].shape
    template = gray[0].astype(np.float32)
    coverage_probe = np.full((height, width), 255.0, dtype=np.float32)
    full_valid = np.ones((height, width), dtype=bool)

    aligned: list[np.ndarray] = []
    valids: list[np.ndarray] = []
    compensated = 0

    for frame in gray[1:]:
        source = frame.astype(np.float32)
        warp = np.eye(2, 3, dtype=np.float32)
        ok = True
        try:
            _cc, warp = cv2.findTransformECC(
                templateImage=template,
                inputImage=source,
                warpMatrix=warp,
                motionType=cv2.MOTION_AFFINE,
                criteria=_ECC_CRITERIA,
                inputMask=bg_mask,
                gaussFiltSize=_ECC_GAUSS_FILT_SIZE,
            )
            ok = bool(np.isfinite(warp).all())
        except cv2.error:
            ok = False

        if not ok:
            aligned.append(frame)
            valids.append(full_valid)
            continue

        flags = cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP
        warped = cv2.warpAffine(source, warp, (width, height), flags=flags)
        coverage = cv2.warpAffine(coverage_probe, warp, (width, height), flags=flags)
        aligned.append(warped.astype(np.float64))
        valids.append(coverage > _VALID_COVERAGE)
        compensated += 1

    return aligned, valids, compensated


def _masked_mean(diffs: list[np.ndarray], valids: list[np.ndarray], region: np.ndarray) -> float:
    """Mean diff over `region`, per frame, averaged across frames.

    Border pixels that the alignment left undefined are dropped from the
    selection; a frame whose selection ends up empty contributes nothing rather
    than a fake zero.
    """
    per_frame = [float(d[sel].mean()) for d, v in zip(diffs, valids) if (sel := region & v).any()]
    return float(np.mean(per_frame)) if per_frame else 0.0


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


def _element_mask(
    project: LayerProject, project_dir: Path, clip: ClipRecord, layer: Layer
) -> tuple[Image.Image, str]:
    """The layer footprint to measure, preferring the SUBMIT-TIME snapshot.

    ClipRecord.mask_paths is written by grafik.motion.jobs.submit_video_job.
    Verification happens minutes later, so the layer on disk may since have
    been moved, scaled or repainted -- measuring the clip against its present
    footprint would then diff the wrong region entirely. A missing entry (a
    pre-M5 record) or a missing file falls back to the current footprint,
    which is what M3 always did; the caller records which one was used.
    """
    relative = clip.mask_paths.get(layer.id, "")
    if relative:
        path = project_dir / relative
        if path.exists():
            with Image.open(path) as img:
                return img.convert("L"), "submit"
    return layer_mask_on_canvas(project, project_dir, layer), "current"


def verify_clip(project: LayerProject, project_dir: Path, clip: ClipRecord) -> ClipVerification:
    """Pixel-diff a completed clip's frames against each moving/static
    layer's mask (ideal-state criterion #8) -- grayscale mean absolute diff
    from the first sampled frame, inside vs. outside the layer's mask, AFTER
    the frames have been registered onto frame 0 to cancel camera motion (M5).

    Two M5 corrections to the M3 measurement, both aimed at the sc-2 failure
    (a correctly moving element scored "weak" under a global zoom):

    1. Camera. The global transform is estimated with ECC on the background
       only (moving elements dilated out, static ones kept as anchors) and
       every frame is pulled back onto frame 0 before diffing, so in/out no
       longer both contain the camera's contribution. `global_motion` stays
       RAW for continuity with M3 records; `residual_global_motion` reports
       what is left of the background after alignment. If there is too little
       background to fit on, or ECC cannot converge, the frame is diffed
       uncompensated -- identical to M3 behaviour, never a hard failure.
    2. Masks. Element footprints come from the submit-time snapshot when the
       clip has one (see _element_mask), not from the layer's current state.

    NOTE: the sampled frame size is the PROVIDER's output resolution, which
    commonly differs from the project canvas (providers resize/crop the
    input image). The canvas mask is resized onto each frame's actual size
    rather than regenerated at that size, so this is an approximation, not a
    pixel-exact mapping -- good enough for a "did roughly the right thing
    move" signal, not a precise measurement.
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
    # RAW diffs -- global_motion keeps its M3 meaning (uncompensated), so a
    # verification made before and after M5 stays comparable.
    global_motion = float(np.mean([np.abs(g - gray[0]).mean() for g in gray[1:]]))

    layer_motions = clip.motion.layer_motions if clip.motion else {}
    height, width = gray[0].shape

    # Pass 1: resolve every layer's mask up front -- the camera estimate needs
    # to know which regions to ignore before any diff is taken. Iteration order
    # is preserved so the summary lines come out exactly as in M3.
    entries: list[_Element] = []
    sources: list[str] = []

    for layer_id, motion in layer_motions.items():
        wanted = "still" if motion.static else "move"
        layer = project.get_layer(layer_id)
        if layer is None:
            entries.append(_Element(layer_id, None, wanted, None, "current"))
            continue

        mask_canvas, source = _element_mask(project, project_dir, clip, layer)
        sources.append(source)
        mask_arr = _mask_to_frame(mask_canvas, frame_size)
        entries.append(_Element(layer_id, layer, wanted, mask_arr if mask_arr.any() else None, source))

    # Pass 2: camera compensation, then the diffs everything else is built on.
    bg_mask = _background_mask(entries, height, width)
    bg_bool = bg_mask > 0
    enough_background = float(bg_bool.mean()) >= _MIN_BG_FRACTION

    if enough_background:
        aligned, valids, compensated_frames = _align_to_first(gray, bg_mask)
    else:
        aligned = gray[1:]
        valids = [np.ones((height, width), dtype=bool)] * len(gray[1:])
        compensated_frames = 0

    diffs = [np.abs(a - gray[0]) for a in aligned]
    camera_compensated = compensated_frames > 0
    residual = _masked_mean(diffs, valids, bg_bool) if camera_compensated else None

    # Pass 3: verdicts, in the original layer order.
    elements: list[ElementVerdict] = []
    lines: list[str] = []

    for element in entries:
        if element.layer is None:
            lines.append(f"vrstva {element.layer_id} nenalezena v projektu, přeskočeno")
            continue
        if element.mask is None:
            elements.append(ElementVerdict(
                layer_id=element.layer_id, layer_name=element.layer.name, wanted=element.wanted,
                in_motion=0.0, out_motion=0.0, ratio=0.0, verdict="no",
            ))
            lines.append(f"{element.layer.name}: prázdná maska, nelze ověřit")
            continue

        in_motion = _masked_mean(diffs, valids, element.mask)
        out_motion = _masked_mean(diffs, valids, ~element.mask)
        ratio = in_motion / (out_motion + 1e-6)
        verdict = _verdict_for(element.wanted, in_motion, ratio)

        elements.append(ElementVerdict(
            layer_id=element.layer_id, layer_name=element.layer.name, wanted=element.wanted,
            in_motion=in_motion, out_motion=out_motion, ratio=ratio, verdict=verdict,
        ))
        lines.append(f"{element.layer.name}: {_VERDICT_PHRASES[(element.wanted, verdict)]}")

    mask_source = "submit" if sources and all(s == "submit" for s in sources) else "current"
    if sources:
        lines.append(
            "maska ze submitu" if mask_source == "submit" else "maska z aktuálního stavu"
        )
    if camera_compensated:
        # "raw celý snímek": global_motion averages the WHOLE frame while the
        # residual averages the background only -- spelled out so a reader does
        # not take the pair for a like-for-like before/after.
        lines.append(
            f"kamera kompenzována (affine, {compensated_frames}/{len(diffs)} snímků), "
            f"zbytkový pohyb pozadí {residual:.2f} (raw celý snímek {global_motion:.2f})"
        )
    lines.append(f"celkový pohyb v obraze: {global_motion:.2f}")
    summary = "; ".join(lines) + "."

    return ClipVerification(
        verified_at=_now_iso(),
        frame_size=frame_size,
        frames_sampled=len(frames),
        global_motion=global_motion,
        elements=elements,
        summary=summary,
        camera_compensated=camera_compensated,
        compensated_frames=compensated_frames,
        residual_global_motion=residual,
        mask_source=mask_source,
    )
