"""Regression tests for POST /hittest (M2 E2E finding, 2026-08-14).

The route used to read alpha at native-PNG coords (lx = x - layer.x),
ignoring layer.width/height stretch and rotation, so its answer diverged
from the client Konva alpha hit-test whenever layout dims != PNG dims
(layer scaled in editor, or decompose stored different dims). These tests
pin the shared transform model: native PNG -> stretch to width/height ->
rotate clockwise around the (x, y) anchor (Konva/composer semantics).

Fixture `api` mirrors test_api_phase1.py / test_api_m2.py: scratch copy of
the real, read-only decompose-test.grafik with grafik.api.app.PROJECTS_DIR
and _histories monkeypatched. Fully offline, no provider calls.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from grafik.core.layer import Layer
from grafik.core.project import LayerProject

REAL_PROJECT_DIR = Path("C:/Users/stock/Documents/000_NGM/GRAFIK/projects/decompose-test.grafik")


@pytest.fixture
def api(tmp_path, monkeypatch):
    """Returns (client, project_dir, project_id) over a scratch copy of decompose-test.grafik."""
    import grafik.api.app as app_module

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    project_dir = projects_dir / "decompose-test.grafik"
    shutil.copytree(REAL_PROJECT_DIR, project_dir)
    project_id = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))["id"]

    monkeypatch.setattr(app_module, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(app_module, "_histories", {})

    return TestClient(app_module.app), project_dir, project_id


def _add_top_layer(project_dir: Path, **layer_kwargs) -> str:
    """Adds a topmost layer with a 100x100 native PNG: columns 0-49 opaque,
    columns 50-99 alpha 0. Known pixels -> every hit/miss below is derived
    by hand from the transform model, independent of the route's own math."""
    project = LayerProject.load(project_dir)
    img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (50, 100), (255, 0, 0, 255)), (0, 0))
    layer = Layer(name="hit-synthetic", **layer_kwargs)
    layer.save_image(img, project_dir)
    project.add_layer(layer)  # z_order defaults to len(layers) -> topmost
    project.save(project_dir)
    return layer.id


def _hit(client, project_id: str, x: int, y: int) -> str | None:
    resp = client.post(f"/api/projects/{project_id}/hittest", json={"x": x, "y": y})
    assert resp.status_code == 200, resp.text
    return resp.json()["layer_id"]


def test_hittest_native_size_layer(api):
    """Baseline: layout dims == PNG dims (save_image fills width/height)."""
    client, project_dir, project_id = api
    layer_id = _add_top_layer(project_dir, x=400, y=50)

    assert _hit(client, project_id, 420, 60) == layer_id  # native (20, 10), opaque
    assert _hit(client, project_id, 470, 60) != layer_id  # native (70, 10), alpha 0
    assert _hit(client, project_id, 420, 160) != layer_id  # below the layer box

    resp = client.post(f"/api/projects/{project_id}/hittest", json={"x": 420, "y": 60})
    body = resp.json()
    assert body["layer_name"] == "hit-synthetic"
    assert body["z_order"] == 4


def test_hittest_respects_layout_scale(api):
    """Layer stretched 2x: layout 200x200 over a 100x100 PNG at (100, 100).
    Rendered opaque region is canvas x in [100, 200) -- native coords must be
    rescaled, not read directly."""
    client, project_dir, project_id = api
    layer_id = _add_top_layer(project_dir, x=100, y=100, width=200, height=200)

    # Native (5, 5): hit under both old and new math -- sanity anchor.
    assert _hit(client, project_id, 110, 110) == layer_id
    # Native (40, 25): opaque. Old math read native (80, 50) = transparent.
    assert _hit(client, project_id, 180, 150) == layer_id
    # Native (15, 80): opaque. Old math had ly=160 -> out of native bounds.
    assert _hit(client, project_id, 130, 260) == layer_id
    # Native (75, 25): transparent right half -> falls through to layers below.
    assert _hit(client, project_id, 250, 150) != layer_id


def test_hittest_respects_rotation_and_scale_order(api):
    """Layout 200x100 rotated 90deg cw around anchor (300, 300). Forward map:
    native (nx, ny) -> layout (2nx, ny) -> canvas (300 - ly, 300 + lx), so the
    layer renders into x in (200, 300], y in [300, 500), opaque y < 400.
    Inverse must un-rotate FIRST, then rescale (Konva/composer order)."""
    client, project_dir, project_id = api
    layer_id = _add_top_layer(project_dir, x=300, y=300, width=200, height=100, rotation=90.0)

    # Layout (10, 10) -> native (~5, 10): opaque. Old math: lx=-10 -> miss.
    assert _hit(client, project_id, 290, 310) == layer_id
    # Layout (80, 50) -> native (~40, 50): opaque. Scale-before-rotate would
    # read native (80, 25) = transparent -- pins the order of operations.
    assert _hit(client, project_id, 250, 380) == layer_id
    # Layout (120, 50) -> native (~60, 50): transparent.
    assert _hit(client, project_id, 250, 420) != layer_id
