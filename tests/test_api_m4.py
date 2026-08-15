"""Tests for M4: soft-delete/trash, cost ledger, NB Pro image generation,
FLUX Fill provider, and recursive layer decomposition. Fully offline —
network seams are monkeypatched (fal_client.subscribe, provider._run_remote,
FalClient.decompose, httpx.post), projects are synthetic (built through the
API itself), same idioms as test_api_m25.py.
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
from grafik.core.layer import Layer
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
# Soft-delete / trash
# ---------------------------------------------------------------------------


def test_delete_moves_to_trash_and_restore_roundtrip(api):
    client, projects_dir, logs_dir = api
    a = _create_project(client, "kos-test")
    layer = _add_layer(client, a["id"])
    src_dir = _dir_by_id(projects_dir, a["id"])

    resp = client.delete(f"/api/projects/{a['id']}")
    assert resp.status_code == 200, resp.text
    entry = resp.json()["trash_entry"]
    assert entry.endswith("kos-test.grafik")

    # Gone from projects, present (with metadata) in trash.
    assert not src_dir.exists()
    assert a["id"] not in {i["id"] for i in client.get("/api/projects").json()}
    trash_dir = projects_dir / ".trash" / entry
    assert (trash_dir / "project.json").exists()
    items = client.get("/api/trash").json()
    assert len(items) == 1
    assert items[0]["entry"] == entry
    assert items[0]["id"] == a["id"]
    assert items[0]["name"] == "kos-test"
    assert items[0]["layer_count"] == 1
    assert items[0]["deleted_at"]

    ops = _destructive_ops(logs_dir)
    assert ops and ops[-1]["op"] == "project-delete" and ops[-1]["trash_entry"] == entry

    # Restore: same id, original directory name, layer PNG intact.
    resp = client.post(f"/api/trash/{entry}/restore")
    assert resp.status_code == 200, resp.text
    restored = resp.json()
    assert restored["id"] == a["id"]
    assert restored["layer_count"] == 1
    back_dir = _dir_by_id(projects_dir, a["id"])
    assert back_dir.name == "kos-test.grafik"
    proj = LayerProject.load(back_dir)
    assert (back_dir / proj.get_layer(layer["id"]).png_path).exists()
    assert client.get("/api/trash").json() == []
    assert _destructive_ops(logs_dir)[-1]["op"] == "trash-restore"


def test_restore_into_name_collision_gets_numbered_dir(api):
    client, projects_dir, _ = api
    a = _create_project(client, "dup")
    entry = client.delete(f"/api/projects/{a['id']}").json()["trash_entry"]
    b = _create_project(client, "dup")  # re-claims dup.grafik
    assert _dir_by_id(projects_dir, b["id"]).name == "dup.grafik"

    resp = client.post(f"/api/trash/{entry}/restore")
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == a["id"]
    assert _dir_by_id(projects_dir, a["id"]).name == "dup-2.grafik"
    ids = {i["id"] for i in client.get("/api/projects").json()}
    assert {a["id"], b["id"]} <= ids


def test_restore_id_collision_assigns_fresh_id(api):
    """Openart-incident defense: restoring an entry whose id is already live
    must not shadow the live project — the restored copy gets a new id."""
    import shutil

    client, projects_dir, _ = api
    a = _create_project(client, "idclash")
    entry = client.delete(f"/api/projects/{a['id']}").json()["trash_entry"]
    # Simulate an outside copy that already brought the id back to life.
    shutil.copytree(projects_dir / ".trash" / entry, projects_dir / "idclash.grafik")

    resp = client.post(f"/api/trash/{entry}/restore")
    assert resp.status_code == 200, resp.text
    restored = resp.json()
    assert restored["id"] != a["id"]
    ids = [i["id"] for i in client.get("/api/projects").json()]
    assert a["id"] in ids and restored["id"] in ids


def test_empty_trash_purges_everything(api):
    client, projects_dir, logs_dir = api
    for name in ("t1", "t2"):
        p = _create_project(client, name)
        client.delete(f"/api/projects/{p['id']}")
    assert len(client.get("/api/trash").json()) == 2

    resp = client.delete("/api/trash")
    assert resp.status_code == 200, resp.text
    assert resp.json()["purged"] == 2
    assert client.get("/api/trash").json() == []
    assert not any((projects_dir / ".trash").iterdir())
    assert _destructive_ops(logs_dir)[-1]["op"] == "trash-empty"


def test_trash_autopurge_entries_older_than_30_days(api):
    client, projects_dir, logs_dir = api
    trash = projects_dir / ".trash"
    trash.mkdir()
    old = trash / "20250101-000000-old.grafik"
    old.mkdir()
    (old / "project.json").write_text(
        json.dumps({"id": "old1", "name": "old", "layers": []}), encoding="utf-8"
    )

    assert client.get("/api/trash").json() == []
    assert not old.exists()
    ops = _destructive_ops(logs_dir)
    assert ops and ops[-1]["op"] == "trash-autopurge" and ops[-1]["entry"] == old.name


def test_trash_restore_unknown_entry_404(api):
    client, _, _ = api
    assert client.post("/api/trash/does-not-exist/restore").status_code == 404


# ---------------------------------------------------------------------------
# Cost ledger (grafik.core.costs) + routes
# ---------------------------------------------------------------------------


def test_estimate_usd_uses_registry_rates():
    assert costs.estimate_usd("fal-ai/flux-pro/v1/fill", mp=2.0) == pytest.approx(0.10)
    assert costs.estimate_usd("fal-ai/qwen-image-edit/inpaint", mp=1.0) == pytest.approx(0.03)
    assert costs.estimate_usd("fal-ai/qwen-image-layered") == pytest.approx(0.05)
    assert costs.estimate_usd("fal-ai/sam-3/image") == pytest.approx(0.005)
    assert costs.estimate_usd("google/nano-banana-pro-preview") == pytest.approx(0.134)
    assert costs.estimate_usd("wan/v2.6/image-to-video", seconds=5.0) == pytest.approx(0.50)
    # Non-numeric duration (seedance "auto") and unknown endpoints stay honest.
    assert costs.estimate_usd("bytedance/seedance-2.5/image-to-video", seconds=None) is None
    assert costs.estimate_usd("no-such-endpoint", mp=1.0) is None


def test_record_paid_call_writes_ledger_and_session(tmp_path):
    costs.reset_session()
    entry = costs.record_paid_call(
        "fal-ai/sam-3/image", "segment", note="unit", project_dir=tmp_path
    )
    assert entry["est_usd"] == pytest.approx(0.005)
    ledger = costs.read_ledger(tmp_path)
    assert len(ledger) == 1 and ledger[0]["endpoint"] == "fal-ai/sam-3/image"
    assert costs.total_usd(ledger) == pytest.approx(0.005)
    assert costs.session_entries()[-1]["note"] == "unit"


def test_tracked_subscribe_records_via_context(tmp_path, monkeypatch):
    from grafik.fal import client as fal_module

    costs.reset_session()
    monkeypatch.setattr(
        fal_module.fal_client, "subscribe", lambda endpoint, arguments, with_logs=False: {"ok": True}
    )
    with costs.cost_context(tmp_path):
        result = fal_module.tracked_subscribe(
            "fal-ai/qwen-image-edit/inpaint", {"prompt": "x"}, kind="image_edit", mp=2.0
        )
    assert result == {"ok": True}
    ledger = costs.read_ledger(tmp_path)
    assert len(ledger) == 1
    assert ledger[0]["mp"] == 2.0
    assert ledger[0]["est_usd"] == pytest.approx(0.06)


def test_segment_route_attributes_cost_to_project(api, monkeypatch):
    """The contextvar path end-to-end: _load_project binds the project dir,
    the SAM call deep inside _segment_remote lands in its costs.jsonl."""
    client, projects_dir, _ = api
    a = _create_project(client)
    _add_layer(client, a["id"])

    monkeypatch.setattr(
        "fal_client.subscribe",
        lambda endpoint, arguments, with_logs=False: {"masks": [{"url": "https://fake/m.png"}]},
    )
    monkeypatch.setattr("grafik.fal.upload.upload_image", lambda img: "https://fake/i.png")
    monkeypatch.setattr("grafik.fal.upload.download_url", lambda url: Image.new("RGBA", (64, 48)))

    resp = client.post(f"/api/projects/{a['id']}/segment", json={"points": [{"x": 3, "y": 4}]})
    assert resp.status_code == 200, resp.text

    body = client.get(f"/api/projects/{a['id']}/costs").json()
    assert body["count"] == 1
    assert body["entries"][0]["endpoint"] == "fal-ai/sam-3/image"
    assert body["entries"][0]["kind"] == "segment"
    assert body["total_usd"] == pytest.approx(0.005)

    session = client.get("/api/costs/session").json()
    assert session["count"] >= 1
    assert any(e["endpoint"] == "fal-ai/sam-3/image" for e in session["entries"])


def test_attach_cost_entry_to_project(api):
    client, _, _ = api
    a = _create_project(client)
    entry = {
        "ts": "2026-08-15T00:00:00+00:00",
        "endpoint": "google/nano-banana-pro-preview",
        "kind": "image_gen",
        "calls": 1,
        "est_usd": 0.134,
        "note": "generate 1024x1024",
    }
    resp = client.post(f"/api/projects/{a['id']}/costs", json=entry)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_usd"] == pytest.approx(0.134)
    assert client.get(f"/api/projects/{a['id']}/costs").json()["count"] == 1


def test_duplicate_project_starts_with_clean_ledger(api):
    client, projects_dir, _ = api
    a = _create_project(client, "ledgersrc")
    src_dir = _dir_by_id(projects_dir, a["id"])
    costs.record_paid_call("fal-ai/sam-3/image", "segment", project_dir=src_dir)

    dup = client.post(f"/api/projects/{a['id']}/duplicate").json()
    dup_dir = _dir_by_id(projects_dir, dup["id"])
    assert not (dup_dir / "costs.jsonl").exists()
    assert (src_dir / "costs.jsonl").exists()


# ---------------------------------------------------------------------------
# NB Pro (image_gen) — /api/generate-image
# ---------------------------------------------------------------------------


def test_generate_image_returns_png_and_records_cost(api, monkeypatch):
    from grafik.providers.nbpro import NanoBananaProProvider

    client, _, _ = api
    fake_png = _png_bytes(size=(40, 30), color=(0, 128, 255, 255))
    seen = {}

    def fake_run_remote(self, key, prompt, aspect_ratio, image_size):
        seen.update(prompt=prompt, aspect_ratio=aspect_ratio, image_size=image_size)
        return fake_png

    monkeypatch.setattr(NanoBananaProProvider, "_run_remote", fake_run_remote)
    monkeypatch.setattr("grafik.providers.nbpro.resolve_api_key", lambda: "test-key")

    resp = client.post("/api/generate-image", json={"prompt": "kočka na plotě", "aspect_ratio": "4:3"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert seen == {"prompt": "kočka na plotě", "aspect_ratio": "4:3", "image_size": "2K"}
    img = Image.open(BytesIO(base64.b64decode(body["image_b64"])))
    assert img.size == (40, 30)
    assert body["width"] == 40 and body["height"] == 30
    assert body["cost"]["endpoint"] == "google/nano-banana-pro-preview"
    assert body["cost"]["est_usd"] == pytest.approx(0.134)
    assert any(
        e["endpoint"] == "google/nano-banana-pro-preview"
        for e in client.get("/api/costs/session").json()["entries"]
    )


def test_generate_image_missing_key_readable_503(api, monkeypatch):
    monkeypatch.setattr("grafik.providers.nbpro.resolve_api_key", lambda: None)
    client, _, _ = api
    resp = client.post("/api/generate-image", json={"prompt": "cokoliv"})
    assert resp.status_code == 503
    assert "GEMINI_API_KEY" in resp.json()["detail"]


def test_generate_image_validation_errors(api):
    client, _, _ = api
    assert client.post("/api/generate-image", json={"prompt": "x", "aspect_ratio": "7:5"}).status_code == 400
    assert client.post("/api/generate-image", json={"prompt": "   "}).status_code == 400
    assert client.post("/api/generate-image", json={"prompt": "x", "provider": "nope"}).status_code == 404
    assert client.post("/api/generate-image", json={"prompt": "x", "provider": "sam-3"}).status_code == 400


def test_nbpro_parses_inline_data_and_errors_readably(monkeypatch):
    from grafik.providers import nbpro

    payload_b64 = base64.b64encode(b"PNGBYTES").decode("ascii")

    class FakeResp:
        def __init__(self, body):
            self._body = body

        def raise_for_status(self):
            return None

        def json(self):
            return self._body

    good = {
        "candidates": [
            {"content": {"parts": [{"text": "here"}, {"inlineData": {"data": payload_b64}}]}}
        ]
    }
    monkeypatch.setattr(nbpro.httpx, "post", lambda *a, **kw: FakeResp(good))
    provider = nbpro.NanoBananaProProvider()
    assert provider._run_remote("k", "p", "1:1", "2K") == b"PNGBYTES"

    bad = {"candidates": [{"finishReason": "PROHIBITED_CONTENT", "content": {"parts": [{"text": "nope"}]}}]}
    monkeypatch.setattr(nbpro.httpx, "post", lambda *a, **kw: FakeResp(bad))
    with pytest.raises(RuntimeError, match="PROHIBITED_CONTENT"):
        provider._run_remote("k", "p", "1:1", "2K")


def test_nbpro_resolve_key_prefers_env(monkeypatch):
    from grafik.providers import nbpro

    for name in nbpro.KEY_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GOOGLE_GEMINI_API_KEY", "from-env")
    assert nbpro.resolve_api_key() == "from-env"


# ---------------------------------------------------------------------------
# FLUX Fill provider
# ---------------------------------------------------------------------------


def _hard_mask(size=(64, 64), box=(16, 16, 48, 48)) -> Image.Image:
    import numpy as np

    arr = np.zeros(size[::-1], dtype=np.uint8)
    x0, y0, x1, y1 = box
    arr[y0:y1, x0:x1] = 255
    return Image.fromarray(arr, mode="L")


def test_flux_fill_edit_paste_back(monkeypatch):
    import numpy as np

    from grafik.providers.flux_fill import FluxFillProvider

    provider = FluxFillProvider()
    size = (64, 64)
    image = Image.new("RGB", size, (10, 20, 30))
    mask = _hard_mask(size)
    fake_result = Image.new("RGB", size, (200, 150, 100))

    monkeypatch.setattr(
        FluxFillProvider, "_run_remote", lambda self, image, mask, prompt, tol: fake_result
    )
    out = provider.edit(image, mask, "make it blue")
    out_arr = np.array(out)
    # far outside the dilated+feathered mask -> input unchanged
    assert np.array_equal(out_arr[0:4, 0:4], np.array(image)[0:4, 0:4])
    # deep inside -> remote result
    assert np.array_equal(out_arr[28:36, 28:36], np.array(fake_result)[28:36, 28:36])

    # resize-back guard: wrong-size remote result comes back input-sized
    monkeypatch.setattr(
        FluxFillProvider,
        "_run_remote",
        lambda self, image, mask, prompt, tol: Image.new("RGB", (32, 32), (250, 250, 250)),
    )
    assert provider.edit(image, mask, "x").size == size


def test_flux_fill_run_remote_payload_and_cost(monkeypatch):
    from grafik.fal import client as fal_module
    from grafik.providers.flux_fill import FluxFillProvider

    costs.reset_session()
    captured = {}

    def fake_subscribe(endpoint, arguments, with_logs=False):
        captured["endpoint"] = endpoint
        captured["arguments"] = arguments
        return {"images": [{"url": "https://fake/out.png"}]}

    monkeypatch.setattr(fal_module.fal_client, "subscribe", fake_subscribe)
    # flux_fill binds upload_image/download_url at import time -> patch its bindings.
    monkeypatch.setattr("grafik.providers.flux_fill.upload_image", lambda img: "https://fake/up.png")
    monkeypatch.setattr(
        "grafik.providers.flux_fill.download_url",
        lambda url: Image.new("RGBA", (64, 64), (1, 2, 3, 255)),
    )

    provider = FluxFillProvider()
    out = provider._run_remote(Image.new("RGB", (64, 64)), Image.new("L", (64, 64)), "p", "2")
    assert out.size == (64, 64)
    assert captured["endpoint"] == "fal-ai/flux-pro/v1/fill"
    # Raw-OpenAPI-verified shape: required fields + png override of the jpeg default.
    assert captured["arguments"] == {
        "prompt": "p",
        "image_url": "https://fake/up.png",
        "mask_url": "https://fake/up.png",
        "output_format": "png",
        "safety_tolerance": "2",
    }
    session = costs.session_entries()
    assert session and session[-1]["endpoint"] == "fal-ai/flux-pro/v1/fill"
    # Ledger stores mp rounded to 4 decimals (est_usd is computed pre-rounding).
    assert session[-1]["mp"] == pytest.approx(round(64 * 64 / 1e6, 4))


def test_ai_edit_route_accepts_flux_fill_provider(api, monkeypatch):
    from grafik.providers.flux_fill import FluxFillProvider

    client, _, _ = api
    a = _create_project(client)
    layer = _add_layer(client, a["id"])
    monkeypatch.setattr(
        FluxFillProvider,
        "_run_remote",
        lambda self, image, mask, prompt, tol: Image.new("RGB", image.size, (9, 9, 9)),
    )
    resp = client.post(
        f"/api/projects/{a['id']}/layers/{layer['id']}/ai-edit",
        json={"prompt": "zmodrej", "provider": "flux-fill"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["provider"] == "flux-fill"


# ---------------------------------------------------------------------------
# Recursive layer decomposition
# ---------------------------------------------------------------------------


def _mock_layer_decompose(monkeypatch, sub_count=2, native=(16, 12)):
    """FalClient.decompose seam for the layer-decompose route: returns
    `sub_count` full-frame synthetic Layers with PNGs saved to project_dir,
    width/height at fal's native resolution (deliberately NOT the layer's)."""
    from grafik.fal.client import FalClient

    def fake_decompose(self, image_url, num_layers, *, project=None, project_dir=None):
        subs = []
        for i in range(sub_count):
            l = Layer(name=f"Layer {i}", z_order=i, source="fal:i2l", tags=["decomposed"])
            l.save_image(Image.new("RGBA", native, (40 * (i + 1), 0, 0, 255)), project_dir)
            subs.append(l)
        return subs

    monkeypatch.setattr(FalClient, "decompose", fake_decompose)
    monkeypatch.setattr("grafik.fal.upload.upload_image", lambda img: "https://fake/layer.png")


def test_decompose_layer_replaces_with_sublayers_inheriting_geometry(api, monkeypatch):
    client, projects_dir, _ = api
    a = _create_project(client)
    bottom = _add_layer(client, a["id"], "bottom.png")
    target = _add_layer(client, a["id"], "target.png")
    top = _add_layer(client, a["id"], "top.png")
    # Give the target a non-trivial quad, rotation included.
    resp = client.post(
        f"/api/projects/{a['id']}/layers/{target['id']}/transform",
        json={"x": 5, "y": 7, "width": 40, "height": 30, "rotation": 15.0},
    )
    assert resp.status_code == 200, resp.text

    _mock_layer_decompose(monkeypatch)
    resp = client.post(
        f"/api/projects/{a['id']}/layers/{target['id']}/decompose", json={"num_layers": 2}
    )
    assert resp.status_code == 200, resp.text
    subs = resp.json()
    assert [s["name"] for s in subs] == ["target.png / 1", "target.png / 2"]
    for s in subs:
        assert (s["x"], s["y"], s["width"], s["height"]) == (5, 7, 40, 30)
        assert s["rotation"] == 15.0
        assert s["tags"] == ["decomposed", "sub"]

    # Original replaced in place: bottom, sub1, sub2, top with sequential z.
    layers = client.get(f"/api/projects/{a['id']}/layers").json()
    assert [l["id"] for l in layers] == [bottom["id"], subs[0]["id"], subs[1]["id"], top["id"]]
    assert [l["z_order"] for l in layers] == [0, 1, 2, 3]
    assert target["id"] not in {l["id"] for l in layers}

    # The original PNG stays on disk, so undo restores the layer fully.
    proj_dir = _dir_by_id(projects_dir, a["id"])
    assert (proj_dir / f"layers/{target['id']}.png").exists()
    assert client.post(f"/api/projects/{a['id']}/undo").status_code == 200
    after_undo = {l["id"] for l in client.get(f"/api/projects/{a['id']}/layers").json()}
    assert target["id"] in after_undo
    assert subs[0]["id"] not in after_undo


def test_decompose_layer_failure_maps_to_502(api, monkeypatch):
    from grafik.fal.client import FalClient

    client, _, _ = api
    a = _create_project(client)
    layer = _add_layer(client, a["id"])

    def boom(self, image_url, num_layers, *, project=None, project_dir=None):
        raise RuntimeError("fal down")

    monkeypatch.setattr(FalClient, "decompose", boom)
    monkeypatch.setattr("grafik.fal.upload.upload_image", lambda img: "https://fake/x.png")
    resp = client.post(f"/api/projects/{a['id']}/layers/{layer['id']}/decompose", json={})
    assert resp.status_code == 502
    assert "Dekompozice vrstvy selhala" in resp.json()["detail"]

    assert client.post(f"/api/projects/{a['id']}/layers/nope/decompose", json={}).status_code == 404
