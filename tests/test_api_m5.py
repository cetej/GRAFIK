"""Tests for M5 API integration layer: SAM box + multi-point segmentation,
NB Pro reference images, crop_inpaint plumbing (ai-edit / inpaint-behind),
and trash per-entry purge + undo-after-restore. Fully offline — network
seams are monkeypatched (fal_client.subscribe, _segment_remote,
provider.edit/generate), projects are synthetic (built through the API
itself), same idioms as test_api_m25.py / test_api_m4.py.
"""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import grafik.core.costs as costs
from grafik.core.project import LayerProject


@pytest.fixture
def api(tmp_path, monkeypatch):
    """(client, projects_dir, logs_dir) over scratch dirs; session costs reset."""
    import grafik.api.app as app_module

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    logs_dir = tmp_path / "logs"
    monkeypatch.setattr(app_module, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(app_module, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(app_module, "_histories", {})
    costs.reset_session()
    return TestClient(app_module.app), projects_dir, logs_dir


def _png_bytes(size=(32, 24), color=(255, 0, 0, 255)) -> bytes:
    buf = BytesIO()
    Image.new("RGBA", size, color).save(buf, "PNG")
    return buf.getvalue()


def _png_b64(size=(6, 6), color=(1, 2, 3, 255)) -> str:
    return base64.b64encode(_png_bytes(size, color)).decode("ascii")


def _create_project(client, name="proj") -> dict:
    resp = client.post(
        "/api/projects", json={"name": name, "canvas_width": 64, "canvas_height": 48}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _add_layer(client, project_id, filename="l.png") -> dict:
    resp = client.post(
        f"/api/projects/{project_id}/layers",
        files={"file": (filename, _png_bytes(), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _dir_by_id(projects_dir: Path, project_id: str) -> Path:
    for p in projects_dir.iterdir():
        manifest = p / "project.json"
        if p.is_dir() and manifest.exists():
            if json.loads(manifest.read_text(encoding="utf-8")).get("id") == project_id:
                return p
    raise AssertionError(f"no project dir for id {project_id}")


def _destructive_ops(logs_dir: Path) -> list[dict]:
    log = logs_dir / "destructive.jsonl"
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# SAM box + multi-point segmentation
# ---------------------------------------------------------------------------


def test_segment_remote_boxes_payload_shape(monkeypatch):
    """Payload-level: real _segment_remote, network seams monkeypatched.
    box_prompts carries the raw-OpenAPI BoxPrompt keys, prompt is still "" for
    a box-only call (same load-bearing rule as point-only calls)."""
    import grafik.api.app as app_module
    from grafik.api.models import SegmentBox

    captured = {}

    def fake_subscribe(endpoint, arguments, with_logs=False):
        captured["arguments"] = arguments
        return {"masks": [{"url": "https://fake/mask.png"}]}

    monkeypatch.setattr("fal_client.subscribe", fake_subscribe)
    monkeypatch.setattr("grafik.fal.upload.upload_image", lambda img: "https://fake/img.png")
    monkeypatch.setattr("grafik.fal.upload.download_url", lambda url: Image.new("RGBA", (8, 8)))

    img = Image.new("RGBA", (8, 8))
    box = SegmentBox(x_min=1, y_min=2, x_max=30, y_max=40)
    masks = app_module._segment_remote(img, "", "fal-ai/sam-3/image", boxes=[box])

    assert len(masks) == 1
    assert captured["arguments"]["prompt"] == ""
    assert captured["arguments"]["box_prompts"] == [
        {"x_min": 1, "y_min": 2, "x_max": 30, "y_max": 40}
    ]


def test_segment_remote_points_object_id_included_or_omitted(monkeypatch):
    """Two points sharing object_id=0 -> both dicts carry it (schema field
    that groups points onto one object). A point with object_id=None ->
    the key is absent from the dict entirely, never sent as null."""
    import grafik.api.app as app_module
    from grafik.api.models import SegmentPoint

    captured = {}

    def fake_subscribe(endpoint, arguments, with_logs=False):
        captured["arguments"] = arguments
        return {"masks": [{"url": "https://fake/mask.png"}]}

    monkeypatch.setattr("fal_client.subscribe", fake_subscribe)
    monkeypatch.setattr("grafik.fal.upload.upload_image", lambda img: "https://fake/img.png")
    monkeypatch.setattr("grafik.fal.upload.download_url", lambda url: Image.new("RGBA", (8, 8)))

    img = Image.new("RGBA", (8, 8))
    pts = [SegmentPoint(x=1, y=2, object_id=0), SegmentPoint(x=3, y=4, object_id=0)]
    app_module._segment_remote(img, "", "fal-ai/sam-3/image", points=pts)
    assert captured["arguments"]["point_prompts"] == [
        {"x": 1, "y": 2, "label": 1, "object_id": 0},
        {"x": 3, "y": 4, "label": 1, "object_id": 0},
    ]

    pts_no_oid = [SegmentPoint(x=5, y=6)]
    app_module._segment_remote(img, "", "fal-ai/sam-3/image", points=pts_no_oid)
    assert captured["arguments"]["point_prompts"] == [{"x": 5, "y": 6, "label": 1}]
    assert "object_id" not in captured["arguments"]["point_prompts"][0]


def test_segment_route_passes_boxes_through(api, monkeypatch):
    """Route-level: /segment forwards req.boxes as SegmentBox models into
    _segment_remote's boxes kwarg (only when non-empty -- see the route's
    remote_kwargs comment for why)."""
    client, _, _ = api
    import grafik.api.app as app_module

    a = _create_project(client)
    _add_layer(client, a["id"])

    seen = {}

    def fake_segment_remote(image, text, endpoint, points=None, boxes=None):
        seen["boxes"] = boxes
        seen["points"] = points
        return [Image.new("L", image.size, 255)]

    monkeypatch.setattr(app_module, "_segment_remote", fake_segment_remote)

    resp = client.post(
        f"/api/projects/{a['id']}/segment",
        json={"boxes": [{"x_min": 1, "y_min": 2, "x_max": 30, "y_max": 40}]},
    )
    assert resp.status_code == 200, resp.text
    assert len(seen["boxes"]) == 1
    b0 = seen["boxes"][0]
    assert (b0.x_min, b0.y_min, b0.x_max, b0.y_max) == (1, 2, 30, 40)


def test_segment_no_text_points_boxes_400(api):
    client, _, _ = api
    a = _create_project(client)
    resp = client.post(f"/api/projects/{a['id']}/segment", json={})
    assert resp.status_code == 400


def test_segment_layer_naming_for_box_and_multipoint(api, monkeypatch):
    client, _, _ = api
    import grafik.api.app as app_module

    a = _create_project(client)
    _add_layer(client, a["id"])

    def fake_segment_remote(image, text, endpoint, points=None, boxes=None):
        return [Image.new("L", image.size, 255)]

    monkeypatch.setattr(app_module, "_segment_remote", fake_segment_remote)

    resp_box = client.post(
        f"/api/projects/{a['id']}/segment",
        json={"boxes": [{"x_min": 1, "y_min": 2, "x_max": 30, "y_max": 40}]},
    )
    assert resp_box.status_code == 200, resp_box.text
    assert resp_box.json()["layers"][0]["name"] == "sam: box (1,2)–(30,40)"

    resp_multi = client.post(
        f"/api/projects/{a['id']}/segment",
        json={"points": [{"x": 1, "y": 2}, {"x": 3, "y": 4}]},
    )
    assert resp_multi.status_code == 200, resp_multi.text
    assert resp_multi.json()["layers"][0]["name"] == "sam: 2 bodů"

    # Single point stays unchanged (pre-M5 behaviour).
    resp_single = client.post(
        f"/api/projects/{a['id']}/segment",
        json={"points": [{"x": 9, "y": 10}]},
    )
    assert resp_single.status_code == 200, resp_single.text
    assert resp_single.json()["layers"][0]["name"] == "sam: bod (9,10)"


# ---------------------------------------------------------------------------
# NB Pro reference images
# ---------------------------------------------------------------------------


def test_generate_image_references_forwarded_as_pil(api, monkeypatch):
    from grafik.providers.nbpro import NanoBananaProProvider

    client, _, _ = api
    seen = {}

    def fake_generate(self, prompt, **kw):
        seen.update(kw)
        return Image.new("RGBA", (8, 8))

    monkeypatch.setattr(NanoBananaProProvider, "generate", fake_generate)

    resp = client.post(
        "/api/generate-image",
        json={"prompt": "kočka", "reference_b64": [_png_b64((5, 5)), _png_b64((7, 7))]},
    )
    assert resp.status_code == 200, resp.text
    refs = seen["reference_images"]
    assert len(refs) == 2
    assert all(isinstance(r, Image.Image) for r in refs)
    assert {r.size for r in refs} == {(5, 5), (7, 7)}
    assert resp.json()["cost"]["note"].endswith("+2 ref")


def test_generate_image_no_references_omits_ref_suffix(api, monkeypatch):
    from grafik.providers.nbpro import NanoBananaProProvider

    client, _, _ = api
    seen = {}

    def fake_generate(self, prompt, **kw):
        seen.update(kw)
        return Image.new("RGBA", (8, 8))

    monkeypatch.setattr(NanoBananaProProvider, "generate", fake_generate)

    resp = client.post("/api/generate-image", json={"prompt": "pes"})
    assert resp.status_code == 200, resp.text
    assert seen["reference_images"] == []
    assert "ref" not in resp.json()["cost"]["note"]


def test_generate_image_too_many_references_400(api):
    client, _, _ = api
    resp = client.post(
        "/api/generate-image",
        json={"prompt": "x", "reference_b64": [_png_b64() for _ in range(4)]},
    )
    assert resp.status_code == 400
    assert "3" in resp.json()["detail"]


def test_generate_image_invalid_reference_b64_400(api):
    client, _, _ = api
    garbage = base64.b64encode(b"not a real image").decode("ascii")
    resp = client.post("/api/generate-image", json={"prompt": "x", "reference_b64": [garbage]})
    assert resp.status_code == 400
    assert "0" in resp.json()["detail"]  # index of the bad reference


# ---------------------------------------------------------------------------
# crop_inpaint plumbing (ai-edit / inpaint-behind)
# ---------------------------------------------------------------------------


def test_ai_edit_forwards_crop_inpaint_default_and_explicit(api, monkeypatch):
    from grafik.providers.qwen_inpaint import QwenInpaintProvider

    client, _, _ = api
    a = _create_project(client)
    layer = _add_layer(client, a["id"])

    seen = {}

    def fake_edit(self, image, mask, prompt, **kw):
        seen["crop_inpaint"] = kw.get("crop_inpaint")
        return Image.new("RGB", image.size, (1, 2, 3))

    monkeypatch.setattr(QwenInpaintProvider, "edit", fake_edit)

    resp = client.post(
        f"/api/projects/{a['id']}/layers/{layer['id']}/ai-edit", json={"prompt": "x"}
    )
    assert resp.status_code == 200, resp.text
    assert seen["crop_inpaint"] is True  # AiEditRequest default

    resp2 = client.post(
        f"/api/projects/{a['id']}/layers/{layer['id']}/ai-edit",
        json={"prompt": "x", "crop_inpaint": False},
    )
    assert resp2.status_code == 200, resp2.text
    assert seen["crop_inpaint"] is False


def test_inpaint_behind_forwards_crop_inpaint_default_and_explicit(api, monkeypatch):
    from grafik.providers.qwen_inpaint import QwenInpaintProvider

    client, _, _ = api
    a = _create_project(client)
    bg = _add_layer(client, a["id"], "bg.png")
    fg = _add_layer(client, a["id"], "fg.png")

    seen = {}

    def fake_edit(self, image, mask, prompt, **kw):
        seen["crop_inpaint"] = kw.get("crop_inpaint")
        return Image.new("RGB", image.size, (9, 9, 9))

    monkeypatch.setattr(QwenInpaintProvider, "edit", fake_edit)

    resp = client.post(f"/api/projects/{a['id']}/layers/{fg['id']}/inpaint-behind", json={})
    assert resp.status_code == 200, resp.text
    assert seen["crop_inpaint"] is True  # InpaintBehindRequest default

    resp2 = client.post(
        f"/api/projects/{a['id']}/layers/{fg['id']}/inpaint-behind",
        json={"crop_inpaint": False},
    )
    assert resp2.status_code == 200, resp2.text
    assert seen["crop_inpaint"] is False


# ---------------------------------------------------------------------------
# Trash: per-entry purge + undo-after-restore
# ---------------------------------------------------------------------------


def test_purge_single_trash_entry(api):
    client, projects_dir, logs_dir = api
    a = _create_project(client, "keep-me")
    b = _create_project(client, "purge-me")
    entry_a = client.delete(f"/api/projects/{a['id']}").json()["trash_entry"]
    entry_b = client.delete(f"/api/projects/{b['id']}").json()["trash_entry"]
    assert len(client.get("/api/trash").json()) == 2

    resp = client.delete(f"/api/trash/{entry_b}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["purged"] == entry_b

    remaining = client.get("/api/trash").json()
    assert len(remaining) == 1
    assert remaining[0]["entry"] == entry_a
    assert not (projects_dir / ".trash" / entry_b).exists()
    assert (projects_dir / ".trash" / entry_a).exists()

    ops = _destructive_ops(logs_dir)
    assert ops[-1]["op"] == "trash-purge-entry" and ops[-1]["entry"] == entry_b


def test_purge_single_trash_entry_unknown_404(api):
    client, _, _ = api
    assert client.delete("/api/trash/does-not-exist").status_code == 404


def test_undo_after_restore_from_trash(api):
    """Reveals whether undo survives a delete->restore roundtrip: history.json
    travels inside the .grafik dir (soft-delete moves the whole directory),
    and _histories is popped on delete, so /undo must lazy-load it back from
    disk via _get_history. No app.py undo/trash logic is changed here -- this
    test only records the CURRENT behaviour."""
    client, projects_dir, _ = api
    a = _create_project(client, "undo-after-restore")
    layer = _add_layer(client, a["id"])

    # can_undo() requires undo_stack length > 1 (grafik/core/history.py), so
    # a single snapshot-pushing mutation isn't enough -- two renames, like
    # test_api_m25's test_rename_layer_persists_and_undoes.
    r1 = client.post(
        f"/api/projects/{a['id']}/layers/{layer['id']}/rename", json={"name": "jedna"}
    )
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        f"/api/projects/{a['id']}/layers/{layer['id']}/rename", json={"name": "dva"}
    )
    assert r2.status_code == 200, r2.text

    src_dir = _dir_by_id(projects_dir, a["id"])
    assert (src_dir / "history.json").exists()

    entry = client.delete(f"/api/projects/{a['id']}").json()["trash_entry"]
    restored = client.post(f"/api/trash/{entry}/restore").json()
    assert restored["id"] == a["id"]  # no id collision here -> id is preserved

    resp = client.post(f"/api/projects/{a['id']}/undo")
    assert resp.status_code == 200, resp.text
    assert resp.json()["undone"] is True

    proj_dir = _dir_by_id(projects_dir, a["id"])
    proj = LayerProject.load(proj_dir)
    assert proj.get_layer(layer["id"]).name == "jedna"
