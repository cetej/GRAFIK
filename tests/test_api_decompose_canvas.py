"""Decompose vs. canvas geometry. fal I2L returns layers at the model's
native resolution (~0.4 MP, empirically 544x736 for a 3:4 input) regardless
of the input image size, while POST /decompose/file auto-sets the canvas
from the *uploaded* image. Without layout scaling the composite ends up
with content only in the top-left (0,0,544,736) box of e.g. a 1792x2400
canvas (restored project openart 75778f1bd1a4, 2026-08-15).

Fully offline -- fal_client.subscribe, the client's download_url binding
and upload_image are monkeypatched, same seams as test_api_m25.py.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from grafik.core.project import LayerProject

FAL_NATIVE = (544, 736)  # empirical I2L output for a 3:4 input
UPLOAD_SIZE = (1792, 2400)  # openart source image


@pytest.fixture
def api(tmp_path, monkeypatch):
    """Returns (client, projects_dir) over an empty scratch projects directory."""
    import grafik.api.app as app_module

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    monkeypatch.setattr(app_module, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(app_module, "_histories", {})
    return TestClient(app_module.app), projects_dir


def _png_bytes(size, color=(40, 90, 200, 255)) -> bytes:
    buf = BytesIO()
    Image.new("RGBA", size, color).save(buf, "PNG")
    return buf.getvalue()


def _create_project(client, name="proj", width=0, height=0) -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": name, "canvas_width": width, "canvas_height": height},
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


def _mock_fal(monkeypatch, layer_count=2, fal_size=FAL_NATIVE):
    """fal I2L seam: subscribe returns layer URLs, download returns opaque
    full-frame RGBA images at the model's native resolution -- deliberately
    NOT the size of the input/uploaded image."""

    def fake_subscribe(model, arguments, with_logs=False):
        return {"layers": [{"url": f"https://fake/layer{i}.png"} for i in range(layer_count)]}

    monkeypatch.setattr("fal_client.subscribe", fake_subscribe)
    # client.py binds download_url at import time -> patch the binding
    monkeypatch.setattr(
        "grafik.fal.client.download_url",
        lambda url: Image.new("RGBA", fal_size, (200, 30, 30, 255)),
    )
    monkeypatch.setattr("grafik.fal.upload.upload_image", lambda img: "https://fake/uploaded.png")


# ---------------------------------------------------------------------------
# POST /decompose/file -- canvas from upload, layers from fal
# ---------------------------------------------------------------------------


def test_decompose_file_scales_layout_to_upload_canvas(api, monkeypatch):
    """Canvas stays at upload dimensions, layer *layout* is stretched onto it
    (variant a); pixel data on disk keeps fal's native resolution -- the
    composer resizes at compose time, mirroring the inpaint resize-back."""
    client, projects_dir = api
    a = _create_project(client)  # canvas 0x0 -> auto-set from upload
    _mock_fal(monkeypatch)

    resp = client.post(
        f"/api/projects/{a['id']}/decompose/file",
        files={"file": ("photo.png", _png_bytes(UPLOAD_SIZE), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    layers = resp.json()
    assert len(layers) == 2
    for l in layers:
        assert (l["x"], l["y"]) == (0, 0)
        assert (l["width"], l["height"]) == UPLOAD_SIZE

    proj_dir = _dir_by_id(projects_dir, a["id"])
    proj = LayerProject.load(proj_dir)
    assert (proj.canvas_width, proj.canvas_height) == UPLOAD_SIZE
    # pixel data stays native -- only the layout scales
    for layer in proj.layers:
        assert Image.open(proj_dir / layer.png_path).size == FAL_NATIVE


def test_composite_covers_full_canvas_after_file_decompose(api, monkeypatch):
    """The bug symptom itself: before the fix the 1792x2400 composite was
    transparent outside the (0,0,544,736) box."""
    client, projects_dir = api
    a = _create_project(client)
    _mock_fal(monkeypatch, layer_count=1)

    resp = client.post(
        f"/api/projects/{a['id']}/decompose/file",
        files={"file": ("photo.png", _png_bytes(UPLOAD_SIZE), "image/png")},
    )
    assert resp.status_code == 200, resp.text

    comp = client.get(f"/api/projects/{a['id']}/composite")
    assert comp.status_code == 200, comp.text
    img = Image.open(BytesIO(comp.content))
    assert img.size == UPLOAD_SIZE
    # bottom-right corner, far outside the fal-native box, must be opaque
    assert img.getpixel((UPLOAD_SIZE[0] - 1, UPLOAD_SIZE[1] - 1))[3] == 255


# ---------------------------------------------------------------------------
# POST /decompose (URL) -- both canvas states
# ---------------------------------------------------------------------------


def test_decompose_url_without_canvas_keeps_native_dims(api, monkeypatch):
    """Backward compat: no pre-set canvas -> canvas adopts fal's output size
    and no scaling happens. This is the exact shape of the existing e2e-sc1
    and decompose-test projects (canvas == layers == 544x736)."""
    client, projects_dir = api
    a = _create_project(client)
    _mock_fal(monkeypatch, layer_count=1)

    resp = client.post(
        f"/api/projects/{a['id']}/decompose", json={"image_url": "https://fake/src.png"}
    )
    assert resp.status_code == 200, resp.text
    l = resp.json()[0]
    assert (l["width"], l["height"]) == FAL_NATIVE
    assert (l["x"], l["y"]) == (0, 0)

    proj = LayerProject.load(_dir_by_id(projects_dir, a["id"]))
    assert (proj.canvas_width, proj.canvas_height) == FAL_NATIVE


def test_decompose_url_into_preset_canvas_scales_layout(api, monkeypatch):
    """The fix lives in FalClient.decompose, so a project created with an
    explicit canvas gets scaled layers through the URL endpoint too."""
    client, projects_dir = api
    a = _create_project(client, width=1920, height=1080)
    _mock_fal(monkeypatch, layer_count=1, fal_size=(640, 352))

    resp = client.post(
        f"/api/projects/{a['id']}/decompose", json={"image_url": "https://fake/src.png"}
    )
    assert resp.status_code == 200, resp.text
    l = resp.json()[0]
    assert (l["width"], l["height"]) == (1920, 1080)

    proj_dir = _dir_by_id(projects_dir, a["id"])
    proj = LayerProject.load(proj_dir)
    assert (proj.canvas_width, proj.canvas_height) == (1920, 1080)
    assert Image.open(proj_dir / proj.layers[0].png_path).size == (640, 352)
