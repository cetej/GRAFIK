"""Tests for grafik.motion.verify -- pixel-diff clip verification (M3,
ideal-state criterion #8, docs/plans/2026-08-14-phase1-gate.md A3). Fully
offline: sample_frames (the only function that touches ffmpeg/disk) is
monkeypatched in every verify_clip test, so these exercise the actual
mask-generation + diff + verdict pipeline against synthetic frames with
known, exact deltas -- not real decoded video.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

import grafik.motion.verify as verify_mod
from grafik.core.layer import Layer
from grafik.core.motion import ClipRecord, LayerMotion, MotionSpec
from grafik.core.project import LayerProject
from grafik.motion.verify import layer_mask_on_canvas

CANVAS = (64, 64)
BOX = (16, 16, 48, 48)  # opaque square, centered, half the canvas each dim


def _project_with_layer(tmp_path, box=BOX, canvas=CANVAS):
    """One canvas-sized layer, opaque only inside `box` (RGBA fully opaque
    inside, fully transparent outside) -- gives layer_mask_on_canvas a known,
    exact footprint to test against."""
    project_dir = tmp_path / "verify-test.grafik"
    project = LayerProject.new("verify-test", canvas[0], canvas[1])
    layer = Layer(name="Square")
    arr = np.zeros((canvas[1], canvas[0], 4), dtype=np.uint8)
    x0, y0, x1, y1 = box
    arr[y0:y1, x0:x1] = (200, 50, 50, 255)
    layer.save_image(Image.fromarray(arr, mode="RGBA"), project_dir)
    project.add_layer(layer)
    project.save(project_dir)
    return project, project_dir, layer


def _frames(canvas=CANVAS, box=BOX, inside_delta=0, outside_delta=0, base=100, n=5):
    """A first frame at flat `base`, then n-1 frames with a constant delta
    applied inside/outside `box` -- verify_clip's per-t diffs then come out
    to exactly |inside_delta| / |outside_delta| for every sampled t>0 frame
    (R=G=B per pixel, so grayscale conversion is lossless)."""
    w, h = canvas
    x0, y0, x1, y1 = box
    frames = [Image.fromarray(np.full((h, w, 3), base, dtype=np.uint8), mode="RGB")]
    inside_val = int(np.clip(base + inside_delta, 0, 255))
    outside_val = int(np.clip(base + outside_delta, 0, 255))
    for _ in range(n - 1):
        arr = np.full((h, w, 3), outside_val, dtype=np.uint8)
        arr[y0:y1, x0:x1] = inside_val
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
# layer_mask_on_canvas
# ---------------------------------------------------------------------------


def test_layer_mask_on_canvas_matches_layer_alpha(tmp_path):
    project, project_dir, layer = _project_with_layer(tmp_path)
    mask = layer_mask_on_canvas(project, project_dir, layer)

    assert mask.mode == "L"
    assert mask.size == CANVAS
    mask_arr = np.array(mask)
    assert (mask_arr[16:48, 16:48] == 255).all()
    assert (mask_arr[0:16, 0:16] == 0).all()


# ---------------------------------------------------------------------------
# verify_clip -- wanted="move" (static=False)
# ---------------------------------------------------------------------------


def test_verify_clip_move_yes(tmp_path, monkeypatch):
    project, project_dir, layer = _project_with_layer(tmp_path)
    frames = _frames(inside_delta=50, outside_delta=0)
    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=False), frames)

    assert result.frame_size == [64, 64]
    assert result.frames_sampled == 5
    e = result.elements[0]
    assert e.layer_id == layer.id
    assert e.layer_name == "Square"
    assert e.wanted == "move"
    assert e.verdict == "yes"
    assert e.in_motion == pytest.approx(50.0, abs=0.5)
    assert e.out_motion == pytest.approx(0.0, abs=0.5)
    assert "Square" in result.summary


def test_verify_clip_move_weak_low_motion(tmp_path, monkeypatch):
    project, project_dir, layer = _project_with_layer(tmp_path)
    frames = _frames(inside_delta=4, outside_delta=0)
    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=False), frames)
    assert result.elements[0].verdict == "weak"


def test_verify_clip_move_weak_global_drift(tmp_path, monkeypatch):
    """Strong absolute motion but ratio < 1.2 (moves just as much outside the
    mask, e.g. camera drift) -- only "weak", not "yes"."""
    project, project_dir, layer = _project_with_layer(tmp_path)
    frames = _frames(inside_delta=50, outside_delta=50)
    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=False), frames)
    e = result.elements[0]
    assert e.in_motion >= 6.0
    assert e.ratio == pytest.approx(1.0, abs=0.05)
    assert e.verdict == "weak"


def test_verify_clip_move_no(tmp_path, monkeypatch):
    project, project_dir, layer = _project_with_layer(tmp_path)
    frames = _frames(inside_delta=1, outside_delta=0)
    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=False), frames)
    assert result.elements[0].verdict == "no"


# ---------------------------------------------------------------------------
# verify_clip -- wanted="still" (static=True)
# ---------------------------------------------------------------------------


def test_verify_clip_still_yes(tmp_path, monkeypatch):
    project, project_dir, layer = _project_with_layer(tmp_path)
    frames = _frames(inside_delta=0, outside_delta=0)
    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=True), frames)
    e = result.elements[0]
    assert e.wanted == "still"
    assert e.verdict == "yes"


def test_verify_clip_still_weak(tmp_path, monkeypatch):
    project, project_dir, layer = _project_with_layer(tmp_path)
    frames = _frames(inside_delta=4, outside_delta=0)
    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=True), frames)
    assert result.elements[0].verdict == "weak"


def test_verify_clip_still_no(tmp_path, monkeypatch):
    project, project_dir, layer = _project_with_layer(tmp_path)
    frames = _frames(inside_delta=10, outside_delta=0)
    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=True), frames)
    assert result.elements[0].verdict == "no"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_verify_clip_empty_mask(tmp_path, monkeypatch):
    project, project_dir, layer = _project_with_layer(tmp_path, box=(0, 0, 0, 0))
    frames = _frames(inside_delta=50, outside_delta=0)
    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=False), frames)
    e = result.elements[0]
    assert e.verdict == "no"
    assert "prázdná maska" in result.summary


def test_verify_clip_layer_not_found_is_skipped(tmp_path, monkeypatch):
    project, project_dir, _layer = _project_with_layer(tmp_path)
    frames = _frames()
    clip = _clip("does-not-exist", static=False)
    result = _verify(monkeypatch, project, project_dir, clip, frames)
    assert result.elements == []
    assert "nenalezena" in result.summary


def test_verify_clip_insufficient_frames(tmp_path, monkeypatch):
    project, project_dir, layer = _project_with_layer(tmp_path)
    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=False), _frames(n=1))
    assert result.elements == []
    assert result.frames_sampled == 1


def test_verify_clip_mask_resized_to_frame_size(tmp_path, monkeypatch):
    """Provider output resolution (here 32x32) commonly differs from the
    project canvas (64x64) -- the mask must be resized to match, not crash."""
    project, project_dir, layer = _project_with_layer(tmp_path)  # 64x64 canvas, box (16,16,48,48)
    frames = _frames(canvas=(32, 32), box=(8, 8, 24, 24), inside_delta=50, outside_delta=0)
    result = _verify(monkeypatch, project, project_dir, _clip(layer.id, static=False), frames)
    assert result.frame_size == [32, 32]
    assert result.elements[0].verdict == "yes"


def test_verify_clip_no_motion_spec(tmp_path, monkeypatch):
    """clip.motion is None (e.g. a job submitted with only prompt_override) --
    no per-element verdicts, but global_motion is still computed."""
    project, project_dir, _layer = _project_with_layer(tmp_path)
    frames = _frames(inside_delta=50, outside_delta=0)
    clip = ClipRecord(
        provider_id="kling-26-pro",
        endpoint="fal-ai/kling-video/v2.6/pro/image-to-video",
        status="completed",
        path="clips/fake.mp4",
        motion=None,
    )
    result = _verify(monkeypatch, project, project_dir, clip, frames)
    assert result.elements == []
    assert result.global_motion > 0
