"""Tests for GRAFIK M2 API routes: provider listing, ai-edit brush masks
(mask_b64), inpaint-behind, readable provider-error responses, and layer
reorder. Fully offline -- QwenInpaintProvider._run_remote is monkeypatched,
same seam test_api_phase1.py and test_providers.py use.

Fixture `api` mirrors test_api_phase1.py exactly: copies the real, read-only
decompose-test.grafik project into tmp_path and monkeypatches
grafik.api.app.PROJECTS_DIR / _histories so the API never touches the real
projects/ directory and undo/redo state can't leak between tests.
"""

from __future__ import annotations

import base64
import json
import shutil
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageFilter

from grafik.core.layer import Layer
from grafik.core.project import LayerProject
from grafik.providers.qwen_inpaint import QwenInpaintProvider

REAL_PROJECT_DIR = Path("C:/Users/stock/Documents/000_NGM/GRAFIK/projects/decompose-test.grafik")
LAYER_0_ID = "5588a9f356b6"  # "Layer 0", visible, canvas-sized (0,0,544,736) -- lowest visible z_order
LAYER_2_ID = "e64e0a36cfa9"  # "Layer 2", visible, canvas-sized
LAYER_3_ID = "7d30fcc59fa3"  # "Layer 3", visible, alpha coverage ~11%, compact object

# dilate_px/feather_px defaults shared by AiEditRequest and InpaintBehindRequest.
DEFAULT_DILATE_PX = 4
DEFAULT_FEATHER_PX = 2


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
    # Same shared-live-dir hazard, geometry edition: manual/E2E sessions can
    # move, scale, flip, or re-show layers in the real project (it happened —
    # M2 E2E drift broke the inpaint-behind tests). The tests below assume the
    # M2 baseline (Layers 0/2/3 visible, canvas-aligned at (0,0) in native PNG
    # size, no rotation, everything else hidden), so pin exactly that in the
    # scratch copy instead of trusting whatever state disk happens to be in.
    baseline_visible = {LAYER_0_ID, LAYER_2_ID, LAYER_3_ID}
    project = LayerProject.load(project_dir)
    for layer in project.layers:
        layer.visible = layer.id in baseline_visible
        if layer.id in baseline_visible:
            img = layer.load_image(project_dir)
            layer.x = 0
            layer.y = 0
            layer.width = img.width
            layer.height = img.height
            layer.rotation = 0.0
    project.save(project_dir)
    project_id = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))["id"]

    monkeypatch.setattr(app_module, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(app_module, "_histories", {})

    return TestClient(app_module.app), project_dir, project_id


def _b64_png(img: Image.Image) -> str:
    buf = BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _feathered(hard_mask: Image.Image, dilate_px=DEFAULT_DILATE_PX, feather_px=DEFAULT_FEATHER_PX) -> Image.Image:
    """Reproduces the dilate+feather steps ai_edit_layer/inpaint_behind_layer
    apply to a hard mask, so tests can compute expected changed/unchanged
    zones independently instead of trusting the route's own math."""
    out = hard_mask
    if dilate_px > 0:
        out = out.filter(ImageFilter.MaxFilter(2 * dilate_px + 1))
    if feather_px > 0:
        out = out.filter(ImageFilter.GaussianBlur(feather_px))
    return out


# ---------------------------------------------------------------------------
# GET /api/providers
# ---------------------------------------------------------------------------


def test_providers_list_has_impl_flags(api):
    client, _, _ = api
    resp = client.get("/api/providers")
    assert resp.status_code == 200, resp.text
    items = {i["id"]: i for i in resp.json()}
    assert items["qwen-inpaint"]["has_impl"] is True
    assert items["qwen-inpaint"]["kind"] == "image_edit"
    assert items["qwen-inpaint"]["endpoint"] == "fal-ai/qwen-image-edit/inpaint"
    # M4: flux-fill got a concrete impl (FluxFillProvider)
    assert items["flux-fill"]["has_impl"] is True
    assert items["kling-26-pro"]["has_impl"] is False


def test_providers_filter_by_kind(api):
    client, _, _ = api
    resp = client.get("/api/providers", params={"kind": "video"})
    assert resp.status_code == 200, resp.text
    ids = {i["id"] for i in resp.json()}
    assert ids == {"kling-26-pro", "wan-26", "seedance-25", "kling-15-pro"}
    assert all(i["kind"] == "video" for i in resp.json())


# ---------------------------------------------------------------------------
# ai-edit -- mask_b64 (brush mode)
# ---------------------------------------------------------------------------


def test_ai_edit_mask_b64_merges_without_replacing(api, monkeypatch):
    client, project_dir, project_id = api

    # Synthetic layer with fully known, fully transparent content so the
    # merge outcome is fully predictable (no dependency on real photo pixels).
    project = LayerProject.load(project_dir)
    layer = Layer(x=50, y=50, name="synthetic")
    layer.save_image(Image.new("RGBA", (100, 100), (128, 128, 128, 0)), project_dir)
    project.add_layer(layer)
    project.save(project_dir)

    def fake_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
        return Image.new("RGB", image.size, (10, 20, 200))

    monkeypatch.setattr(QwenInpaintProvider, "_run_remote", fake_run_remote)

    # Brush box in CANVAS coords (60,60)-(120,120) -- a subset of the layer's
    # own box (50,50)-(150,150), comfortably clear of its edges after dilate+feather.
    mask_arr = np.zeros((736, 544), dtype=np.uint8)
    mask_arr[60:120, 60:120] = 255
    mask_img = Image.fromarray(mask_arr, mode="L")

    resp = client.post(
        f"/api/projects/{project_id}/layers/{layer.id}/ai-edit",
        json={"prompt": "x", "mask_b64": _b64_png(mask_img)},
    )
    assert resp.status_code == 200, resp.text

    after = Image.open(BytesIO(client.get(f"/api/projects/{project_id}/layers/{layer.id}/png").content))
    after_arr = np.array(after.convert("RGBA"))

    feathered_full = np.array(_feathered(Image.fromarray(mask_arr, mode="L")))
    local_feathered = feathered_full[50:150, 50:150]  # layer's own box, y then x (symmetric here)
    outside = local_feathered == 0
    inside_solid = local_feathered == 255
    assert outside.any() and inside_solid.any()

    before_pixel = np.array([128, 128, 128, 0], dtype=np.uint8)
    assert np.all(after_arr[outside] == before_pixel), "pixels outside the feathered brush must stay bit-identical"
    assert np.all(after_arr[inside_solid][:, :3] == [10, 20, 200]), "deep inside the brush -> provider result"
    # Alpha must be EXPANDED (was 0 everywhere originally), not replaced/shrunk.
    assert np.all(after_arr[inside_solid][:, 3] == 255)


def test_ai_edit_mask_b64_wrong_size_400(api):
    client, _, project_id = api
    bad_mask = Image.new("L", (100, 100), 255)  # composite is 544x736

    resp = client.post(
        f"/api/projects/{project_id}/layers/{LAYER_3_ID}/ai-edit",
        json={"prompt": "x", "mask_b64": _b64_png(bad_mask)},
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "(100, 100)" in detail
    assert "(544, 736)" in detail


# ---------------------------------------------------------------------------
# inpaint-behind
# ---------------------------------------------------------------------------


def test_inpaint_behind_happy_path(api, monkeypatch):
    client, project_dir, project_id = api

    def fake_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
        return Image.new("RGB", image.size, (10, 200, 20))

    monkeypatch.setattr(QwenInpaintProvider, "_run_remote", fake_run_remote)

    before_bytes = client.get(f"/api/projects/{project_id}/layers/{LAYER_0_ID}/png").content
    before_arr = np.array(Image.open(BytesIO(before_bytes)).convert("RGBA"))

    resp = client.post(f"/api/projects/{project_id}/layers/{LAYER_3_ID}/inpaint-behind", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["layer"]["id"] == LAYER_0_ID  # lowest z_order OTHER visible layer
    assert body["provider"] == "qwen-inpaint"
    assert body["elapsed_s"] >= 0

    after_bytes = client.get(f"/api/projects/{project_id}/layers/{LAYER_0_ID}/png").content
    assert after_bytes != before_bytes
    after_arr = np.array(Image.open(BytesIO(after_bytes)).convert("RGBA"))

    # Layer 3's own thresholded+dilated+feathered alpha is the exact footprint
    # merged into Layer 0 -- both layers are canvas-sized at (0,0), so no
    # coordinate offset is needed to compare them directly.
    layer3_png = client.get(f"/api/projects/{project_id}/layers/{LAYER_3_ID}/png").content
    layer3_alpha = Image.open(BytesIO(layer3_png)).convert("RGBA").split()[-1]
    hard = layer3_alpha.point(lambda a: 255 if a > 127 else 0)
    feathered_arr = np.array(_feathered(hard))

    outside = feathered_arr == 0
    inside_solid = feathered_arr == 255
    assert outside.any() and inside_solid.any()

    assert np.array_equal(after_arr[outside], before_arr[outside]), "unchanged outside the removed element's footprint"
    assert np.all(after_arr[inside_solid][:, :3] == [10, 200, 20]), "filled with the provider result inside the footprint"

    # Project must reload cleanly and the edit must be snapshotted for undo.
    reloaded = LayerProject.load(project_dir)
    assert reloaded.get_layer(LAYER_0_ID) is not None
    hist_data = json.loads((project_dir / "history.json").read_text(encoding="utf-8"))
    assert len(hist_data["undo_stack"]) == 1


def test_inpaint_behind_no_other_visible_layer_400(api):
    client, _, project_id = api
    for lid in (LAYER_0_ID, LAYER_2_ID):
        r = client.post(f"/api/projects/{project_id}/layers/{lid}/visibility")
        assert r.status_code == 200, r.text
        assert r.json()["visible"] is False

    resp = client.post(f"/api/projects/{project_id}/layers/{LAYER_3_ID}/inpaint-behind", json={})
    assert resp.status_code == 400
    assert "no other visible layer" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# provider exceptions -> 502 (ai-edit + inpaint-behind)
# ---------------------------------------------------------------------------


def _raise_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
    raise RuntimeError("fal quota exceeded")


def test_ai_edit_provider_exception_502(api, monkeypatch):
    client, _, project_id = api
    monkeypatch.setattr(QwenInpaintProvider, "_run_remote", _raise_run_remote)

    resp = client.post(
        f"/api/projects/{project_id}/layers/{LAYER_3_ID}/ai-edit", json={"prompt": "x"}
    )
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert "fal quota exceeded" in detail
    assert "qwen-inpaint" in detail


def test_inpaint_behind_provider_exception_502(api, monkeypatch):
    client, _, project_id = api
    monkeypatch.setattr(QwenInpaintProvider, "_run_remote", _raise_run_remote)

    resp = client.post(f"/api/projects/{project_id}/layers/{LAYER_3_ID}/inpaint-behind", json={})
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert "fal quota exceeded" in detail
    assert "qwen-inpaint" in detail


# ---------------------------------------------------------------------------
# reorder
# ---------------------------------------------------------------------------


def test_reorder_changes_order_and_persists(api):
    client, project_dir, project_id = api

    resp = client.post(f"/api/projects/{project_id}/layers/{LAYER_0_ID}/reorder", json={"z_order": 10})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 4
    ids_in_order = [l["id"] for l in body]
    assert ids_in_order[-1] == LAYER_0_ID  # pushed to the back
    assert [l["z_order"] for l in body] == [0, 1, 2, 3]  # contiguous reindex

    reloaded = LayerProject.load(project_dir)
    reloaded_ids = [l.id for l in sorted(reloaded.layers, key=lambda l: l.z_order)]
    assert reloaded_ids == ids_in_order


def test_reorder_single_step_down(api):
    """Regression (user report, 2026-08-15): a +-1 move -- the only move the
    UI arrows produce -- was a silent no-op. Assign-and-stable-sort kept
    duplicate z_order keys in their original relative order, so _reindex
    restored the starting state."""
    client, _, project_id = api
    before = client.get(f"/api/projects/{project_id}/layers").json()
    top = max(before, key=lambda l: l["z_order"])
    resp = client.post(
        f"/api/projects/{project_id}/layers/{top['id']}/reorder",
        json={"z_order": top["z_order"] - 1},
    )
    assert resp.status_code == 200, resp.text
    body = sorted(resp.json(), key=lambda l: l["z_order"])
    assert body[-2]["id"] == top["id"]  # moved exactly one slot down
    assert [l["z_order"] for l in body] == list(range(len(body)))


def test_reorder_single_step_up(api):
    client, _, project_id = api
    before = client.get(f"/api/projects/{project_id}/layers").json()
    bottom = min(before, key=lambda l: l["z_order"])
    resp = client.post(
        f"/api/projects/{project_id}/layers/{bottom['id']}/reorder",
        json={"z_order": bottom["z_order"] + 1},
    )
    assert resp.status_code == 200, resp.text
    body = sorted(resp.json(), key=lambda l: l["z_order"])
    assert body[1]["id"] == bottom["id"]  # moved exactly one slot up
    assert [l["z_order"] for l in body] == list(range(len(body)))


def test_reorder_unknown_layer_404(api):
    client, _, project_id = api
    resp = client.post(f"/api/projects/{project_id}/layers/does-not-exist/reorder", json={"z_order": 0})
    assert resp.status_code == 404


def test_transform_snapshots_for_undo(api):
    """Regression (E2E finding, 2026-08-14): /transform was the only mutating
    route without _snapshot(), so moves/scales were invisible to undo/redo."""
    client, _, project_id = api

    r1 = client.post(
        f"/api/projects/{project_id}/layers/{LAYER_3_ID}/transform", json={"x": 100, "y": 50}
    )
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        f"/api/projects/{project_id}/layers/{LAYER_3_ID}/transform", json={"x": 200, "y": 90}
    )
    assert r2.status_code == 200, r2.text

    hist = client.get(f"/api/projects/{project_id}/history").json()
    assert hist["undo_count"] == 1

    undo = client.post(f"/api/projects/{project_id}/undo")
    assert undo.status_code == 200, undo.text

    layers = client.get(f"/api/projects/{project_id}/layers").json()
    l3 = next(l for l in layers if l["id"] == LAYER_3_ID)
    assert (l3["x"], l3["y"]) == (100, 50)
