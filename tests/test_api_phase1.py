"""Tests for task 1.7 API routes: per-element AI edit, SAM-3 segmentation,
and async video jobs. Fully offline -- every network boundary is
monkeypatched:

- QwenInpaintProvider._run_remote (ai-edit) -- same seam test_providers.py uses.
- grafik.api.app._segment_remote (segment) -- the route's own isolated helper.
- grafik.motion.jobs._upload/_submit/_status/_result/_download (video jobs).

Fixture `api` copies the real, read-only decompose-test.grafik project
(same one test_motion_v2.py uses) into tmp_path and monkeypatches
grafik.api.app.PROJECTS_DIR so the API never touches the real projects/
directory. It also resets grafik.api.app._histories to a fresh dict per
test: project_id is stable across tests (baked into the copied
project.json), and _histories is a module-level dict keyed by project_id,
so without this reset, undo/redo state would leak between tests.
"""

from __future__ import annotations

import json
import shutil
from io import BytesIO
from pathlib import Path

import fal_client
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from grafik.core.project import LayerProject
from grafik.providers.qwen_inpaint import QwenInpaintProvider

# Real, pre-existing v1 project on disk -- READ-ONLY, always copied first (matches test_motion_v2.py).
REAL_PROJECT_DIR = Path("C:/Users/stock/Documents/000_NGM/GRAFIK/projects/decompose-test.grafik")
LAYER_3_ID = "7d30fcc59fa3"  # "Layer 3", alpha coverage ~11%, compact object (see scripts/smoke_kling_motion.py)


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


def _submit_fake_job(client, project_id, monkeypatch, request_id="req-abc-123"):
    """POST /video/jobs with _upload/_submit monkeypatched. Returns the ClipRecord JSON."""
    import grafik.motion.jobs as jobs_module

    monkeypatch.setattr(jobs_module, "_upload", lambda path: "https://fake-cdn.example.com/in.png")
    monkeypatch.setattr(jobs_module, "_submit", lambda endpoint, payload: request_id)

    body = {
        "motion": {"duration": "5", "layer_motions": {LAYER_3_ID: {"static": True}}},
        "provider": "kling-26-pro",
    }
    resp = client.post(f"/api/projects/{project_id}/video/jobs", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# ai-edit
# ---------------------------------------------------------------------------


def test_ai_edit_happy_path_and_undo(api, monkeypatch):
    client, project_dir, project_id = api

    def fake_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
        return Image.new("RGB", image.size, (0, 255, 0))

    monkeypatch.setattr(QwenInpaintProvider, "_run_remote", fake_run_remote)

    before_bytes = client.get(f"/api/projects/{project_id}/layers/{LAYER_3_ID}/png").content

    # First call: mutates pixels and pushes the first history snapshot.
    r1 = client.post(
        f"/api/projects/{project_id}/layers/{LAYER_3_ID}/ai-edit",
        json={"prompt": "add a red hat"},
    )
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["provider"] == "qwen-inpaint"
    assert body1["layer"]["id"] == LAYER_3_ID
    assert body1["elapsed_s"] >= 0

    after1_bytes = client.get(f"/api/projects/{project_id}/layers/{LAYER_3_ID}/png").content
    assert after1_bytes != before_bytes, "layer PNG bytes must change after ai-edit"

    # History stores project.json snapshots (metadata only, not pixel bytes --
    # same as every other ops route in this file, e.g. recolor/flip/mask).
    # can_undo requires >1 pushes, so nothing is undo-able after just one call.
    hist1 = client.get(f"/api/projects/{project_id}/history").json()
    assert hist1 == {"undo_count": 0, "redo_count": 0}

    # Second call pushes a second snapshot -> undo becomes available.
    r2 = client.post(
        f"/api/projects/{project_id}/layers/{LAYER_3_ID}/ai-edit",
        json={"prompt": "now a blue hat"},
    )
    assert r2.status_code == 200, r2.text

    hist2 = client.get(f"/api/projects/{project_id}/history").json()
    assert hist2["undo_count"] == 1

    undo_resp = client.post(f"/api/projects/{project_id}/undo")
    assert undo_resp.status_code == 200
    assert undo_resp.json() == {"undone": True, "undo_remaining": 0, "redo_available": 1}

    # The undo mechanism must not corrupt the project (ideal-state #11 concern).
    reloaded = LayerProject.load(project_dir)
    assert reloaded.get_layer(LAYER_3_ID) is not None


def test_ai_edit_provider_without_mask_support_400(api):
    client, _, project_id = api
    resp = client.post(
        f"/api/projects/{project_id}/layers/{LAYER_3_ID}/ai-edit",
        json={"prompt": "x", "provider": "kling-26-pro"},  # video provider, supports_mask=False
    )
    assert resp.status_code == 400
    assert "kling-26-pro" in resp.json()["detail"]


def test_ai_edit_unknown_provider_404(api):
    client, _, project_id = api
    resp = client.post(
        f"/api/projects/{project_id}/layers/{LAYER_3_ID}/ai-edit",
        json={"prompt": "x", "provider": "does-not-exist"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# segment
# ---------------------------------------------------------------------------


def test_segment_creates_capped_tagged_layers(api, monkeypatch):
    client, project_dir, project_id = api
    import grafik.api.app as app_module

    def fake_segment_remote(image, text, endpoint, points=None):
        return [Image.new("L", image.size, 255) for _ in range(10)]  # more than the 8 cap

    monkeypatch.setattr(app_module, "_segment_remote", fake_segment_remote)

    before_count = len(LayerProject.load(project_dir).layers)

    resp = client.post(f"/api/projects/{project_id}/segment", json={"text": "a cat"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mask_count"] == 10
    assert len(body["layers"]) == 8
    assert all(l["tags"] == ["sam"] for l in body["layers"])
    assert all(l["name"] == "sam: a cat" for l in body["layers"])

    after = LayerProject.load(project_dir)
    assert len(after.layers) == before_count + 8


def test_segment_create_layers_false_returns_count_only(api, monkeypatch):
    client, project_dir, project_id = api
    import grafik.api.app as app_module

    monkeypatch.setattr(
        app_module,
        "_segment_remote",
        lambda image, text, endpoint, points=None: [Image.new("L", image.size, 255)] * 3,
    )

    before_count = len(LayerProject.load(project_dir).layers)
    resp = client.post(
        f"/api/projects/{project_id}/segment",
        json={"text": "a dog", "create_layers": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mask_count"] == 3
    assert body["layers"] == []
    assert len(LayerProject.load(project_dir).layers) == before_count


def test_segment_unknown_provider_404(api):
    client, _, project_id = api
    resp = client.post(f"/api/projects/{project_id}/segment", json={"text": "x", "provider": "does-not-exist"})
    assert resp.status_code == 404


def test_segment_wrong_kind_400(api):
    client, _, project_id = api
    resp = client.post(f"/api/projects/{project_id}/segment", json={"text": "x", "provider": "qwen-inpaint"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# video jobs
# ---------------------------------------------------------------------------


def test_video_job_submit_and_list(api, monkeypatch):
    client, project_dir, project_id = api

    clip = _submit_fake_job(client, project_id, monkeypatch)
    assert clip["status"] == "running"
    assert clip["request_id"] == "req-abc-123"
    assert clip["provider_id"] == "kling-26-pro"

    reloaded = LayerProject.load(project_dir)
    assert len(reloaded.clips) == 1
    assert reloaded.clips[0].request_id == "req-abc-123"
    assert reloaded.clips[0].status == "running"

    listing = client.get(f"/api/projects/{project_id}/video/jobs")
    assert listing.status_code == 200
    ids = [c["id"] for c in listing.json()]
    assert clip["id"] in ids


def test_video_job_refresh_completed_serves_video(api, monkeypatch):
    client, project_dir, project_id = api
    import grafik.motion.jobs as jobs_module

    clip = _submit_fake_job(client, project_id, monkeypatch)
    clip_id = clip["id"]

    monkeypatch.setattr(jobs_module, "_status", lambda endpoint, rid: fal_client.Completed(logs=None, metrics={}))
    monkeypatch.setattr(
        jobs_module, "_result", lambda endpoint, rid: {"video": {"url": "https://fake-cdn.example.com/clip.mp4"}}
    )
    monkeypatch.setattr(jobs_module, "_download", lambda url: b"FAKE-MP4-BYTES")

    resp = client.get(f"/api/projects/{project_id}/video/jobs/{clip_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["path"] == f"clips/{clip_id}.mp4"

    clip_file = project_dir / "clips" / f"{clip_id}.mp4"
    assert clip_file.exists()
    assert clip_file.read_bytes() == b"FAKE-MP4-BYTES"

    video_resp = client.get(f"/api/projects/{project_id}/clips/{clip_id}/video")
    assert video_resp.status_code == 200
    assert video_resp.headers["content-type"] == "video/mp4"
    assert video_resp.content == b"FAKE-MP4-BYTES"


def test_video_job_refresh_in_progress_stays_running(api, monkeypatch):
    client, project_dir, project_id = api
    import grafik.motion.jobs as jobs_module

    clip = _submit_fake_job(client, project_id, monkeypatch)
    clip_id = clip["id"]

    monkeypatch.setattr(jobs_module, "_status", lambda endpoint, rid: fal_client.Queued(position=2))

    resp = client.get(f"/api/projects/{project_id}/video/jobs/{clip_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "running"
    assert LayerProject.load(project_dir).clips[0].status == "running"


def test_video_job_refresh_failure_keeps_project_loadable(api, monkeypatch):
    client, project_dir, project_id = api
    import grafik.motion.jobs as jobs_module

    clip = _submit_fake_job(client, project_id, monkeypatch)
    clip_id = clip["id"]

    def fake_status_raises(endpoint, rid):
        raise Exception("moderation: flagged")

    monkeypatch.setattr(jobs_module, "_status", fake_status_raises)

    resp = client.get(f"/api/projects/{project_id}/video/jobs/{clip_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "failed"
    assert "moderation: flagged" in body["error"]

    # Ideal-state criterion #11: generation failure surfaces the reason and does NOT corrupt the project.
    reloaded = LayerProject.load(project_dir)
    assert reloaded.clips[0].status == "failed"
    assert "moderation: flagged" in reloaded.clips[0].error


def test_video_job_unknown_provider_404(api):
    client, _, project_id = api
    resp = client.post(
        f"/api/projects/{project_id}/video/jobs",
        json={"motion": {}, "provider": "does-not-exist"},
    )
    assert resp.status_code == 404


def test_video_job_wrong_kind_400(api):
    client, _, project_id = api
    resp = client.post(
        f"/api/projects/{project_id}/video/jobs",
        json={"motion": {}, "provider": "qwen-inpaint"},  # image_edit, not video
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# layers/png checker background (pre-existing route, regression for missing PIL import)
# ---------------------------------------------------------------------------


def test_layer_png_checker(api):
    client, _, project_id = api
    resp = client.get(f"/api/projects/{project_id}/layers/{LAYER_3_ID}/png?checker=true")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "image/png"
    img = Image.open(BytesIO(resp.content)).convert("RGBA")
    # Layer 3 alone is ~11% opaque; the checker composite must yield a fully opaque image.
    assert img.getchannel("A").getextrema() == (255, 255)
