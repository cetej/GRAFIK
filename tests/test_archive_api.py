"""Archiv přes Engine (GET /api/v2/archive): hledání v úlohách vlastní fronty, relativní adresy, náhledy."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from tests.test_engine_v2 import FakeSd, free_port  # noqa: F401
from engine import sdserver
from engine.app import create_app
from engine.backends import FluxLocal
from engine.config import Settings


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(sdserver, "free_vram_mib", lambda: None)
    s = Settings(data_dir=tmp_path, flux_dir=tmp_path, sd_port=free_port(), gpu_lock_path=tmp_path / "gpu.lock")
    sd = FakeSd(s)
    app = create_app(s, backends={"flux-local": FluxLocal(s, sd)}, server=sd, backends3d={})
    with TestClient(app) as c:
        store = app.state.store
        for caller, prompt in (("ng-robot", "Inkové, Machu Picchu za úsvitu"), ("studio", "Maják v noci, akvarel")):
            job_dir = tmp_path / "library" / "2026-10" / caller
            job_dir.mkdir(parents=True)
            Image.new("RGB", (512, 512), (10, 20, 30)).save(job_dir / "image-0.png")
            job_id = store.add_task("image", caller, "flux-local", {"prompt": prompt})
            store.next_queued()
            store.finish(job_id, result={"files": [str(job_dir / "image-0.png")], "prompt_sent": "x"})
        yield c
    sd.stop("test teardown")


def test_archive_search_returns_relative_urls_and_serves_the_thumbnail(api):
    r = api.get("/api/v2/archive", params={"q": "inkove machu"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1 and body["results"][0]["caller"] == "ng-robot"
    img = body["results"][0]["images"][0]
    assert img["thumb_path"].endswith("thumb-image-0-256.jpg")
    thumb = api.get(img["thumb_url"])
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"


def test_archive_filters_and_facets(api):
    assert api.get("/api/v2/archive", params={"caller": "studio"}).json()["count"] == 1
    assert api.get("/api/v2/archive", params={"kind": "localize"}).json()["count"] == 0
    assert api.get("/api/v2/archive", params={"since": "včera"}).status_code == 400
    f = api.get("/api/v2/archive/facets").json()
    assert f["total"] == 2 and f["callers"] == {"ng-robot": 1, "studio": 1}
