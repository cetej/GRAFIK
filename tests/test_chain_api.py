"""Řetězec infografika z tématu: jedna cena předem, doběhne k výběru bez kliknutí, zastaví se nad rozpočtem, přežije restart."""
import json
import time
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from engine import chain as ch
from engine import proposals as pp
from engine.app import create_app
from engine.backends import FluxLocal
from engine.jobs import load_costs
from engine.workflows import WorkflowStore
from ngm_shared import claude
from tests.test_engine_v2 import api, sd, settings  # noqa: F401  (fixtures)
from tests.test_research_api import fake_get

PANEL = {"titulek": "Řez", "co": "Co je uvnitř", "druh": "rez", "x": 0, "y": 0, "w": 100, "h": 60, "poradi": 1, "fakta": ["f1", "f999"], "predloha": "rez"}
REPLY = {"navrhy": [{"nazev": "Velký řez", "veta": "Čtenář pochopí stavbu.", "format": "2:3", "panely": [PANEL], "vzhled": "a cutaway"},
                    {"nazev": "Bez panelů", "panely": []},
                    {"nazev": "Čísla", "veta": "Rozměry.", "format": "neznámý", "panely": [{**PANEL, "x": 90, "w": 50, "fakta": ["f1"]}]}]}
LOGIC = {"souhrn": "Dává smysl.", "ucel": "Ukázat stavbu.", "problemy": [{"co": "Malé písmo", "proc": "x", "oprava": "y", "zavaznost": "nízká"}]}


class FakeAsk:
    """Na návrhy i kontrolu; pamatuje si volání, cena z konstruktoru."""

    def __init__(self, usd=0.05, reply=None):
        self.usd, self.reply, self.calls = usd, reply or REPLY, []

    def __call__(self, content, system, *, what, model, effort="low", max_tokens=16000):
        self.calls.append({"what": what, "model": model, "content": content})
        data = LOGIC if what == "kontrola logiky" else self.reply
        return claude.Answer(json.dumps(data, ensure_ascii=False), model, 1000, 500, self.usd, "end_turn")


def make(settings, sd, ask, start_worker=True):
    app = create_app(settings, backends={"flux-local": FluxLocal(settings, sd)}, server=sd, ask=ask, start_worker=start_worker)
    researcher = next(h.__self__ for k, h in app.state.worker.handlers.items() if k == "research")
    buf = BytesIO()
    Image.new("RGB", (2000, 1500), (90, 70, 60)).save(buf, "JPEG")
    researcher.get = fake_get
    researcher.fetch_image = lambda file: researcher.reflib.add(buf.getvalue(), origin="commons", title=file, author="Dehio", license="CC0", page_url="https://c/p")
    app.state.chain.raster = lambda svg, w, h, fmt: _png()
    return app


def _png():
    buf = BytesIO()
    Image.new("RGB", (60, 90), (200, 200, 200)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def lab(settings, sd):
    ask = FakeAsk()
    with TestClient(make(settings, sd, ask)) as c:
        c.ask = ask
        yield c


def wait_stage(c, wf_id, stages, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        wf = c.get(f"/api/v2/workflows/{wf_id}").json()
        if wf["stage"] in stages:
            return wf
        time.sleep(0.05)
    raise AssertionError(f"řetězec stojí ve fázi {wf['stage']}: {wf['stop_reason']}")


def start(c, **body):
    r = c.post("/api/v2/workflows/infografika", json={"topic": "Pantheon", "qid": "Q99309", "confirm_cost": True, **body})
    assert r.status_code == 201, r.text
    return r.json()


def test_one_price_up_front_nothing_starts_without_consent(lab, settings):
    r = lab.post("/api/v2/workflows/infografika", json={"topic": "Pantheon"})
    assert r.status_code == 402
    body = r.json()
    assert body["estimate_usd"] == pytest.approx(pp.estimate_usd(pp.DEFAULT_MODEL) + 0.07)
    assert [i["usd"] for i in body["items"]][0] == 0.0 and len(body["items"]) == 3
    assert lab.get("/api/v2/workflows").json() == [] and not settings.costs_path.exists()


def test_topic_runs_to_the_choice_without_clicks(lab, settings):
    wf = wait_stage(lab, start(lab)["id"], ("vyber", "stop"))
    assert wf["stage"] == "vyber", wf["stop_reason"]
    assert [c["what"] for c in lab.ask.calls] == ["návrhy skladby"]

    assert [p["nazev"] for p in wf["navrhy"]] == ["Velký řez", "Čísla"]     # návrh bez panelů vypadl
    first, second = wf["navrhy"]
    assert first["panely"][0]["fakta"] == ["f1"] and first["neznama_fakta"] == 1
    assert second["format"] == pp.DEFAULT_FORMAT and second["panely"][0]["w"] == 10     # panel oříznutý na plátno
    assert wf["spent_usd"] == pytest.approx(0.05) and wf["budget_usd"] == pytest.approx(pp.estimate_usd(pp.DEFAULT_MODEL) + 0.07)

    dossier = lab.get(f"/api/v2/research/{wf['research_id']}").json()
    assert dossier["status"] == "done" and dossier["dossier"]["facts"]
    sketch = lab.get(f"/api/v2/workflows/{wf['id']}/navrhy/navrh-1.svg")
    assert sketch.status_code == 200 and sketch.headers["content-type"].startswith("image/svg") and "1. Řez" in sketch.text and "Co je uvnitř" in sketch.text
    assert lab.get(f"/api/v2/workflows/{wf['id']}/navrhy/..%2Fx.svg").status_code == 404

    rows = [r for r in load_costs(settings.costs_path) if r["backend"] == "claude:navrhy"]
    assert len(rows) == 1 and rows[0]["status"] == "ok" and rows[0]["usd"] == 0.05


def test_pick_runs_the_advisory_check_and_blocks_nothing(lab, settings):
    wf = wait_stage(lab, start(lab)["id"], ("vyber",))
    assert lab.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 9}).status_code == 404
    assert lab.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 1}).status_code == 200
    done = wait_stage(lab, wf["id"], ("hotovo", "stop"))
    assert done["stage"] == "hotovo" and done["vyber"] == 1
    assert done["kontrola"]["summary"] == "Dává smysl." and done["kontrola"]["warnings"][0]["what"] == "Malé písmo"
    assert done["spent_usd"] == pytest.approx(0.10)
    assert {r["backend"] for r in load_costs(settings.costs_path)} >= {"claude:navrhy", "claude:check-logic"}
    assert lab.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 1}).status_code == 409


def test_failed_advisory_check_does_not_stop_the_chain(lab):
    wf = wait_stage(lab, start(lab)["id"], ("vyber",))

    def broken(*a, **k):
        raise claude.ClaudeError("kontrola logiky: odpověď nedokončena", {"usd": 0.01})

    lab.app.state.chain.check_ask = broken
    lab.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 1})
    done = wait_stage(lab, wf["id"], ("hotovo", "stop"))
    assert done["stage"] == "hotovo" and "nedokončena" in done["kontrola"]["chyba"] and done["spent_usd"] == pytest.approx(0.06)


def test_broken_sketch_raster_does_not_stop_the_chain(lab):
    wf = wait_stage(lab, start(lab)["id"], ("vyber",))

    def broken(*a, **k):
        raise OSError("Chromium nejde spustit")

    lab.app.state.chain.raster = broken
    lab.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 1})
    done = wait_stage(lab, wf["id"], ("hotovo", "stop"))
    assert done["stage"] == "hotovo" and "Chromium" in done["kontrola"]["chyba"] and done["spent_usd"] == pytest.approx(0.05)


def test_corrupt_workflow_file_does_not_stop_the_engine(settings, sd):
    wfs = WorkflowStore(settings.data_dir / "workflows")
    wfs.root.mkdir(parents=True)
    (wfs.root / "rozbity.json").write_text("{", encoding="utf-8")
    with TestClient(make(settings, sd, FakeAsk(), start_worker=False)) as c:
        assert c.get("/api/v2/health").json()["engine"] == "ok"


def test_step_over_budget_stops_and_asks(lab):
    lab.ask.usd = 0.50      # návrhy stály víc, než se schválilo: kontrola se už nevejde
    wf = wait_stage(lab, start(lab)["id"], ("vyber",))
    lab.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 1})
    stopped = wait_stage(lab, wf["id"], ("stop",))
    assert "nevejde" in stopped["stop_reason"] and stopped["resume_stage"] == "kontrola"
    assert [c["what"] for c in lab.ask.calls] == ["návrhy skladby"]     # kontrola se nezavolala

    r = lab.post(f"/api/v2/workflows/{wf['id']}/continue", json={})
    assert r.status_code == 402 and r.json()["estimate_usd"] == pytest.approx(0.07)
    lab.ask.usd = 0.05
    assert lab.post(f"/api/v2/workflows/{wf['id']}/continue", json={"confirm_cost": True}).status_code == 200
    assert wait_stage(lab, wf["id"], ("hotovo",))["kontrola"]["summary"]


def test_paid_failure_stops_and_keeps_what_it_cost(lab, settings):
    def bad(*a, **k):
        raise claude.ClaudeError("návrhy skladby: odpověď nedokončena", {"usd": 0.02})

    lab.app.state.chain.ask = bad
    wf = wait_stage(lab, start(lab)["id"], ("stop",))
    assert "nedokončena" in wf["stop_reason"] and wf["resume_stage"] == "navrhy" and wf["spent_usd"] == pytest.approx(0.02)
    rows = [r for r in load_costs(settings.costs_path) if r["backend"] == "claude:navrhy"]
    assert rows[0]["status"] == "failed" and rows[0]["usd"] == 0.02


def test_empty_dossier_pays_nothing(lab, settings):
    def nothing(host, params):
        reply = fake_get(host, params)
        if "wikidata" in host:
            reply["entities"]["Q99309"].update(claims={}, sitelinks={})
        return reply

    lab.app.state.chain.researcher.get = nothing
    wf = wait_stage(lab, start(lab)["id"], ("stop",))
    assert "fakta" in wf["stop_reason"] and lab.ask.calls == []
    assert not [r for r in load_costs(settings.costs_path) if r["backend"] == "claude:navrhy"]


def test_starts_from_a_finished_dossier_with_a_reference_image(lab):
    first = wait_stage(lab, start(lab)["id"], ("vyber",))
    buf = BytesIO()
    Image.new("RGB", (300, 200), (10, 20, 30)).save(buf, "PNG")
    ref = lab.app.state.chain.reflib.add(buf.getvalue(), origin="upload", title="vzor")["id"]
    lab.ask.reply = {**REPLY, "rozbor": {"drzet": ["žánr"], "zmenit": ["skladbu"]}}

    price = lab.post("/api/v2/workflows/infografika", json={"research": first["research_id"]})
    assert price.status_code == 402 and len(price.json()["items"]) == 2     # podklady už jsou

    wf = wait_stage(lab, start(lab, research=first["research_id"], vzor=ref)["id"], ("vyber",))
    assert wf["research_id"] == first["research_id"] and wf["rozbor"]["drzet"] == ["žánr"]
    assert lab.ask.calls[-1]["content"][0]["type"] == "image"
    assert lab.post("/api/v2/workflows/infografika", json={"research": "neni-v1", "confirm_cost": True}).status_code == 404
    assert lab.post("/api/v2/workflows/infografika", json={"topic": "x", "vzor": "0" * 32, "confirm_cost": True}).status_code == 404


def test_restart_in_the_free_step_carries_on_by_itself(settings, sd):
    ask = FakeAsk()
    with TestClient(make(settings, sd, ask, start_worker=False)) as c:
        wf_id = start(c)["id"]
        row = c.app.state.store.next_queued()   # úloha běží, když Engine spadne
        assert row["kind"] == ch.KIND and json.loads(row["request"])["stage"] == "podklady"
    with TestClient(make(settings, sd, ask)) as c:
        wf = wait_stage(c, wf_id, ("vyber", "stop"))
        assert wf["stage"] == "vyber", wf["stop_reason"]
        assert c.get(f"/api/v2/jobs/{row['id']}").json()["error"] == "přerušeno restartem Engine"
        assert len(ask.calls) == 1


def test_restart_in_the_paid_step_stops_and_asks_counting_the_estimate(settings, sd):
    ask = FakeAsk()
    with TestClient(make(settings, sd, ask)) as c:
        wf_id = wait_stage(c, start(c)["id"], ("vyber",))["id"]
        research_id = c.get(f"/api/v2/workflows/{wf_id}").json()["research_id"]
    # stav jako při pádu uprostřed návrhů: úloha běží, odhad je v ledgeru jako pending
    wfs = WorkflowStore(settings.data_dir / "workflows")
    with TestClient(make(settings, sd, ask, start_worker=False)) as c:
        wf = wfs.get(wf_id)
        c.app.state.chain.enqueue(wf.model_copy(update={"navrhy": [], "stage": "navrhy", "spent_usd": 0.0}), "navrhy")
        row = c.app.state.store.next_queued()
        assert json.loads(row["request"])["stage"] == "navrhy"
    calls = len(ask.calls)
    with TestClient(make(settings, sd, ask)) as c:
        wf = c.get(f"/api/v2/workflows/{wf_id}").json()
        assert wf["stage"] == "stop" and wf["resume_stage"] == "navrhy" and "restart" in wf["stop_reason"]
        assert wf["research_id"] == research_id and wf["spent_usd"] == pytest.approx(pp.estimate_usd(wf["model"]))
        time.sleep(0.8)
        assert len(ask.calls) == calls      # sám znovu nezaplatil
        r = c.post(f"/api/v2/workflows/{wf_id}/continue", json={})
        assert r.status_code == 402
        assert c.post(f"/api/v2/workflows/{wf_id}/continue", json={"confirm_cost": True}).status_code == 200
        assert wait_stage(c, wf_id, ("vyber",))["navrhy"]


def test_queued_step_survives_a_restart_without_a_second_job(settings, sd):
    ask = FakeAsk()
    with TestClient(make(settings, sd, ask, start_worker=False)) as c:
        wf = start(c)
    with TestClient(make(settings, sd, ask, start_worker=False)) as c:
        assert c.app.state.store.queue_len() == 1
        assert c.get(f"/api/v2/workflows/{wf['id']}").json()["step_job"] == wf["step_job"]


def test_chain_and_historical_guide_do_not_mix(lab):
    guide = lab.post("/api/v2/workflows/historical", json={"object": "loď"}).json()
    assert guide["kind"] == "historical"
    assert lab.post(f"/api/v2/workflows/{guide['id']}/pick", json={"navrh": 1}).status_code == 404
    assert lab.post(f"/api/v2/workflows/{guide['id']}/continue", json={}).status_code == 404


def test_model_choice_goes_to_the_price_and_the_ledger(lab, settings):
    cheap = lab.get("/api/v2/workflows/infografika/estimate", params={"model": "gpt-6.1-terra"}).json()
    dear = lab.get("/api/v2/workflows/infografika/estimate", params={"model": "claude-sonnet-5-5"}).json()
    assert cheap["total_usd"] < dear["total_usd"] and "gpt-6.1-terra" in cheap["items"][1]["what"]
    wf = wait_stage(lab, start(lab, model="gpt-6.1-terra")["id"], ("vyber",))
    assert lab.ask.calls[-1]["model"] == "gpt-6.1-terra" and wf["model"] == "gpt-6.1-terra"
    assert [r["usd"] for r in load_costs(settings.costs_path) if r["backend"] == "openai:navrhy"] == [0.05]


def test_sketch_escapes_text_and_keeps_inside_the_panel():
    proposal = pp.clean({"navrhy": [{"nazev": "X", "panely": [{"titulek": "<script>", "co": "a & b " * 200, "x": 0, "y": 0, "w": 50, "h": 20}]}]},
                        {"facts": []})[0]
    svg = pp.sketch(proposal)
    assert "<script>" not in svg and "&lt;script&gt;" in svg and "…" in svg


def test_dossier_text_is_one_line_per_fact_and_cut():
    dossier = {"tema": "T", "entita": {"label": "L", "popis": "p"}, "images": [{"role": "rez", "ref_id": "a"}, {"role": "rez"}],
               "facts": [{"id": "f1", "stav": "rozpor", "tema": "stavba", "tvrzeni": "x" * 500}]}
    text = pp.dossier_text(dossier)
    assert "rez 1" in text and "f1 [rozpor, stavba] " + "x" * pp.MAX_FACT_TEXT in text and "x" * (pp.MAX_FACT_TEXT + 1) not in text
