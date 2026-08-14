"""Tests for GRAFIK M3 API routes: per-layer motion persistence, video
compile preview, prompt_override on job submission, and clip verification.
Fully offline -- fal network boundaries (grafik.motion.jobs._upload/_submit,
grafik.motion.verify.sample_frames) are monkeypatched, same seams
test_api_phase1.py and test_motion_verify.py use.

Fixture `api` mirrors test_api_phase1.py / test_api_m2.py exactly: copies
the real, read-only decompose-test.grafik project into tmp_path and
monkeypatches grafik.api.app.PROJECTS_DIR / _histories so the API never
touches the real projects/ directory and undo/redo state can't leak between
tests. Video-job tests reuse the plain video/jobs submit/refresh coverage
already in test_api_phase1.py -- only the NEW M3 behavior (prompt_override,
compile preview, verify) is tested here.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import fal_client
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from grafik.core.motion import MotionSpec
from grafik.core.project import LayerProject
from grafik.motion.compiler import compile_motion_prompt

REAL_PROJECT_DIR = Path("C:/Users/stock/Documents/000_NGM/GRAFIK/projects/decompose-test.grafik")
LAYER_3_ID = "7d30fcc59fa3"  # "Layer 3", alpha coverage ~11%, compact object


@pytest.fixture
def api(tmp_path, monkeypatch):
    """Returns (client, project_dir, project_id) over a scratch copy of decompose-test.grafik."""
    import grafik.api.app as app_module

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    project_dir = projects_dir / "decompose-test.grafik"
    shutil.copytree(REAL_PROJECT_DIR, project_dir)
    # REAL_PROJECT_DIR is a shared, live directory -- manual/E2E use against it
    # (outside this test run) can leave a real history.json behind, which
    # would otherwise get copied in and poison undo_count for this test.
    (project_dir / "history.json").unlink(missing_ok=True)
    project_id = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))["id"]

    monkeypatch.setattr(app_module, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(app_module, "_histories", {})

    return TestClient(app_module.app), project_dir, project_id


def _submit_job(client, project_id, monkeypatch, body=None, request_id="req-m3-1"):
    """POST /video/jobs with _upload/_submit monkeypatched (test_api_phase1.py
    pattern). Returns the ClipRecord JSON."""
    import grafik.motion.jobs as jobs_module

    monkeypatch.setattr(jobs_module, "_upload", lambda path: "https://fake-cdn.example.com/in.png")
    monkeypatch.setattr(jobs_module, "_submit", lambda endpoint, payload: request_id)

    body = body or {
        "motion": {"duration": "5", "layer_motions": {LAYER_3_ID: {"static": True}}},
        "provider": "kling-26-pro",
    }
    resp = client.post(f"/api/projects/{project_id}/video/jobs", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _completed_clip(client, project_id, monkeypatch):
    """Submit + refresh a fake video job to status=completed with a real
    (fake-content) mp4 file on disk, ready for /verify (test_api_phase1.py's
    test_video_job_refresh_completed_serves_video pattern)."""
    import grafik.motion.jobs as jobs_module

    clip = _submit_job(client, project_id, monkeypatch)
    monkeypatch.setattr(jobs_module, "_status", lambda endpoint, rid: fal_client.Completed(logs=None, metrics={}))
    monkeypatch.setattr(
        jobs_module, "_result", lambda endpoint, rid: {"video": {"url": "https://fake-cdn.example.com/clip.mp4"}}
    )
    monkeypatch.setattr(jobs_module, "_download", lambda url: b"FAKE-MP4-BYTES")

    resp = client.get(f"/api/projects/{project_id}/video/jobs/{clip['id']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "completed"
    return clip["id"]


# ---------------------------------------------------------------------------
# Layer motion persistence (POST/DELETE .../motion) -- ideal-state criterion #6
# ---------------------------------------------------------------------------


def test_set_layer_motion_persists_and_appears_on_layer_response(api):
    client, project_dir, project_id = api
    body = {
        "trajectory": [{"x": 10, "y": 20}, {"x": 30, "y": 40}],
        "static": False,
        "description": "letí doprava",
    }
    resp = client.post(f"/api/projects/{project_id}/layers/{LAYER_3_ID}/motion", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["motion"]["trajectory"] == [{"x": 10, "y": 20}, {"x": 30, "y": 40}]
    assert data["motion"]["static"] is False
    assert data["motion"]["description"] == "letí doprava"

    raw = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    layer_raw = next(l for l in raw["layers"] if l["id"] == LAYER_3_ID)
    assert layer_raw["motion"]["trajectory"] == [{"x": 10, "y": 20}, {"x": 30, "y": 40}]

    layers = client.get(f"/api/projects/{project_id}/layers").json()
    l3 = next(l for l in layers if l["id"] == LAYER_3_ID)
    assert l3["motion"]["description"] == "letí doprava"


def test_set_layer_motion_defaults_when_body_empty(api):
    client, _, project_id = api
    resp = client.post(f"/api/projects/{project_id}/layers/{LAYER_3_ID}/motion", json={})
    assert resp.status_code == 200, resp.text
    motion = resp.json()["motion"]
    assert motion == {"trajectory": [], "static": False, "description": ""}


def test_set_layer_motion_unknown_layer_404(api):
    client, _, project_id = api
    resp = client.post(f"/api/projects/{project_id}/layers/does-not-exist/motion", json={})
    assert resp.status_code == 404


def test_delete_layer_motion_clears(api):
    client, project_dir, project_id = api
    client.post(f"/api/projects/{project_id}/layers/{LAYER_3_ID}/motion", json={"static": True})

    resp = client.delete(f"/api/projects/{project_id}/layers/{LAYER_3_ID}/motion")
    assert resp.status_code == 200, resp.text
    assert resp.json()["motion"] is None

    raw = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    layer_raw = next(l for l in raw["layers"] if l["id"] == LAYER_3_ID)
    assert layer_raw["motion"] is None


def test_delete_layer_motion_unknown_layer_404(api):
    client, _, project_id = api
    resp = client.delete(f"/api/projects/{project_id}/layers/does-not-exist/motion")
    assert resp.status_code == 404


def test_layer_motion_undo_restores_previous_motion(api):
    """Same _snapshot-after-mutation pattern as /transform (LEARNINGS
    2026-08-14): undo restores the state as of the PREVIOUS snapshot, i.e.
    the first mutation's result, not the pre-mutation state."""
    client, _, project_id = api
    r1 = client.post(f"/api/projects/{project_id}/layers/{LAYER_3_ID}/motion", json={"static": True})
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        f"/api/projects/{project_id}/layers/{LAYER_3_ID}/motion",
        json={"static": False, "description": "second"},
    )
    assert r2.status_code == 200, r2.text

    hist = client.get(f"/api/projects/{project_id}/history").json()
    assert hist["undo_count"] == 1

    undo = client.post(f"/api/projects/{project_id}/undo")
    assert undo.status_code == 200, undo.text

    layers = client.get(f"/api/projects/{project_id}/layers").json()
    l3 = next(l for l in layers if l["id"] == LAYER_3_ID)
    assert l3["motion"]["static"] is True
    assert l3["motion"]["description"] == ""


# ---------------------------------------------------------------------------
# /video/compile -- ideal-state criterion #7
# ---------------------------------------------------------------------------


def test_compile_video_prompt_matches_compiler_and_cost_math(api):
    client, project_dir, project_id = api
    motion_body = {
        "camera": {"move": "zoom_in", "magnitude": 0.9},
        "duration": "5",
        "layer_motions": {
            LAYER_3_ID: {
                "trajectory": [{"x": 10, "y": 10}, {"x": 200, "y": 10}],
                "static": False,
                "description": "",
            },
        },
    }
    resp = client.post(
        f"/api/projects/{project_id}/video/compile",
        json={"motion": motion_body, "provider": "kling-26-pro"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    project = LayerProject.load(project_dir)
    spec = MotionSpec.model_validate(motion_body)
    assert data["prompt"] == compile_motion_prompt(project, spec)
    assert data["provider"] == "kling-26-pro"
    assert data["endpoint"] == "fal-ai/kling-video/v2.6/pro/image-to-video"
    assert data["duration"] == "5"
    assert data["est_cost_usd"] == pytest.approx(0.07 * 5)
    assert data["payload_preview"] == {
        "prompt": data["prompt"],
        "start_image_url": "<composite>",
        "duration": "5",
        "generate_audio": False,
    }


def test_compile_video_wan26_payload_preview_fields(api):
    client, _, project_id = api
    motion_body = {"duration": "10", "layer_motions": {LAYER_3_ID: {"static": True}}}
    resp = client.post(
        f"/api/projects/{project_id}/video/compile",
        json={"motion": motion_body, "provider": "wan-26"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["endpoint"] == "wan/v2.6/image-to-video"
    assert data["est_cost_usd"] == pytest.approx(0.10 * 10)
    assert data["payload_preview"]["image_url"] == "<composite>"
    assert data["payload_preview"]["resolution"] == "720p"
    assert data["payload_preview"]["enable_prompt_expansion"] is False
    assert "start_image_url" not in data["payload_preview"]


def test_compile_video_unknown_provider_404(api):
    client, _, project_id = api
    resp = client.post(f"/api/projects/{project_id}/video/compile", json={"motion": {}, "provider": "nope"})
    assert resp.status_code == 404


def test_compile_video_non_video_provider_400(api):
    client, _, project_id = api
    resp = client.post(
        f"/api/projects/{project_id}/video/compile", json={"motion": {}, "provider": "qwen-inpaint"}
    )
    assert resp.status_code == 400


def test_compile_video_duration_out_of_choices_400(api):
    client, _, project_id = api
    resp = client.post(
        f"/api/projects/{project_id}/video/compile",
        json={"motion": {"duration": "999"}, "provider": "kling-26-pro"},
    )
    assert resp.status_code == 400


def test_compile_video_est_cost_none_when_price_unknown(api):
    client, _, project_id = api
    resp = client.post(
        f"/api/projects/{project_id}/video/compile",
        json={"motion": {"duration": "auto"}, "provider": "seedance-25"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["est_cost_usd"] is None


# ---------------------------------------------------------------------------
# /video/jobs -- prompt_override
# ---------------------------------------------------------------------------


def test_video_job_prompt_override_used_instead_of_compiled_prompt(api, monkeypatch):
    client, project_dir, project_id = api
    import grafik.motion.jobs as jobs_module

    monkeypatch.setattr(jobs_module, "_upload", lambda path: "https://fake-cdn.example.com/in.png")
    captured = {}

    def fake_submit(endpoint, payload):
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        return "req-override-1"

    monkeypatch.setattr(jobs_module, "_submit", fake_submit)

    body = {
        "motion": {"duration": "5", "layer_motions": {LAYER_3_ID: {"static": True}}},
        "provider": "kling-26-pro",
        "prompt_override": "A hand-written custom prompt.",
    }
    resp = client.post(f"/api/projects/{project_id}/video/jobs", json=body)
    assert resp.status_code == 200, resp.text
    clip = resp.json()

    # kling-26-pro's image field is start_image_url, not image_url.
    assert captured["payload"] == {
        "prompt": "A hand-written custom prompt.",
        "start_image_url": "https://fake-cdn.example.com/in.png",
        "duration": "5",
        "generate_audio": False,
    }
    assert clip["prompt"] == "A hand-written custom prompt."

    reloaded = LayerProject.load(project_dir)
    assert reloaded.clips[0].prompt == "A hand-written custom prompt."


def test_video_job_prompt_override_wan26_uses_image_url_field(api, monkeypatch):
    client, _, project_id = api
    import grafik.motion.jobs as jobs_module

    monkeypatch.setattr(jobs_module, "_upload", lambda path: "https://fake-cdn.example.com/in.png")
    captured = {}

    def fake_submit(endpoint, payload):
        captured["payload"] = payload
        return "req-wan-1"

    monkeypatch.setattr(jobs_module, "_submit", fake_submit)

    body = {
        "motion": {"duration": "10"},
        "provider": "wan-26",
        "prompt_override": "Wan override prompt.",
    }
    resp = client.post(f"/api/projects/{project_id}/video/jobs", json=body)
    assert resp.status_code == 200, resp.text
    assert captured["payload"] == {
        "prompt": "Wan override prompt.",
        "image_url": "https://fake-cdn.example.com/in.png",
        "duration": "10",
        "resolution": "720p",
        "enable_prompt_expansion": False,
    }


def test_video_job_blank_prompt_override_falls_back_to_compiled(api, monkeypatch):
    """Whitespace-only override must NOT beat the compiled prompt (str.strip() check)."""
    client, _, project_id = api
    import grafik.motion.jobs as jobs_module

    monkeypatch.setattr(jobs_module, "_upload", lambda path: "https://fake-cdn.example.com/in.png")
    captured = {}

    def fake_submit(endpoint, payload):
        captured["payload"] = payload
        return "req-blank-1"

    monkeypatch.setattr(jobs_module, "_submit", fake_submit)

    body = {
        "motion": {"duration": "5", "layer_motions": {LAYER_3_ID: {"static": True}}},
        "provider": "kling-26-pro",
        "prompt_override": "   ",
    }
    resp = client.post(f"/api/projects/{project_id}/video/jobs", json=body)
    assert resp.status_code == 200, resp.text
    assert captured["payload"]["prompt"] != "   "
    assert "Layer 3" in captured["payload"]["prompt"]


# ---------------------------------------------------------------------------
# /clips/{clip_id}/verify -- ideal-state criterion #8
# ---------------------------------------------------------------------------


def test_verify_clip_persists_verification(api, monkeypatch):
    client, project_dir, project_id = api
    clip_id = _completed_clip(client, project_id, monkeypatch)

    import grafik.motion.verify as verify_module

    frame = Image.new("RGB", (544, 736), (100, 100, 100))
    monkeypatch.setattr(verify_module, "sample_frames", lambda video_path, count=5: [frame, frame])

    resp = client.post(f"/api/projects/{project_id}/clips/{clip_id}/verify")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    verification = body["verification"]
    assert verification is not None
    assert verification["frame_size"] == [544, 736]
    assert verification["frames_sampled"] == 2
    assert verification["global_motion"] == 0.0
    elements = verification["elements"]
    assert len(elements) == 1
    assert elements[0]["layer_id"] == LAYER_3_ID
    assert elements[0]["wanted"] == "still"
    assert elements[0]["verdict"] == "yes"

    reloaded = LayerProject.load(project_dir)
    reloaded_clip = next(c for c in reloaded.clips if c.id == clip_id)
    assert reloaded_clip.verification is not None
    assert reloaded_clip.verification.frames_sampled == 2


def test_verify_clip_unknown_clip_404(api):
    client, _, project_id = api
    resp = client.post(f"/api/projects/{project_id}/clips/does-not-exist/verify")
    assert resp.status_code == 404


def test_verify_clip_not_completed_400(api, monkeypatch):
    client, _, project_id = api
    clip = _submit_job(client, project_id, monkeypatch)  # stays "running" -- never refreshed

    resp = client.post(f"/api/projects/{project_id}/clips/{clip['id']}/verify")
    assert resp.status_code == 400


def test_verify_clip_missing_file_400(api, monkeypatch):
    client, project_dir, project_id = api
    clip_id = _completed_clip(client, project_id, monkeypatch)
    (project_dir / "clips" / f"{clip_id}.mp4").unlink()

    resp = client.post(f"/api/projects/{project_id}/clips/{clip_id}/verify")
    assert resp.status_code == 400
