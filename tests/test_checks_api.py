"""Poradní kontroly přes Engine (POST /api/v2/checks): 402 bez souhlasu, obě kontroly naráz, cena z usage do
ledgeru, výsledek vedle obrázku v knihovně. Claude je zamockovaný (`ask`)."""
from __future__ import annotations

import base64
import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from tests.test_engine_v2 import FakeSd, free_port  # noqa: F401
from engine import sdserver
from engine.app import create_app
from engine.backends import FluxLocal
from engine.config import Settings
from ngm_shared import claude

BRIEF = {"verdikt": "vrátit", "vady": [{"co": "jen jedna hruška", "oprava": "dvě hrušky", "zavaznost": "vysoká"}]}
LOGIC = {"souhrn": "Kvádr nemá kam jít.", "ucel": "Zvedá se na zeď, která chybí.",
         "problemy": [{"co": "chybí lešení", "proc": "kvádr nemá cíl", "oprava": "přidat zeď", "zavaznost": "střední"}]}


class FakeClaude:
    def __init__(self):
        self.calls, self.fail = [], None

    def __call__(self, content, system, **kw):
        self.calls.append(kw["what"])
        if self.fail:
            raise self.fail
        payload, usd = (LOGIC, 0.0524) if kw["what"] == "kontrola logiky" else (BRIEF, 0.0047)
        return claude.Answer(json.dumps(payload, ensure_ascii=False), "claude-opus-5-5", 1186, 2385, usd, "end_turn")


def png_b64() -> str:
    buf = BytesIO()
    Image.new("RGB", (64, 48), (200, 180, 120)).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


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


def costs(api) -> list[dict]:
    p = api.settings.costs_path
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def test_checks_need_consent_with_the_estimate_for_both(api):
    r = api.post("/api/v2/checks", json={"b64": png_b64(), "brief": "Dvě hrušky.", "kinds": ["brief", "logic"]})
    assert r.status_code == 402 and r.json()["estimate_usd"] == 0.09 and api.claude.calls == []


def test_both_checks_are_advisory_and_logged_with_usage_cost(api):
    r = api.post("/api/v2/checks", json={"b64": png_b64(), "brief": "Dvě hrušky.", "kinds": ["brief", "logic"],
                                         "caller": "klapka", "confirm_cost": True})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["advisory"] and [x["kind"] for x in out["results"]] == ["brief", "logic"]
    assert out["results"][0]["verdict"] == "vrátit" and out["results"][1]["purpose"].startswith("Zvedá")
    assert out["cost_usd"] == 0.0571
    rows = costs(api)
    assert [(x["backend"], x["usd"], x["caller"]) for x in rows] == [("claude:check-brief", 0.0047, "klapka"),
                                                                     ("claude:check-logic", 0.0524, "klapka")]
    assert api.get("/api/v2/costs").json()["total_usd"] == 0.0571


def test_check_of_a_library_image_is_kept_next_to_it(api, tmp_path):
    job_dir = tmp_path / "library" / "2026-10" / "20261029-100000-abcdef"
    job_dir.mkdir(parents=True)
    Image.new("RGB", (32, 32)).save(job_dir / "image-0.png")
    store = api.app.state.store
    job_id = store.add_task("image-import", "test", "local", {"prompt": "hrušky"})
    store.next_queued()
    store.finish(job_id, result={"files": [str(job_dir / "image-0.png")]})
    r = api.post("/api/v2/checks", json={"image": f"{job_id}/0", "brief": "Dvě hrušky.", "phase": "image",
                                         "kinds": ["logic"], "confirm_cost": True})
    assert r.status_code == 200, r.text
    saved = [json.loads(x) for x in (job_dir / "image-0.checks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert saved[0]["image"] == f"{job_id}/0" and saved[0]["results"][0]["kind"] == "logic"


def test_bad_check_requests(api):
    ok = {"b64": png_b64(), "brief": "x", "confirm_cost": True}
    assert api.post("/api/v2/checks", json={**ok, "kinds": ["style"]}).status_code == 400
    assert api.post("/api/v2/checks", json={**ok, "brief": "  "}).status_code == 400
    assert api.post("/api/v2/checks", json={**ok, "phase": "video"}).status_code == 400
    assert api.post("/api/v2/checks", json={"brief": "x", "confirm_cost": True}).status_code == 400
    assert api.post("/api/v2/checks", json={**ok, "b64": None, "image": "20990101-000000-abcdef/0"}).status_code == 404
    assert api.claude.calls == []


def test_failed_check_is_a_502_and_still_logs_what_was_billed(api):
    api.claude.fail = claude.ClaudeError("kontrola proti zadání: odpověď nedokončena",
                                         {"model": "claude-opus-5-5", "in": 1000, "out": 4000, "usd": 0.084})
    r = api.post("/api/v2/checks", json={"b64": png_b64(), "brief": "x", "confirm_cost": True})
    assert r.status_code == 502 and "nedokončena" in r.json()["detail"]
    assert costs(api)[-1]["status"] == "failed" and costs(api)[-1]["usd"] == 0.084
