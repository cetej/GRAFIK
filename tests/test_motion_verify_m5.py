"""Tests for M5 clip verification: camera compensation + submit-time masks.

Fully offline and deterministic -- np.random.default_rng(0) builds the
background texture, grafik.motion.verify.sample_frames is monkeypatched with
synthetic PIL frames, and the fal boundaries (_upload/_submit) are
monkeypatched exactly like tests/test_api_m3.py does. No network, no ffmpeg.

The scene reproduces the M3 E2E failure (docs/spikes/2026-08-14-m3-e2e-sc2.md):
a global camera zoom on top of a per-element move. Uncompensated, the zoom
lands in BOTH the inside-mask and outside-mask numbers, ratio collapses to ~1
and a correctly moving element scores "hýbal se jen slabě". The frames are
built at canvas resolution so no mask resizing is involved -- the thing under
test is the alignment, not the (separately covered) resize approximation.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest
from PIL import Image

import grafik.motion.jobs as jobs_mod
import grafik.motion.verify as verify_mod
from grafik.core.layer import Layer
from grafik.core.motion import ClipRecord, LayerMotion, MotionSpec
from grafik.core.project import LayerProject

CANVAS = 512
SQUARE = 60  # element edge, px
SQUARE_ORIGIN = (100, 100)
MASK_PAD = 2  # the layer's alpha footprint is a couple of px wider than the drawn square
ELEMENT_STEP = 8  # px the element travels per sampled frame
ZOOM_STEP = 0.02  # camera scale added per sampled frame: 1.00 -> 1.08 over 5
FRAME_COUNT = 5


# ---------------------------------------------------------------------------
# Synthetic scene (camera tests)
# ---------------------------------------------------------------------------


def _background() -> np.ndarray:
    """Multi-octave deterministic texture.

    ECC is a gradient-based estimator with no image pyramid, so it needs
    structure at a scale comparable to the displacement it has to recover
    (~20 px at the edges for an 8 % zoom). Per-pixel white noise would give it
    only high-frequency detail and no capture range; upsampled coarse noise
    (8/16/32 cells) gives smooth, well-conditioned gradients -- and is a much
    fairer stand-in for real footage than a flat fill.
    """
    rng = np.random.default_rng(0)
    texture = np.zeros((CANVAS, CANVAS), dtype=np.float32)
    for cells, amplitude in ((8, 90.0), (16, 40.0), (32, 20.0)):
        coarse = rng.random((cells, cells)).astype(np.float32)
        texture += cv2.resize(coarse, (CANVAS, CANVAS), interpolation=cv2.INTER_CUBIC) * amplitude
    return np.clip(texture + 40.0, 0, 255)


def _scene(index: int, moving: bool) -> np.ndarray:
    """Background + a bright square, optionally displaced by `index` steps.

    The square's edges are softened (Gaussian, sigma 1.5) so that resampling it
    twice -- once to zoom the frame, once to align it back -- does not leave a
    hard-edge ringing artefact that would masquerade as element motion.
    """
    img = _background()
    x0 = SQUARE_ORIGIN[0] + (ELEMENT_STEP * index if moving else 0)
    y0 = SQUARE_ORIGIN[1]
    patch = np.zeros((CANVAS, CANVAS), dtype=np.float32)
    patch[y0:y0 + SQUARE, x0:x0 + SQUARE] = 1.0
    patch = cv2.GaussianBlur(patch, (0, 0), 1.5)
    return np.clip(img * (1.0 - patch) + 235.0 * patch, 0, 255)


def _apply_camera(img: np.ndarray, scale: float) -> np.ndarray:
    """Global affine zoom about the frame centre -- the camera move that broke
    M3 verification (CameraMove.ZOOM_IN)."""
    matrix = cv2.getRotationMatrix2D((CANVAS / 2, CANVAS / 2), 0, scale)
    return cv2.warpAffine(img, matrix, (CANVAS, CANVAS), flags=cv2.INTER_LINEAR)


def _camera_frames(moving: bool = True, zoom_step: float = ZOOM_STEP) -> list[Image.Image]:
    frames = []
    for k in range(FRAME_COUNT):
        img = _scene(k, moving=moving)
        if zoom_step:
            img = _apply_camera(img, 1.0 + zoom_step * k)
        frames.append(Image.fromarray(img.astype(np.uint8), mode="L").convert("RGB"))
    return frames


# ---------------------------------------------------------------------------
# Projects / clips
# ---------------------------------------------------------------------------


def _project(tmp_path, canvas: int, box: tuple[int, int, int, int], name="m5"):
    """One canvas-sized layer, opaque only inside `box`."""
    project_dir = tmp_path / f"{name}.grafik"
    project = LayerProject.new(name, canvas, canvas)
    layer = Layer(name="Square")
    arr = np.zeros((canvas, canvas, 4), dtype=np.uint8)
    x0, y0, x1, y1 = box
    arr[y0:y1, x0:x1] = (200, 50, 50, 255)
    layer.save_image(Image.fromarray(arr, mode="RGBA"), project_dir)
    project.add_layer(layer)
    project.save(project_dir)
    return project, project_dir, layer


def _scene_project(tmp_path, box=None):
    if box is None:
        x0, y0 = SQUARE_ORIGIN[0] - MASK_PAD, SQUARE_ORIGIN[1] - MASK_PAD
        box = (x0, y0, x0 + SQUARE + 2 * MASK_PAD, y0 + SQUARE + 2 * MASK_PAD)
    return _project(tmp_path, CANVAS, box)


FLAT_CANVAS = 128
FLAT_BOX = (16, 16, 48, 48)


def _flat_project(tmp_path):
    return _project(tmp_path, FLAT_CANVAS, FLAT_BOX, name="m5-flat")


def _flat_frames(box=FLAT_BOX, delta=50, base=100, n=FRAME_COUNT) -> list[Image.Image]:
    """Frame 0 flat, later frames differing ONLY inside `box` -- an exact,
    known in/out signal (texture-less on purpose: ECC cannot converge on it, so
    these tests also cover the "compensation unavailable" degradation path)."""
    x0, y0, x1, y1 = box
    frames = [Image.fromarray(np.full((FLAT_CANVAS, FLAT_CANVAS, 3), base, np.uint8), mode="RGB")]
    for _ in range(n - 1):
        arr = np.full((FLAT_CANVAS, FLAT_CANVAS, 3), base, np.uint8)
        arr[y0:y1, x0:x1] = base + delta
        frames.append(Image.fromarray(arr, mode="RGB"))
    return frames


def _clip(layer_id: str, static: bool) -> ClipRecord:
    return ClipRecord(
        provider_id="kling-26-pro",
        endpoint="fal-ai/kling-video/v2.6/pro/image-to-video",
        status="completed",
        path="clips/fake.mp4",
        motion=MotionSpec(layer_motions={layer_id: LayerMotion(static=static)}),
    )


def _verify(monkeypatch, project, project_dir, clip, frames):
    monkeypatch.setattr(verify_mod, "sample_frames", lambda video_path, count=5: frames)
    return verify_mod.verify_clip(project, project_dir, clip)


# ---------------------------------------------------------------------------
# 1. Camera zoom + a genuinely moving element -- the sc-2 regression
# ---------------------------------------------------------------------------


def test_moving_element_under_camera_zoom_is_credited(tmp_path, monkeypatch):
    project, project_dir, layer = _scene_project(tmp_path)
    frames = _camera_frames(moving=True)
    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=False), frames)

    assert result.camera_compensated is True
    assert result.compensated_frames == FRAME_COUNT - 1
    assert result.residual_global_motion is not None
    # The zoom dominates the raw whole-frame diff; after alignment the
    # background is quiet again (measured ~6.98 raw vs ~2.13 residual).
    assert result.residual_global_motion * 3 <= result.global_motion

    e = result.elements[0]
    assert e.wanted == "move"
    assert e.verdict == "yes"
    assert e.in_motion >= verify_mod._IN_MOTION_HIGH
    assert e.ratio >= verify_mod._RATIO_STRONG
    # sc-2 measured ratio 0.95 uncompensated; compensation must lift it clear
    # of the threshold, not merely nudge it.
    assert e.ratio > 5.0
    assert "kamera kompenzována" in result.summary


def test_moving_element_under_camera_zoom_would_fail_uncompensated(tmp_path, monkeypatch):
    """The control for the test above: with compensation suppressed (the
    element mask covers so much of the frame that there is no background to
    fit), the same footage reproduces the sc-2 verdict."""
    project, project_dir, layer = _scene_project(tmp_path, box=(2, 2, CANVAS - 2, CANVAS - 2))
    frames = _camera_frames(moving=True)
    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=False), frames)

    assert result.camera_compensated is False
    assert result.elements[0].ratio < verify_mod._RATIO_STRONG
    assert result.elements[0].verdict == "weak"


# ---------------------------------------------------------------------------
# 2. Camera zoom + a static element -- exactly what M3 mis-scored
# ---------------------------------------------------------------------------


def test_static_element_under_camera_zoom_is_not_blamed(tmp_path, monkeypatch):
    project, project_dir, layer = _scene_project(tmp_path)
    frames = _camera_frames(moving=False)
    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=True), frames)

    assert result.camera_compensated is True
    e = result.elements[0]
    assert e.wanted == "still"
    assert e.verdict == "yes"
    assert e.in_motion < verify_mod._IN_MOTION_LOW
    # Uncompensated this element would have carried the whole zoom (the raw
    # whole-frame motion is well past the "no" threshold) and been reported as
    # having moved when it never did.
    assert result.global_motion >= verify_mod._IN_MOTION_HIGH


# ---------------------------------------------------------------------------
# 3. No camera move -- compensation must not disturb the M3 answer
# ---------------------------------------------------------------------------


def test_moving_element_without_camera_still_verifies(tmp_path, monkeypatch):
    project, project_dir, layer = _scene_project(tmp_path)
    frames = _camera_frames(moving=True, zoom_step=0.0)
    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=False), frames)

    e = result.elements[0]
    assert e.verdict == "yes"
    assert e.in_motion >= verify_mod._IN_MOTION_HIGH
    assert e.ratio >= verify_mod._RATIO_STRONG
    # ECC converges to (near) identity on a still background: aligning must not
    # invent motion, so the element still stands far above its surroundings.
    assert result.residual_global_motion is not None
    assert result.residual_global_motion < e.in_motion / 5


# ---------------------------------------------------------------------------
# 4. Guard -- not enough background to estimate a camera from
# ---------------------------------------------------------------------------


def test_oversized_element_mask_skips_compensation(tmp_path, monkeypatch):
    """A mask covering >80 % of the frame leaves no static reference; fitting a
    global transform to it would absorb the element's own motion. Compensation
    is skipped and verification degrades to the M3 behaviour."""
    project, project_dir, layer = _scene_project(tmp_path, box=(10, 10, CANVAS - 10, CANVAS - 10))
    frames = _camera_frames(moving=True)
    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=False), frames)

    assert result.camera_compensated is False
    assert result.compensated_frames == 0
    assert result.residual_global_motion is None
    assert "kamera kompenzována" not in result.summary
    assert result.elements[0].in_motion > 0  # measured, not crashed


def test_texture_less_footage_degrades_without_crashing(tmp_path, monkeypatch):
    """ECC raises cv2.error ("NaN encountered") on a flat template. Every frame
    then falls back to the raw diff -- the numbers must match the M3 pipeline
    exactly."""
    project, project_dir, layer = _flat_project(tmp_path)
    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=False), _flat_frames())

    assert result.camera_compensated is False
    assert result.compensated_frames == 0
    e = result.elements[0]
    assert e.in_motion == pytest.approx(50.0, abs=0.5)
    assert e.out_motion == pytest.approx(0.0, abs=0.5)
    assert e.verdict == "yes"


# ---------------------------------------------------------------------------
# 5. Submit-time masks: the layer moves while the job is running
# ---------------------------------------------------------------------------


def test_submit_snapshots_masks_and_verify_measures_the_old_position(tmp_path, monkeypatch):
    project, project_dir, layer = _flat_project(tmp_path)
    monkeypatch.setattr(jobs_mod, "_upload", lambda path: "https://fake-cdn.example.com/in.png")
    monkeypatch.setattr(jobs_mod, "_submit", lambda endpoint, payload: "req-m5-1")

    spec = MotionSpec(duration="5", layer_motions={layer.id: LayerMotion(static=False)})
    record = jobs_mod.submit_video_job(project, project_dir, spec, "kling-26-pro")

    assert record.mask_paths == {layer.id: f"clips/{record.id}-mask-{layer.id}.png"}
    mask_file = project_dir / record.mask_paths[layer.id]
    assert mask_file.exists()
    reloaded = LayerProject.load(project_dir)
    assert reloaded.clips[0].mask_paths == record.mask_paths

    # ... and now the user drags the layer while the clip is still generating.
    layer.x += 64
    project.save(project_dir)
    record.status = "completed"
    record.path = "clips/fake.mp4"

    # The generated footage moves what was at the ORIGINAL position (that is
    # the composite the provider actually received).
    frames = _flat_frames()
    result = _verify(monkeypatch, project, project_dir, record, frames)

    assert result.mask_source == "submit"
    assert "maska ze submitu" in result.summary
    e = result.elements[0]
    assert e.in_motion == pytest.approx(50.0, abs=0.5)
    assert e.out_motion == pytest.approx(0.0, abs=0.5)
    assert e.verdict == "yes"

    # Counterfactual: the M3 path (current footprint) points 64 px to the right
    # of where anything happened and reports the element as motionless.
    stale = record.model_copy(update={"mask_paths": {}})
    stale_result = _verify(monkeypatch, project, project_dir, stale, frames)
    assert stale_result.mask_source == "current"
    assert stale_result.elements[0].in_motion == pytest.approx(0.0, abs=0.5)
    assert stale_result.elements[0].verdict == "no"


def test_submit_skips_masks_for_layers_missing_from_project(tmp_path, monkeypatch):
    project, project_dir, layer = _flat_project(tmp_path)
    monkeypatch.setattr(jobs_mod, "_upload", lambda path: "https://fake-cdn.example.com/in.png")
    monkeypatch.setattr(jobs_mod, "_submit", lambda endpoint, payload: "req-m5-2")

    spec = MotionSpec(
        duration="5",
        layer_motions={layer.id: LayerMotion(static=True), "ghost-layer": LayerMotion(static=True)},
    )
    record = jobs_mod.submit_video_job(project, project_dir, spec, "kling-26-pro")

    assert set(record.mask_paths) == {layer.id}


# ---------------------------------------------------------------------------
# 6. Pre-M5 records
# ---------------------------------------------------------------------------


def test_clip_record_without_mask_paths_falls_back_to_current(tmp_path, monkeypatch):
    """A ClipRecord persisted by M3 has no mask_paths key at all."""
    project, project_dir, layer = _flat_project(tmp_path)
    clip = ClipRecord.model_validate({
        "id": "oldclip00001",
        "provider_id": "kling-26-pro",
        "endpoint": "fal-ai/kling-video/v2.6/pro/image-to-video",
        "status": "completed",
        "path": "clips/fake.mp4",
        "motion": {"layer_motions": {layer.id: {"static": False}}},
    })
    assert clip.mask_paths == {}

    result = _verify(monkeypatch, project, project_dir, clip, _flat_frames())

    assert result.mask_source == "current"
    assert "maska z aktuálního stavu" in result.summary
    assert result.elements[0].in_motion == pytest.approx(50.0, abs=0.5)
    assert result.elements[0].verdict == "yes"


def test_missing_mask_file_falls_back_to_current(tmp_path, monkeypatch):
    """mask_paths survives project duplication/restore, the PNGs may not."""
    project, project_dir, layer = _flat_project(tmp_path)
    clip = _clip(layer.id, static=False)
    clip.mask_paths = {layer.id: "clips/gone-mask.png"}

    result = _verify(monkeypatch, project, project_dir, clip, _flat_frames())

    assert result.mask_source == "current"
    assert result.elements[0].in_motion == pytest.approx(50.0, abs=0.5)


# ---------------------------------------------------------------------------
# 6. Large zoom -- the feature-based (ORB + RANSAC) alignment path
# ---------------------------------------------------------------------------
# The smooth-octave _background() has no ORB corners, so every test above
# exercises the ECC-only regime. Real footage (M3 sc-2 re-measurement,
# 2026-08-15) needs the feature path: a prompt-compiled zoom_in 0.25 came back
# as a ~3.5x push-in plus a +24/255 exposure drift, where identity-seeded ECC
# settles into a near-identity local minimum. This scene rebuilds that regime
# synthetically: corner-rich block mosaic, 1.0 -> 1.6 zoom, brightness drift.


def _blocky_background() -> np.ndarray:
    """Nearest-neighbour upscaled coarse noise -- sharp block corners for ORB."""
    rng = np.random.default_rng(7)
    coarse = (rng.random((32, 32)) * 200 + 30).astype(np.float32)
    return cv2.resize(coarse, (CANVAS, CANVAS), interpolation=cv2.INTER_NEAREST)


def test_large_zoom_uses_feature_alignment(tmp_path, monkeypatch):
    project, project_dir, layer = _scene_project(tmp_path)

    frames = []
    n = 6
    for k in range(n):
        img = _blocky_background()
        x0 = SQUARE_ORIGIN[0] + 10 * k
        y0 = SQUARE_ORIGIN[1]
        patch = np.zeros((CANVAS, CANVAS), dtype=np.float32)
        patch[y0:y0 + SQUARE, x0:x0 + SQUARE] = 1.0
        patch = cv2.GaussianBlur(patch, (0, 0), 1.5)
        img = np.clip(img * (1.0 - patch) + 235.0 * patch, 0, 255)
        img = _apply_camera(img, 1.0 + 0.12 * k)  # 1.0 -> 1.6: far beyond ECC's basin
        img = np.clip(img + 4.0 * k, 0, 255)  # generative-style exposure drift
        frames.append(Image.fromarray(img.astype(np.uint8), mode="L").convert("RGB"))

    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=False), frames)

    assert result.camera_compensated is True
    assert result.compensated_frames == n - 1
    assert result.residual_global_motion is not None
    # Alignment + luminance offset must strip most of the zoom+drift signal.
    assert result.residual_global_motion < result.global_motion / 2
    element = result.elements[0]
    assert element.verdict == "yes"
    assert element.ratio >= 1.2
