"""Tests for MotionSpec + project.json schema v2 (task 1.6).

See docs/plans/2026-08-14-unified-editor.md (A6) and
docs/plans/2026-08-14-phase1-gate.md (A3 amendment: MotionSpec compiles to a
structured prompt, not a Kling dynamic_masks payload).

Covers:
- sc-4: the real, pre-existing v1 `.grafik` project loads unchanged.
- Round-trip: v2 additions (LayerMotion, ClipRecord) survive save/reload.
- v1-code-reads-v2 tolerance: a v2 project.json minus its new keys still
  validates — the new fields are safe to ignore.
- grafik.motion.compiler: direction/static/camera phrasing, determinism,
  and the minimal video payload shape.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from grafik.core.layer import Layer
from grafik.core.motion import (
    CameraMove,
    CameraSpec,
    ClipRecord,
    LayerMotion,
    MotionSpec,
    TrajectoryPoint,
)
from grafik.core.project import LayerProject
from grafik.motion.compiler import build_video_payload, compile_motion_prompt, estimate_direction

# Real, pre-existing v1 project on disk. READ-ONLY in every test below —
# never write into this directory; copy it into tmp_path first.
REAL_PROJECT_DIR = Path("C:/Users/stock/Documents/000_NGM/GRAFIK/projects/decompose-test.grafik")


def _tiny_project() -> LayerProject:
    """Small synthetic project for compiler unit tests (isolated, no disk I/O)."""
    project = LayerProject.new("compiler-test", 400, 300)
    project.add_layer(Layer(id="bird", name="Bird"))
    project.add_layer(Layer(id="mountain", name="Mountain"))
    return project


# ---------------------------------------------------------------------------
# sc-4 — backward compat: the real v1 project loads unchanged
# ---------------------------------------------------------------------------


def test_v1_project_loads_unchanged():
    project = LayerProject.load(REAL_PROJECT_DIR)

    assert len(project.layers) == 4
    assert project.canvas_width == 544
    assert project.canvas_height == 736
    # v1 project.json has no schema_version key; the v2 model default fills
    # in the CURRENT schema version (2) rather than retroactively inferring 1.
    assert project.schema_version == 2
    assert project.clips == []
    assert all(layer.motion is None for layer in project.layers)


# ---------------------------------------------------------------------------
# Round-trip: add v2 data on a scratch copy, save, reload
# ---------------------------------------------------------------------------


def test_roundtrip_motion_and_clip(tmp_path):
    copy_dir = tmp_path / "decompose-test.grafik"
    shutil.copytree(REAL_PROJECT_DIR, copy_dir)

    project = LayerProject.load(copy_dir)
    target = next(l for l in project.layers if l.name == "Layer 3")
    target.motion = LayerMotion(
        trajectory=[TrajectoryPoint(x=204, y=515), TrajectoryPoint(x=304, y=515)],
        static=False,
        description="",
    )
    clip = ClipRecord(
        provider_id="kling-26-pro",
        endpoint="fal-ai/kling-video/v2.6/pro/image-to-video",
        status="completed",
        request_id="req-123",
        path="clips/req-123.mp4",
        prompt="Layer 3 moves to the right.",
        motion=MotionSpec(layer_motions={target.id: target.motion}),
        cost_note="~$0.30",
    )
    project.clips.append(clip)

    saved_path = project.save(copy_dir)
    reloaded = LayerProject.load(saved_path)

    assert reloaded.model_dump() == project.model_dump()
    # old fields unchanged
    assert reloaded.canvas_width == 544
    assert reloaded.canvas_height == 736
    assert len(reloaded.layers) == 4
    assert [l.name for l in reloaded.layers] == ["Layer 0", "Layer 1", "Layer 2", "Layer 3"]
    # clips/ dir created alongside layers/ and composites/
    assert (saved_path / "clips").is_dir()

    raw = json.loads((saved_path / "project.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == 2
    assert len(raw["clips"]) == 1
    raw_target = next(l for l in raw["layers"] if l["id"] == target.id)
    assert raw_target["motion"] is not None
    assert raw_target["motion"]["trajectory"] == [{"x": 204, "y": 515}, {"x": 304, "y": 515}]


# ---------------------------------------------------------------------------
# v1-code-reads-v2 tolerance: strip v2-only keys, confirm it still validates
# ---------------------------------------------------------------------------


def test_v1_shaped_json_still_validates(tmp_path):
    copy_dir = tmp_path / "decompose-test.grafik"
    shutil.copytree(REAL_PROJECT_DIR, copy_dir)

    project = LayerProject.load(copy_dir)
    project.layers[0].motion = LayerMotion(static=True)
    project.clips.append(
        ClipRecord(provider_id="kling-26-pro", endpoint="fal-ai/kling-video/v2.6/pro/image-to-video")
    )
    saved_path = project.save(copy_dir)

    raw = json.loads((saved_path / "project.json").read_text(encoding="utf-8"))
    raw.pop("schema_version", None)
    raw.pop("clips", None)
    for layer in raw["layers"]:
        layer.pop("motion", None)

    stripped = LayerProject.model_validate(raw)

    assert stripped.schema_version == 2  # default fills back in
    assert stripped.clips == []
    assert all(l.motion is None for l in stripped.layers)
    assert len(stripped.layers) == 4
    assert stripped.canvas_width == 544
    assert stripped.canvas_height == 736


# ---------------------------------------------------------------------------
# grafik.motion.compiler
# ---------------------------------------------------------------------------


def test_compile_direction_and_name():
    project = _tiny_project()
    spec = MotionSpec(
        layer_motions={
            "bird": LayerMotion(
                trajectory=[TrajectoryPoint(x=10, y=10), TrajectoryPoint(x=200, y=10)]
            ),
        }
    )
    prompt = compile_motion_prompt(project, spec)
    assert "right" in prompt
    assert "Bird" in prompt


def test_compile_static_layer():
    project = _tiny_project()
    spec = MotionSpec(layer_motions={"mountain": LayerMotion(static=True)})
    prompt = compile_motion_prompt(project, spec)
    assert "remains still" in prompt
    assert "Mountain" in prompt


def test_compile_camera_zoom_in_quickly():
    project = _tiny_project()
    spec = MotionSpec(camera=CameraSpec(move=CameraMove.ZOOM_IN, magnitude=0.9))
    prompt = compile_motion_prompt(project, spec)
    assert "quickly" in prompt


def test_compile_deterministic():
    project = _tiny_project()
    spec = MotionSpec(
        camera=CameraSpec(move=CameraMove.PAN_LEFT, magnitude=0.5),
        layer_motions={
            "bird": LayerMotion(
                trajectory=[TrajectoryPoint(x=0, y=0), TrajectoryPoint(x=50, y=50)]
            ),
            "mountain": LayerMotion(static=True),
        },
    )
    assert compile_motion_prompt(project, spec) == compile_motion_prompt(project, spec)


def test_compile_description_used_verbatim():
    project = _tiny_project()
    spec = MotionSpec(layer_motions={"bird": LayerMotion(description="flaps and glides eastward")})
    prompt = compile_motion_prompt(project, spec)
    assert "flaps and glides eastward" in prompt


def test_compile_no_motion_no_camera_fallback():
    project = _tiny_project()
    assert compile_motion_prompt(project, MotionSpec()) == "The scene remains still."


def test_estimate_direction_basic():
    assert estimate_direction([TrajectoryPoint(x=10, y=10), TrajectoryPoint(x=200, y=10)]) == "right"
    assert estimate_direction([TrajectoryPoint(x=0, y=0)]) == ""
    assert estimate_direction([]) == ""


def test_build_video_payload_shape():
    payload = build_video_payload(
        endpoint="fal-ai/kling-video/v2.6/pro/image-to-video",
        image_url="https://example.com/in.png",
        prompt="Bird moves right.",
        duration="5",
    )
    assert payload == {
        "prompt": "Bird moves right.",
        "image_url": "https://example.com/in.png",
        "duration": "5",
    }
