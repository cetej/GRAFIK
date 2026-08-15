"""Tests for M6-UX1 API routes: text-layer detection (SAM "letters" concept)
+ rewrite, and cached project thumbnails. Fully offline -- projects are
synthetic (built directly through Layer/LayerProject, no decompose-test
fixture dependency) and grafik.api.app._segment_remote /
QwenInpaintProvider._run_remote are monkeypatched, same seams
test_api_m25.py and test_api_m2.py use.
"""

from __future__ import annotations

import json
import os
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from grafik.core.layer import Layer
from grafik.core.project import LayerProject
from grafik.providers.qwen_inpaint import QwenInpaintProvider


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


def _create_project(client, name="proj", width=32, height=24) -> dict:
    resp = client.post(
        "/api/projects", json={"name": name, "canvas_width": width, "canvas_height": height}
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


def _add_synthetic_layer(project: LayerProject, project_dir: Path, name: str, x: int, y: int, w: int, h: int, color) -> Layer:
    layer = Layer(name=name, x=x, y=y)
    layer.save_image(Image.new("RGBA", (w, h), color), project_dir)
    project.add_layer(layer)
    return layer


# ---------------------------------------------------------------------------
# Layer model: backward compat + round-trip of the new text fields
# ---------------------------------------------------------------------------


def test_layer_model_loads_old_manifest_with_defaults_and_roundtrips(tmp_path):
    old_manifest = {
        "id": "proj1",
        "name": "old",
        "canvas_width": 10,
        "canvas_height": 10,
        "layers": [
            {"id": "L1", "name": "layer1", "z_order": 0, "png_path": "layers/L1.png"}
        ],
    }
    d = tmp_path / "old.grafik"
    d.mkdir()
    (d / "project.json").write_text(json.dumps(old_manifest), encoding="utf-8")

    project = LayerProject.load(d)
    layer = project.layers[0]
    assert layer.is_text is False
    assert layer.text_score is None
    assert layer.text_original is None
    assert layer.text_current is None

    layer.is_text = True
    layer.text_score = 0.87
    layer.text_original = "Vitejte"
    layer.text_current = "Welcome"
    project.save(d)

    reloaded = LayerProject.load(d)
    rl = reloaded.layers[0]
    assert rl.is_text is True
    assert rl.text_score == 0.87
    assert rl.text_original == "Vitejte"
    assert rl.text_current == "Welcome"


# ---------------------------------------------------------------------------
# GET /api/projects/{id}/thumbnail
# ---------------------------------------------------------------------------


def test_thumbnail_cache_hit_and_regeneration(api):
    client, projects_dir = api
    a = _create_project(client, "thumbs", width=800, height=600)
    _add_layer(client, a["id"])
    project_dir = _dir_by_id(projects_dir, a["id"])

    r1 = client.get(f"/api/projects/{a['id']}/thumbnail")
    assert r1.status_code == 200, r1.text
    assert r1.headers["content-type"] == "image/png"
    img = Image.open(BytesIO(r1.content))
    assert max(img.size) <= 256
    assert img.size != (800, 600)  # actually downscaled, not passed through

    thumb_path = project_dir / "thumb.png"
    assert thumb_path.exists()
    mtime_1 = thumb_path.stat().st_mtime

    r2 = client.get(f"/api/projects/{a['id']}/thumbnail")
    assert r2.status_code == 200, r2.text
    assert thumb_path.stat().st_mtime == mtime_1  # cache hit -- file untouched

    # Backdate the cached thumbnail so a fresh project.save() (new mtime) is
    # unambiguously newer, regardless of filesystem mtime-resolution granularity.
    os.utime(thumb_path, (mtime_1 - 10, mtime_1 - 10))
    project = LayerProject.load(project_dir)
    project.save(project_dir)

    r3 = client.get(f"/api/projects/{a['id']}/thumbnail")
    assert r3.status_code == 200, r3.text
    assert thumb_path.stat().st_mtime > mtime_1 - 10  # regenerated, not the backdated cache


def test_thumbnail_empty_project_404(api):
    client, _ = api
    resp = client.post("/api/projects", json={"name": "empty"})
    assert resp.status_code == 200, resp.text
    project_id = resp.json()["id"]

    r = client.get(f"/api/projects/{project_id}/thumbnail")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/projects/{id}/detect-text
# ---------------------------------------------------------------------------


def test_detect_text_scores_and_flags_layers(api, monkeypatch):
    client, projects_dir = api
    import grafik.api.app as app_module

    a = _create_project(client, "detect", width=40, height=40)
    project_dir = _dir_by_id(projects_dir, a["id"])
    project = LayerProject.load(project_dir)

    _add_synthetic_layer(project, project_dir, "bg", 0, 0, 40, 40, (10, 10, 10, 255))
    _add_synthetic_layer(project, project_dir, "caption", 5, 5, 10, 10, (255, 255, 255, 255))
    project.save(project_dir)

    def fake_segment_remote(image, text_prompt, endpoint):
        assert text_prompt == "letters"  # module-level DETECT_TEXT_PROMPT (empirical, M6-UX1)
        mask = np.zeros((image.height, image.width), dtype=np.uint8)
        mask[5:15, 5:15] = 255  # exactly the "caption" layer's canvas footprint
        return [Image.fromarray(mask, mode="L")]

    monkeypatch.setattr(app_module, "_segment_remote", fake_segment_remote)

    resp = client.post(f"/api/projects/{a['id']}/detect-text", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mask_count"] == 1

    by_name = {l["name"]: l for l in body["layers"]}
    assert by_name["caption"]["is_text"] is True
    assert by_name["caption"]["text_score"] == pytest.approx(1.0)
    assert by_name["bg"]["is_text"] is False
    assert by_name["bg"]["text_score"] < 0.35

    # One mutating call -> exactly one undo snapshot (undo_count itself stays
    # 0 for a single snapshot -- History.undo_count is len(stack)-1, see
    # test_transform_snapshots_for_undo in test_api_m2.py for the same
    # two-mutations-then-undo_count-1 pattern; check the raw stack instead).
    hist_data = json.loads((project_dir / "history.json").read_text(encoding="utf-8"))
    assert len(hist_data["undo_stack"]) == 1

    reloaded = LayerProject.load(project_dir)
    reloaded_by_name = {l.name: l for l in reloaded.layers}
    assert reloaded_by_name["caption"].is_text is True
    assert reloaded_by_name["bg"].is_text is False


def test_detect_text_zero_masks_all_false(api, monkeypatch):
    client, projects_dir = api
    import grafik.api.app as app_module

    a = _create_project(client, "detect-empty", width=20, height=20)
    project_dir = _dir_by_id(projects_dir, a["id"])
    project = LayerProject.load(project_dir)
    _add_synthetic_layer(project, project_dir, "only", 0, 0, 20, 20, (1, 2, 3, 255))
    project.save(project_dir)

    monkeypatch.setattr(app_module, "_segment_remote", lambda image, text_prompt, endpoint: [])

    resp = client.post(f"/api/projects/{a['id']}/detect-text", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mask_count"] == 0
    assert all(l["is_text"] is False for l in body["layers"])
    assert all(l["text_score"] == 0.0 for l in body["layers"])


def test_detect_text_resizes_mismatched_mask_size(api, monkeypatch):
    """Mask returned at a different resolution than the composite -- exercises
    the resize-to-composite-size path. A uniformly-white half-size mask avoids
    any LANCZOS edge-interpolation ambiguity in the expected result, while
    still proving the resize ran: without it, the union/alpha numpy arrays
    would have mismatched shapes and raise instead of returning 200."""
    client, projects_dir = api
    import grafik.api.app as app_module

    a = _create_project(client, "detect-resize", width=40, height=40)
    project_dir = _dir_by_id(projects_dir, a["id"])
    project = LayerProject.load(project_dir)
    _add_synthetic_layer(project, project_dir, "whole", 0, 0, 40, 40, (9, 9, 9, 255))
    project.save(project_dir)

    monkeypatch.setattr(
        app_module, "_segment_remote", lambda image, text_prompt, endpoint: [Image.new("L", (20, 20), 255)]
    )

    resp = client.post(f"/api/projects/{a['id']}/detect-text", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mask_count"] == 1
    assert body["layers"][0]["is_text"] is True
    assert body["layers"][0]["text_score"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# POST /api/projects/{id}/layers/{layer_id}/rewrite-text
# ---------------------------------------------------------------------------


def test_rewrite_text_prompt_with_original_and_metadata(api, monkeypatch):
    client, projects_dir = api

    a = _create_project(client, "rewrite", width=40, height=40)
    project_dir = _dir_by_id(projects_dir, a["id"])
    project = LayerProject.load(project_dir)
    layer = _add_synthetic_layer(project, project_dir, "caption", 0, 0, 40, 40, (200, 200, 200, 255))
    project.save(project_dir)

    captured = {}

    def fake_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
        captured["prompt"] = prompt
        return Image.new("RGB", image.size, (1, 2, 3))

    monkeypatch.setattr(QwenInpaintProvider, "_run_remote", fake_run_remote)
    import grafik.api.app as app_module
    monkeypatch.setattr(app_module, "_segment_remote", lambda *a, **k: [])  # re-cutout fallback: keep band alpha

    resp = client.post(
        f"/api/projects/{a['id']}/layers/{layer.id}/rewrite-text",
        json={"new_text": "Novy napis", "original_text": "Stary napis"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    expected_prompt = (
        'Replace the text "Stary napis" with "Novy napis". Keep the same font style, '
        "size, color and position. Do not change anything else."
    )
    assert body["prompt"] == expected_prompt
    assert captured["prompt"] == expected_prompt
    assert body["provider"] == "qwen-inpaint"
    assert body["elapsed_s"] >= 0
    assert body["layer"]["is_text"] is True
    assert body["layer"]["text_original"] == "Stary napis"
    assert body["layer"]["text_current"] == "Novy napis"

    reloaded = LayerProject.load(project_dir)
    rl = reloaded.get_layer(layer.id)
    assert rl.is_text is True
    assert rl.text_original == "Stary napis"
    assert rl.text_current == "Novy napis"

    # Second call without original_text -- falls back to text_current from the
    # first call; text_original is preserved (only overwritten when a
    # non-empty original_text is sent).
    resp2 = client.post(
        f"/api/projects/{a['id']}/layers/{layer.id}/rewrite-text",
        json={"new_text": "Jeste jinak"},
    )
    assert resp2.status_code == 200, resp2.text
    expected_prompt2 = (
        'Replace the text "Novy napis" with "Jeste jinak". Keep the same font style, '
        "size, color and position. Do not change anything else."
    )
    assert captured["prompt"] == expected_prompt2
    body2 = resp2.json()
    assert body2["layer"]["text_original"] == "Stary napis"  # unchanged
    assert body2["layer"]["text_current"] == "Jeste jinak"


def test_rewrite_text_prompt_without_any_original(api, monkeypatch):
    client, projects_dir = api

    a = _create_project(client, "rewrite-fresh", width=32, height=24)
    project_dir = _dir_by_id(projects_dir, a["id"])
    project = LayerProject.load(project_dir)
    layer = _add_synthetic_layer(project, project_dir, "fresh", 0, 0, 32, 24, (50, 60, 70, 255))
    project.save(project_dir)

    def fake_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
        return Image.new("RGB", image.size, (4, 5, 6))

    monkeypatch.setattr(QwenInpaintProvider, "_run_remote", fake_run_remote)
    import grafik.api.app as app_module
    monkeypatch.setattr(app_module, "_segment_remote", lambda *a, **k: [])  # re-cutout fallback: keep band alpha

    resp = client.post(
        f"/api/projects/{a['id']}/layers/{layer.id}/rewrite-text",
        json={"new_text": "Jen novy"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    expected_prompt = (
        'Replace the text with "Jen novy". Keep the same font style, size, '
        "color and position. Do not change anything else."
    )
    assert body["prompt"] == expected_prompt
    assert body["layer"]["text_original"] is None  # never sent -> stays unset
    assert body["layer"]["text_current"] == "Jen novy"
    assert body["layer"]["is_text"] is True


def test_rewrite_text_empty_400_unknown_layer_404(api):
    client, projects_dir = api
    a = _create_project(client, "rewrite-errs")
    project_dir = _dir_by_id(projects_dir, a["id"])
    project = LayerProject.load(project_dir)
    layer = _add_synthetic_layer(project, project_dir, "x", 0, 0, 32, 24, (1, 1, 1, 255))
    project.save(project_dir)

    resp = client.post(
        f"/api/projects/{a['id']}/layers/{layer.id}/rewrite-text", json={"new_text": "   "}
    )
    assert resp.status_code == 400

    resp2 = client.post(
        f"/api/projects/{a['id']}/layers/does-not-exist/rewrite-text", json={"new_text": "x"}
    )
    assert resp2.status_code == 404


def test_rewrite_text_changes_layer_pixels(api, monkeypatch):
    client, projects_dir = api

    a = _create_project(client, "rewrite-px", width=32, height=24)
    project_dir = _dir_by_id(projects_dir, a["id"])
    project = LayerProject.load(project_dir)
    layer = _add_synthetic_layer(project, project_dir, "txt", 0, 0, 32, 24, (7, 7, 7, 255))
    project.save(project_dir)

    before = client.get(f"/api/projects/{a['id']}/layers/{layer.id}/png").content

    def fake_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
        return Image.new("RGB", image.size, (250, 10, 10))

    monkeypatch.setattr(QwenInpaintProvider, "_run_remote", fake_run_remote)
    import grafik.api.app as app_module
    monkeypatch.setattr(app_module, "_segment_remote", lambda *a, **k: [])  # re-cutout fallback: keep band alpha

    resp = client.post(
        f"/api/projects/{a['id']}/layers/{layer.id}/rewrite-text",
        json={"new_text": "Red now"},
    )
    assert resp.status_code == 200, resp.text

    after = client.get(f"/api/projects/{a['id']}/layers/{layer.id}/png").content
    assert after != before
    after_img = Image.open(BytesIO(after)).convert("RGBA")
    assert after_img.getpixel((5, 5))[:3] == (250, 10, 10)


def test_rewrite_text_uses_band_mask_and_merges(api, monkeypatch):
    """The rewrite mask must be the glyph bbox grown by ~40 % of the line
    height (a band), NOT the glyphs themselves -- confining the model to the
    old strokes cannot fit differently-shaped replacement glyphs (E2E
    2026-08-15: broken overlapping letters). Merge path: outside the band the
    layer stays bit-identical (here: transparent)."""
    client, projects_dir = api

    a = _create_project(client, "rewrite-band", width=64, height=48)
    project_dir = _dir_by_id(projects_dir, a["id"])
    project = LayerProject.load(project_dir)
    glyphs = Image.new("RGBA", (64, 48), (0, 0, 0, 0))
    glyphs.paste((7, 7, 7, 255), (20, 18, 30, 24))  # 10x6 "glyph" blob
    layer = Layer(name="txt")
    layer.save_image(glyphs, project_dir)
    project.add_layer(layer)
    project.save(project_dir)

    captured = {}

    def fake_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
        captured["mask"] = mask
        return Image.new("RGB", image.size, (250, 10, 10))

    monkeypatch.setattr(QwenInpaintProvider, "_run_remote", fake_run_remote)
    import grafik.api.app as app_module
    monkeypatch.setattr(app_module, "_segment_remote", lambda *a, **k: [])  # re-cutout fallback: keep band alpha

    resp = client.post(
        f"/api/projects/{a['id']}/layers/{layer.id}/rewrite-text",
        json={"new_text": "New", "feather_px": 0, "dilate_px": 0},
    )
    assert resp.status_code == 200, resp.text

    # bbox (20,18)-(29,23), line height 6 -> margin max(12, 2.4) = 12 -> band (8,6)-(41,35).
    mask = captured["mask"]
    assert mask.getpixel((22, 20)) == 255  # inside the old glyphs
    assert mask.getpixel((10, 8)) == 255  # inside the band, OUTSIDE the old glyphs
    assert mask.getpixel((2, 2)) == 0  # outside the band

    after = Image.open(
        BytesIO(client.get(f"/api/projects/{a['id']}/layers/{layer.id}/png").content)
    ).convert("RGBA")
    assert after.getpixel((2, 2))[3] == 0  # merge: untouched outside the band
    assert after.getpixel((10, 8)) == (250, 10, 10, 255)  # band area adopted the edit
    assert after.getpixel((22, 20))[:3] == (250, 10, 10)


def test_rewrite_text_sam_recutout_shrinks_alpha_to_glyphs(api, monkeypatch):
    """After the band edit, one SAM "letters" call shrinks the layer's alpha
    back to the new glyphs (clean cutout) -- overlapping bands of nearby text
    layers must not bake copies of each other into their pixels (E2E
    2026-08-15: the title layer's band carried the old subtitle)."""
    client, projects_dir = api
    import grafik.api.app as app_module

    a = _create_project(client, "rewrite-cut", width=64, height=48)
    project_dir = _dir_by_id(projects_dir, a["id"])
    project = LayerProject.load(project_dir)
    glyphs_img = Image.new("RGBA", (64, 48), (0, 0, 0, 0))
    glyphs_img.paste((7, 7, 7, 255), (20, 18, 30, 24))
    layer = Layer(name="txt")
    layer.save_image(glyphs_img, project_dir)
    project.add_layer(layer)
    project.save(project_dir)

    def fake_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
        return Image.new("RGB", image.size, (250, 10, 10))

    monkeypatch.setattr(QwenInpaintProvider, "_run_remote", fake_run_remote)

    def fake_segment_remote(image, text_prompt, endpoint):
        assert text_prompt == "letters"
        # "New glyphs": a 6x4 blob at (4, 6) inside the band crop.
        mask = np.zeros((image.height, image.width), dtype=np.uint8)
        mask[6:10, 4:10] = 255
        return [Image.fromarray(mask, mode="L")]

    monkeypatch.setattr(app_module, "_segment_remote", fake_segment_remote)

    resp = client.post(
        f"/api/projects/{a['id']}/layers/{layer.id}/rewrite-text",
        json={"new_text": "New", "feather_px": 0, "dilate_px": 0},
    )
    assert resp.status_code == 200, resp.text

    after = Image.open(
        BytesIO(client.get(f"/api/projects/{a['id']}/layers/{layer.id}/png").content)
    ).convert("RGBA")
    # band (8,6)-(41,35); glyph blob crop-local (4..9, 6..9) -> layer coords (12..17, 12..15),
    # grown 2 px by MaxFilter(5); far band corner must be re-cut away to transparent.
    assert after.getpixel((14, 13))[3] > 200
    assert after.getpixel((35, 30))[3] == 0  # inside band, outside new glyphs
    assert after.getpixel((2, 2))[3] == 0  # outside band, untouched
