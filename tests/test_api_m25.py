"""Tests for M2.5 API routes: project rename/duplicate + list metadata,
layer rename (with undo), and point-prompted segmentation. Fully offline --
projects are synthetic (built through the API itself, no decompose-test
fixture dependency) and _segment_remote / fal_client are monkeypatched,
same seams test_api_phase1.py uses.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from grafik.core.project import LayerProject


@pytest.fixture
def api(tmp_path, monkeypatch):
    """Returns (client, projects_dir) over an empty scratch projects directory."""
    import grafik.api.app as app_module

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    monkeypatch.setattr(app_module, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(app_module, "_histories", {})
    return TestClient(app_module.app), projects_dir


def _png_bytes(size=(32, 24), color=(255, 0, 0, 255)) -> bytes:
    buf = BytesIO()
    Image.new("RGBA", size, color).save(buf, "PNG")
    return buf.getvalue()


def _create_project(client, name="proj") -> dict:
    resp = client.post(
        "/api/projects", json={"name": name, "canvas_width": 32, "canvas_height": 24}
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


# ---------------------------------------------------------------------------
# GET /api/projects -- metadata + ordering
# ---------------------------------------------------------------------------


def test_list_projects_sorted_by_updated_desc_with_dates(api):
    client, projects_dir = api
    a = _create_project(client, "alpha")
    b = _create_project(client, "beta")
    # Pin timestamps directly in the manifests (any save() would overwrite
    # them) so the ordering assertion is deterministic.
    for pid, ts in ((a["id"], "2026-01-01T00:00:00+00:00"), (b["id"], "2026-02-01T00:00:00+00:00")):
        manifest = _dir_by_id(projects_dir, pid) / "project.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["updated_at"] = ts
        manifest.write_text(json.dumps(data), encoding="utf-8")

    items = client.get("/api/projects").json()
    assert [i["id"] for i in items] == [b["id"], a["id"]]
    assert all(i["created_at"] for i in items)
    assert items[0]["updated_at"] == "2026-02-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# PATCH /api/projects/{id} -- rename
# ---------------------------------------------------------------------------


def test_rename_project_persists_and_bumps_updated(api):
    client, _ = api
    a = _create_project(client, "old-name")
    resp = client.patch(f"/api/projects/{a['id']}", json={"name": "new-name"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "new-name"

    got = client.get(f"/api/projects/{a['id']}").json()
    assert got["name"] == "new-name"
    # ISO-8601 UTC strings compare chronologically as strings.
    assert got["updated_at"] >= a["updated_at"]


def test_rename_project_empty_400_unknown_404(api):
    client, _ = api
    a = _create_project(client)
    assert client.patch(f"/api/projects/{a['id']}", json={"name": "   "}).status_code == 400
    assert client.patch("/api/projects/does-not-exist", json={"name": "x"}).status_code == 404


# ---------------------------------------------------------------------------
# POST /api/projects/{id}/duplicate
# ---------------------------------------------------------------------------


def test_duplicate_project_new_id_copied_layers_no_history(api):
    client, projects_dir = api
    a = _create_project(client, "dupsrc")
    _add_layer(client, a["id"])
    src_dir = _dir_by_id(projects_dir, a["id"])
    # Simulate an existing undo history on the source: its snapshots embed the
    # source id, so the copy must NOT inherit the file.
    (src_dir / "history.json").write_text(
        json.dumps({"undo_stack": ["{}"], "redo_stack": [], "max_size": 20}), encoding="utf-8"
    )

    resp = client.post(f"/api/projects/{a['id']}/duplicate")
    assert resp.status_code == 200, resp.text
    dup = resp.json()
    assert dup["id"] != a["id"]
    assert dup["name"] == "dupsrc (kopie)"
    assert dup["layer_count"] == 1

    dup_dir = _dir_by_id(projects_dir, dup["id"])
    assert dup_dir.name == "dupsrc-kopie.grafik"
    assert not (dup_dir / "history.json").exists()
    assert (src_dir / "history.json").exists()  # source untouched

    dup_proj = LayerProject.load(dup_dir)
    assert (dup_dir / dup_proj.layers[0].png_path).exists()

    # Second duplicate of the same source lands in a numbered directory.
    resp2 = client.post(f"/api/projects/{a['id']}/duplicate")
    assert resp2.status_code == 200, resp2.text
    dup2_dir = _dir_by_id(projects_dir, resp2.json()["id"])
    assert dup2_dir.name == "dupsrc-kopie-2.grafik"


# ---------------------------------------------------------------------------
# DELETE /api/projects/{id}
# ---------------------------------------------------------------------------


def test_delete_project_removes_dir_and_listing(api):
    client, projects_dir = api
    a = _create_project(client, "gone")
    src_dir = _dir_by_id(projects_dir, a["id"])
    resp = client.delete(f"/api/projects/{a['id']}")
    assert resp.status_code == 200, resp.text
    assert not src_dir.exists()
    assert a["id"] not in {i["id"] for i in client.get("/api/projects").json()}


# ---------------------------------------------------------------------------
# POST /api/projects/{id}/layers/{layer_id}/rename
# ---------------------------------------------------------------------------


def test_rename_layer_persists_and_undoes(api):
    client, projects_dir = api
    a = _create_project(client)
    layer = _add_layer(client, a["id"])

    r1 = client.post(f"/api/projects/{a['id']}/layers/{layer['id']}/rename", json={"name": "jedna"})
    assert r1.status_code == 200, r1.text
    assert r1.json()["name"] == "jedna"
    r2 = client.post(f"/api/projects/{a['id']}/layers/{layer['id']}/rename", json={"name": "dva"})
    assert r2.status_code == 200, r2.text

    proj = LayerProject.load(_dir_by_id(projects_dir, a["id"]))
    assert proj.get_layer(layer["id"]).name == "dva"

    # Two renames pushed two snapshots -> undo restores the first one.
    assert client.post(f"/api/projects/{a['id']}/undo").status_code == 200
    proj = LayerProject.load(_dir_by_id(projects_dir, a["id"]))
    assert proj.get_layer(layer["id"]).name == "jedna"


def test_rename_layer_empty_400_unknown_404(api):
    client, _ = api
    a = _create_project(client)
    layer = _add_layer(client, a["id"])
    assert (
        client.post(f"/api/projects/{a['id']}/layers/{layer['id']}/rename", json={"name": " "}).status_code
        == 400
    )
    assert (
        client.post(f"/api/projects/{a['id']}/layers/nope/rename", json={"name": "x"}).status_code == 404
    )


# ---------------------------------------------------------------------------
# POST /api/projects/{id}/segment -- point mode
# ---------------------------------------------------------------------------


def test_segment_points_only_passes_points_and_names_layer(api, monkeypatch):
    client, projects_dir = api
    import grafik.api.app as app_module

    a = _create_project(client)
    _add_layer(client, a["id"])

    seen = {}

    def fake_segment_remote(image, text, endpoint, points=None):
        seen["text"] = text
        seen["points"] = points
        return [Image.new("L", image.size, 255)]

    monkeypatch.setattr(app_module, "_segment_remote", fake_segment_remote)

    resp = client.post(f"/api/projects/{a['id']}/segment", json={"points": [{"x": 10, "y": 12}]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mask_count"] == 1
    assert body["layers"][0]["name"] == "sam: bod (10,12)"
    assert body["layers"][0]["tags"] == ["sam"]
    assert seen["text"] == ""
    assert [(p.x, p.y, p.label) for p in seen["points"]] == [(10, 12, 1)]


def test_segment_without_text_and_points_400(api):
    client, _ = api
    a = _create_project(client)
    resp = client.post(f"/api/projects/{a['id']}/segment", json={})
    assert resp.status_code == 400


def test_segment_remote_point_only_omits_prompt_key(monkeypatch):
    """The real payload builder: point-only calls must not send a `prompt`
    key at all (design decision around the schema's default "wheel" -- see
    _segment_remote docstring), text calls must."""
    import grafik.api.app as app_module
    from grafik.api.models import SegmentPoint

    captured = {}

    def fake_subscribe(endpoint, arguments, with_logs):
        captured["arguments"] = arguments
        return {"masks": [{"url": "https://fake/mask.png"}]}

    monkeypatch.setattr("fal_client.subscribe", fake_subscribe)
    monkeypatch.setattr("grafik.fal.upload.upload_image", lambda img: "https://fake/img.png")
    monkeypatch.setattr("grafik.fal.upload.download_url", lambda url: Image.new("RGBA", (8, 8)))

    img = Image.new("RGBA", (8, 8))
    masks = app_module._segment_remote(img, "", "fal-ai/sam-3/image", points=[SegmentPoint(x=3, y=4)])
    assert len(masks) == 1
    assert "prompt" not in captured["arguments"]
    assert captured["arguments"]["point_prompts"] == [{"x": 3, "y": 4, "label": 1}]

    app_module._segment_remote(img, "socha", "fal-ai/sam-3/image", points=[SegmentPoint(x=3, y=4)])
    assert captured["arguments"]["prompt"] == "socha"
    assert captured["arguments"]["point_prompts"] == [{"x": 3, "y": 4, "label": 1}]
