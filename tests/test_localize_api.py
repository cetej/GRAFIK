"""Počeštění infografiky přes Engine (/api/v2/localize): úloha `localize` ve frontě, 402 bez souhlasu,
cena z usage do ledgeru, opakovaná sazba z dřívějšího čtení zdarma. Claude je zamockovaný (`ask`)."""
from __future__ import annotations

import base64
import json
import time
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from tests.test_engine_v2 import FakeSd, free_port  # noqa: F401
from engine import sdserver
from engine.app import create_app
from engine.backends import FluxLocal
from engine.config import Settings
from ngm_shared import claude


def infographic_b64() -> str:
    img = Image.new("RGB", (400, 160), (235, 240, 245))
    ImageDraw.Draw(img).text((40, 50), "Water cycle", font=ImageFont.truetype("C:/Windows/Fonts/bahnschrift.ttf", 40),
                             fill=(20, 20, 20))
    buf = BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


READ = {"kind": "map", "elements": [{"id": 1, "en": "Water cycle", "cs": "Koloběh vody", "box": [40, 55, 250, 92],
                                     "color": "#141414", "font": "sans"}]}


class FakeClaude:
    def __init__(self):
        self.calls, self.fail = [], None

    def __call__(self, content, system, **kw):
        self.calls.append(kw)
        if self.fail:
            raise self.fail
        return claude.Answer(json.dumps(READ, ensure_ascii=False), "claude-opus-5-5", 1800, 4200, 0.0912, "end_turn")


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(sdserver, "free_vram_mib", lambda: None)
    s = Settings(data_dir=tmp_path, flux_dir=tmp_path, sd_port=free_port(), gpu_lock_path=tmp_path / "gpu.lock")
    sd = FakeSd(s)
    fake = FakeClaude()
    app = create_app(s, backends={"flux-local": FluxLocal(s, sd)}, server=sd, backends3d={}, ask=fake)
    with TestClient(app) as c:
        c.claude, c.settings = fake, s
        yield c
    sd.stop("test teardown")


def wait(api, job_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = api.get(f"/api/v2/jobs/{job_id}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.1)
    raise AssertionError(f"úloha {job_id} nedoběhla")


def costs(api) -> list[dict]:
    p = api.settings.costs_path
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def test_paid_read_needs_consent_and_nothing_is_queued(api):
    r = api.post("/api/v2/localize", json={"b64": infographic_b64(), "caller": "ng-robot"})
    assert r.status_code == 402 and r.json()["estimate_usd"] == 0.20
    assert api.get("/api/v2/localize/jobs").json() == [] and api.claude.calls == []


def test_localize_job_reads_once_logs_usage_cost_and_serves_files(api):
    r = api.post("/api/v2/localize", json={"b64": infographic_b64(), "caller": "test-t2", "confirm_cost": True})
    assert r.status_code == 202, r.text
    job = wait(api, r.json()["job_id"])
    assert job["status"] == "done", job["error"]
    assert job["kind"] == "localize" and job["caller"] == "test-t2" and len(api.claude.calls) == 1
    res = job["result"]
    assert res["cost_usd"] == 0.0912 and res["image_kind"] == "map" and "Koloběh vody" in res["text"]
    assert res["warnings"][0]["what"] == "Obrázek je mapa."            # poradně, úloha doběhla
    png = api.get(job["images"][0])
    assert png.status_code == 200 and Image.open(BytesIO(png.content)).size == (400, 160)
    svg = api.get(f"/api/v2/localize/{job['job_id']}/image-0.svg")
    assert svg.status_code == 200 and "Koloběh vody" in svg.text
    assert api.get(f"/api/v2/localize/{job['job_id']}/../jobs.sqlite").status_code == 404
    prov = api.get(f"/api/v2/jobs/{job['job_id']}/images/0/provenance").json()
    assert prov["texts_from"] == "claude:claude-opus-5-5" and prov["reviewed_by"] is None
    row = costs(api)[-1]
    assert row["job_id"] == job["job_id"] and row["usd"] == 0.0912 and row["usage"]["out"] == 4200
    # /api/v2/jobs zůstává jen pro obrázky (NG-ROBOT)
    assert all(j["kind"] == "image" for j in api.get("/api/v2/jobs").json())


def test_retypeset_from_an_earlier_reading_is_free(api):
    first = wait(api, api.post("/api/v2/localize", json={"b64": infographic_b64(), "confirm_cost": True})
                 .json()["job_id"])
    again = api.post("/api/v2/localize", json={"b64": infographic_b64(), "texts_from": first["job_id"]})
    assert again.status_code == 202 and again.json()["estimate_usd"] == 0.0
    job = wait(api, again.json()["job_id"])
    assert job["status"] == "done" and job["result"]["cost_usd"] == 0.0 and len(api.claude.calls) == 1
    edited = {**READ, "elements": [{**READ["elements"][0], "cs": "Koloběh vody na Zemi"}]}
    third = wait(api, api.post("/api/v2/localize", json={"image": f"{job['job_id']}/0", "texts": edited})
                 .json()["job_id"])
    assert "Koloběh vody na Zemi" in third["result"]["text"] and len(api.claude.calls) == 1
    assert len(costs(api)) == 1


def test_bad_requests(api):
    assert api.post("/api/v2/localize", json={}).status_code == 400
    assert api.post("/api/v2/localize", json={"b64": "bm90IGFuIGltYWdl"}).status_code == 400
    assert api.post("/api/v2/localize", json={"image": "20990101-000000-abcdef/0"}).status_code == 404
    assert api.post("/api/v2/localize", json={"ref_id": "../x"}).status_code == 400
    bad = {"elements": [{"en": "x", "cs": "x", "box": [9, 0, 1, 5]}]}
    assert api.post("/api/v2/localize", json={"b64": infographic_b64(), "texts": bad}).status_code == 400
    assert api.post("/api/v2/localize", json={"b64": infographic_b64(), "texts_from": "nic"}).status_code == 404


def test_failed_read_still_logs_what_was_billed(api):
    api.claude.fail = claude.ClaudeError("čtení textu: odpověď nedokončena (stop=max_tokens)",
                                         {"model": "claude-opus-5-5", "in": 1800, "out": 32000, "usd": 0.6472})
    job = wait(api, api.post("/api/v2/localize", json={"b64": infographic_b64(), "confirm_cost": True})
               .json()["job_id"])
    assert job["status"] == "failed" and "nedokončena" in job["error"]
    row = costs(api)[-1]
    assert row["status"] == "failed" and row["usd"] == 0.6472
