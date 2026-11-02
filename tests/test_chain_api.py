"""Řetězec infografika z tématu: jedna cena předem, doběhne k výběru bez kliknutí, zastaví se nad rozpočtem, přežije restart."""
import json
import time
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from engine import chain as ch
from engine import panels as pn
from engine import proposals as pp
from engine import serie as sr
from engine.app import create_app
from engine.backends import FluxLocal
from engine.jobs import load_costs
from engine.workflows import WorkflowStore
from ngm_shared import claude, research
from tests.test_engine_v2 import api, sd, settings  # noqa: F401  (fixtures)
from tests.test_research_api import fake_get

PANEL = {"titulek": "Řez", "co": "Co je uvnitř", "druh": "rez", "x": 0, "y": 0, "w": 100, "h": 60, "poradi": 1, "fakta": ["f1", "f999"], "predloha": "rez"}
REPLY = {"navrhy": [{"nazev": "Velký řez", "veta": "Čtenář pochopí stavbu.", "format": "2:3", "panely": [PANEL], "vzhled": "a cutaway"},
                    {"nazev": "Bez panelů", "panely": []},
                    {"nazev": "Čísla", "veta": "Rozměry.", "format": "neznámý", "panely": [{**PANEL, "x": 90, "w": 50, "fakta": ["f1"]}]}]}
LOGIC = {"souhrn": "Dává smysl.", "ucel": "Ukázat stavbu.", "problemy": [{"co": "Malé písmo", "proc": "x", "oprava": "y", "zavaznost": "nízká"}]}
TEXTS = {"stranky": [{"stranka": 1, "titulek": "Proč stojí", "panely": [{"panel": 1, "nadpis": "Řez", "polozky": [{"fakt": "f1", "value": "Stavba", "text": "Stojí v Římě."}]}]}]}
CHAIN_USD = pp.estimate_usd(pp.DEFAULT_MODEL) + 0.07 + sr.estimate_usd(pp.DEFAULT_MODEL)


class FakeAsk:
    """Na návrhy i kontrolu; pamatuje si volání, cena z konstruktoru."""

    def __init__(self, usd=0.01, reply=None):
        self.usd, self.reply, self.calls = usd, reply or REPLY, []

    def __call__(self, content, system, *, what, model, effort="low", max_tokens=16000):
        self.calls.append({"what": what, "model": model, "content": content})
        data = LOGIC if what == "kontrola logiky" else TEXTS if what == "texty stránek" else self.reply
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
    assert body["estimate_usd"] == pytest.approx(CHAIN_USD)
    assert [i["usd"] for i in body["items"]][0] == 0.0 and len(body["items"]) == 4
    assert lab.get("/api/v2/workflows").json() == [] and not settings.costs_path.exists()


def test_topic_runs_to_the_choice_without_clicks(lab, settings):
    wf = wait_stage(lab, start(lab)["id"], ("vyber", "stop"))
    assert wf["stage"] == "vyber", wf["stop_reason"]
    assert [c["what"] for c in lab.ask.calls] == ["návrhy skladby"]

    assert [p["nazev"] for p in wf["navrhy"]] == ["Velký řez", "Čísla"]     # návrh bez panelů vypadl
    first, second = wf["navrhy"]
    assert first["panely"][0]["fakta"] == ["f1"] and first["neznama_fakta"] == 1
    assert second["format"] == pp.DEFAULT_FORMAT and second["panely"][0]["w"] == 10     # panel oříznutý na plátno
    assert wf["spent_usd"] == pytest.approx(0.01) and wf["budget_usd"] == pytest.approx(CHAIN_USD)

    dossier = lab.get(f"/api/v2/research/{wf['research_id']}").json()
    assert dossier["status"] == "done" and dossier["dossier"]["facts"]
    sketch = lab.get(f"/api/v2/workflows/{wf['id']}/navrhy/navrh-1.svg")
    assert sketch.status_code == 200 and sketch.headers["content-type"].startswith("image/svg") and "1. Řez" in sketch.text and "Co je uvnitř" in sketch.text
    assert lab.get(f"/api/v2/workflows/{wf['id']}/navrhy/..%2Fx.svg").status_code == 404

    rows = [r for r in load_costs(settings.costs_path) if r["backend"] == "claude:navrhy"]
    assert len(rows) == 1 and rows[0]["status"] == "ok" and rows[0]["usd"] == 0.01


def test_pick_runs_the_advisory_check_and_blocks_nothing(lab, settings):
    wf = wait_stage(lab, start(lab)["id"], ("vyber",))
    assert lab.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 9}).status_code == 404
    assert lab.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 1}).status_code == 200
    done = wait_stage(lab, wf["id"], ("hotovo", "stop"))
    assert done["stage"] == "hotovo" and done["vyber"] == 1
    assert done["kontrola"]["summary"] == "Dává smysl." and done["kontrola"]["warnings"][0]["what"] == "Malé písmo"
    assert done["spent_usd"] == pytest.approx(0.02)
    assert {r["backend"] for r in load_costs(settings.costs_path)} >= {"claude:navrhy", "claude:check-logic"}


def test_changing_the_pick_checks_again_within_the_price(lab):
    wf = wait_stage(lab, start(lab)["id"], ("vyber",))
    lab.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 1})
    wait_stage(lab, wf["id"], ("hotovo",))
    assert lab.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 2}).status_code == 200
    second = wait_stage(lab, wf["id"], ("hotovo", "stop"))
    assert second["vyber"] == 2 and second["stage"] == "hotovo" and second["spent_usd"] == pytest.approx(0.03)


def test_pick_is_refused_while_the_chain_runs(settings, sd):
    with TestClient(make(settings, sd, FakeAsk(), start_worker=False)) as c:
        wf = start(c)
        assert c.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 1}).status_code == 409


def test_failed_advisory_check_does_not_stop_the_chain(lab):
    wf = wait_stage(lab, start(lab)["id"], ("vyber",))

    def broken(*a, **k):
        raise claude.ClaudeError("kontrola logiky: odpověď nedokončena", {"usd": 0.01})

    lab.app.state.chain.check_ask = broken
    lab.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 1})
    done = wait_stage(lab, wf["id"], ("hotovo", "stop"))
    assert done["stage"] == "hotovo" and "nedokončena" in done["kontrola"]["chyba"] and done["spent_usd"] == pytest.approx(0.02)


def test_broken_sketch_raster_does_not_stop_the_chain(lab):
    wf = wait_stage(lab, start(lab)["id"], ("vyber",))

    def broken(*a, **k):
        raise OSError("Chromium nejde spustit")

    lab.app.state.chain.raster = broken
    lab.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 1})
    done = wait_stage(lab, wf["id"], ("hotovo", "stop"))
    assert done["stage"] == "hotovo" and "Chromium" in done["kontrola"]["chyba"] and done["spent_usd"] == pytest.approx(0.01)


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
    assert r.status_code == 402 and r.json()["estimate_usd"] == pytest.approx(0.07 + sr.estimate_usd(pp.DEFAULT_MODEL))
    lab.ask.usd = 0.01
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
    assert price.status_code == 402 and len(price.json()["items"]) == 3     # podklady už jsou

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
    assert [r["usd"] for r in load_costs(settings.costs_path) if r["backend"] == "openai:navrhy"] == [0.01]


def test_sketch_escapes_text_and_keeps_inside_the_panel():
    proposal = pp.clean({"navrhy": [{"nazev": "X", "panely": [{"titulek": "<script>", "co": "a & b " * 200, "x": 0, "y": 0, "w": 50, "h": 20}]}]},
                        {"facts": [], "images": []})[0]
    svg = pp.sketch(proposal)
    assert "<script>" not in svg and "&lt;script&gt;" in svg and "…" in svg


def test_dossier_text_is_one_line_per_fact_and_cut():
    dossier = {"tema": "T", "entita": {"label": "L", "popis": "p"}, "images": [{"role": "rez", "ref_id": "a"}, {"role": "rez"}],
               "facts": [{"id": "f1", "stav": "rozpor", "tema": "stavba", "tvrzeni": "x" * 500}]}
    text = pp.dossier_text(dossier)
    assert "rez 1" in text and "f1 [rozpor, stavba] " + "x" * pp.MAX_FACT_TEXT in text and "x" * (pp.MAX_FACT_TEXT + 1) not in text


def test_proposal_panel_says_its_question_and_where_the_picture_comes_from():
    known = {"f1": {}}
    panel = pp._panel({"titulek": "Scéna", "x": 0, "y": 0, "w": 50, "h": 50, "otazka": "Co se tu dělo?", "obrazek": "obraz", "fakta": ["f1"]}, 0, known, set(), set())
    assert panel["otazka"] == "Co se tu dělo?" and panel["obrazek"] == "obraz"
    assert pp._panel({"x": 0, "y": 0, "w": 50, "h": 50, "obrazek": "kouzlo"}, 0, known, set(), set())["obrazek"] is None


def _kind_dossier(kind=None):
    entity = {"label": "Nikola Tesla", "popis": "vynálezce", **({"druh": kind} if kind else {})}
    images = [{"role": "portret", "ref_id": "a"}, {"role": "mapa"}, {"role": "nezarazeno", "ref_id": "b"}]
    return {"tema": "T", "entita": entity, "images": images, "facts": [{"id": "f1", "stav": "shoda", "tema": "zivot", "tvrzeni": "Narodil se."}]}


def test_panel_keeps_only_the_picture_roles_the_dossier_has():
    panel = {"titulek": "P", "x": 0, "y": 0, "w": 50, "h": 50}
    reply = {"navrhy": [{"nazev": "N", "panely": [{**panel, "predloha": role} for role in ("portret", "rez", "mapa", "nezarazeno", "null", None, ["portret"])]}]}
    proposal = pp.clean(reply, _kind_dossier("osoba"))[0]
    assert [p["predloha"] for p in proposal["panely"]] == ["portret", None, None, None, None, None, None]
    assert proposal["neznama_predloha"] == 3     # rez není role osoby, k mapě není stažený obrázek, nezarazeno není role; null je volba


@pytest.mark.parametrize("kind, sees, not_sees", [
    ("osoba", ("portret|zivot|dilo", "Životopis po letech nestačí", "predloha portret"), ("hlavni|rez|pudorys", "Jediný velký řez", "rekonstrukce")),
    ("zvire", ("zvire|mapa|detail", "Mapa výskytu", "predloha zvire"), ("hlavni|rez|pudorys", "Jediný velký řez", "rekonstrukce")),
    ("vec", ("hlavni|rez|pudorys|detail|cisla|osa|text", "Jediný velký řez", "kdo věc používal"), ("portret", "Životopis")),
    (None, ("hlavni|rez|pudorys|detail|cisla|osa|text", "Jediný velký řez"), ("portret", "Životopis")),     # starší dossier druh nemá
])
def test_prompt_follows_the_kind_of_topic(kind, sees, not_sees):
    seen = {}

    def ask(content, system, *, what, model, effort="low", max_tokens=16000):
        seen["system"] = system
        return claude.Answer(json.dumps(REPLY, ensure_ascii=False), model, 1000, 500, 0.01, "end_turn")

    pp.propose(_kind_dossier(kind), ask=ask)
    assert all(word in seen["system"] for word in sees) and not any(word in seen["system"] for word in not_sees)


def test_estimate_covers_the_largest_measured_dossier():
    assert pp.estimate_usd(pp.DEFAULT_MODEL) >= 0.0551     # Tesla, 120 faktů: levnější odhad zastaví řetězec před kontrolou logiky


def test_panel_kinds_in_the_prompt_are_roles_of_that_kind():
    for kind, panels in pp.PANEL_KINDS.items():
        assert set(panels.split("|")) <= set(research.PROFILES[kind].get("roles", research.ROLES))


FACTS = [{"id": f"f{i}", "stav": "jediny_zdroj", "tema": "dilo", "tvrzeni": f"Fakt {i}, rok 18{i:02d}.", "zdroje": [{"nazev": "Wikipedia (cs): Nikola Tesla", "citace": f"citace {i}", "url": "u"}]} for i in range(1, 13)]
SERIES_DOSSIER = {"facts": FACTS, "images": [{"role": "portret", "ref_id": "r1"}, {"role": "dilo", "ref_id": "r2"}, {"role": "nezarazeno", "ref_id": "r3"}], "entita": {"label": "Tesla", "druh": "osoba"}, "tema": "Tesla"}


def series_panel(*facts, **over):
    return {"titulek": "Panel", "co": "co", "druh": "text", "x": 0, "y": 0, "w": 100, "h": 40, "poradi": 1, "fakta": list(facts), "predloha": None, **over}


SERIES = {"navrhy": [{"nazev": "Série", "veta": "Věta.", "format": "4:5", "panely": [series_panel("f1", "f2", predloha="portret", druh="hlavni")],
                      "dalsi_stranky": [{"nazev": "Druhá", "veta": "Jiná.", "panely": [series_panel("f2", "f3", predloha="dilo", druh="hlavni"), series_panel("f4", "f999", poradi=2)]},
                                        {"nazev": "Prázdná", "panely": []}, "rozbité",
                                        {"nazev": "Třetí", "format": "2:3", "panely": [series_panel("f5")]}, {"nazev": "Navíc", "panely": [series_panel("f6")]}]}]}


def test_proposal_is_a_series_and_a_fact_stays_on_one_page():
    proposal = pp.clean(SERIES, SERIES_DOSSIER)[0]
    pages = pp.pages(proposal)
    assert [p["nazev"] for p in pages] == ["Série", "Druhá", "Třetí"]       # prázdná a rozbitá vypadly, série má nejvýš 3 stránky
    assert pages[1]["format"] == "4:5" and pages[2]["format"] == "2:3"      # bez formátu jako první stránka
    assert pages[0]["panely"][0]["fakta"] == ["f1", "f2"] and pages[1]["panely"][0]["fakta"] == ["f3"]
    assert proposal["opakovana_fakta"] == 1 and proposal["neznama_fakta"] == 1 and proposal["fakta"] == 5
    assert pp.pages({"nazev": "starý návrh", "panely": []}) == [{"nazev": "starý návrh", "panely": []}]
    assert "stránka 2: Druhá" in pp.layout_text(proposal, [1, 2]) and "stránka 3" not in pp.layout_text(proposal, [1, 2])


def series_lab(settings, sd, reply, texts):
    class Ask(FakeAsk):
        def __call__(self, content, system, *, what, model, effort="low", max_tokens=16000):
            self.calls.append({"what": what, "model": model, "content": content})
            data = LOGIC if what == "kontrola logiky" else texts if what == "texty stránek" else self.reply
            return claude.Answer(json.dumps(data, ensure_ascii=False), model, 1000, 500, self.usd, "end_turn")
    return Ask(reply=reply)


def facts_of(c, research_id):
    return c.get(f"/api/v2/research/{research_id}").json()["dossier"]


def test_pick_chooses_pages_and_every_page_has_a_sketch(settings, sd):
    reply = {"navrhy": [{"nazev": "Série", "veta": "Věta.", "format": "4:5", "panely": [{**PANEL, "fakta": ["f1"]}], "dalsi_stranky": [{"nazev": "Druhá", "panely": [{**PANEL, "titulek": "Druhý řez", "fakta": ["f2"]}]}]}]}
    with TestClient(make(settings, sd, FakeAsk(reply=reply))) as c:
        wf = wait_stage(c, start(c)["id"], ("vyber",))
        assert len(wf["navrhy"][0]["dalsi_stranky"]) == 1
        assert "Druhý řez" in c.get(f"/api/v2/workflows/{wf['id']}/navrhy/navrh-1-2.svg").text
        assert c.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 1, "stranky": []}).status_code == 400
        assert c.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 1, "stranky": [3]}).status_code == 400
        assert c.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 1, "stranky": [2]}).json()["stranky"] == [2]
        assert wait_stage(c, wf["id"], ("hotovo",))["stranky"] == [2]
        assert c.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 1}).json()["stranky"] == [1, 2]


def test_pages_are_built_from_facts_and_each_is_checked(settings, sd):
    reply = {"navrhy": [{"nazev": "Série", "veta": "Věta.", "format": "4:5", "panely": [{**PANEL, "predloha": "rez", "fakta": ["f1"]}],
                         "dalsi_stranky": [{"nazev": "Druhá", "veta": "Jiná.", "panely": [{**PANEL, "predloha": None, "druh": "text", "fakta": ["f2"]}]}]}]}
    ask = FakeAsk(reply=reply)
    with TestClient(make(settings, sd, ask)) as c:
        wf = wait_stage(c, start(c)["id"], ("vyber",))
        assert c.post(f"/api/v2/workflows/{wf['id']}/stranky").status_code == 409     # ještě není vybráno
        c.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 1})
        wait_stage(c, wf["id"], ("hotovo",))
        dossier = facts_of(c, wf["research_id"])
        ask_texts = {"stranky": [{"stranka": 1, "titulek": "Proč stojí", "panely": [{"panel": 1, "nadpis": "Řez", "polozky": [{"fakt": "f1", "value": "Stavba", "text": "Stojí v Římě."}]}]},
                                 {"stranka": 2, "titulek": "Co je jinak", "panely": [{"panel": 1, "nadpis": "Rozdíl", "polozky": [{"fakt": "f2", "value": "Text", "text": "Jen text bez obrazu."}, {"fakt": "f1", "value": "Cizí", "text": "Fakt z jiné stránky."}]}]}]}
        import engine.chain as chain_module
        original = chain_module.serie.write_texts
        chain_module.serie.write_texts = lambda d, p, chosen, *, model, ask: original(d, p, chosen, model=model, ask=lambda *a, **k: claude.Answer(json.dumps(ask_texts, ensure_ascii=False), model, 1000, 500, 0.01, "end_turn"))
        try:
            assert c.post(f"/api/v2/workflows/{wf['id']}/stranky").status_code == 200
            done = wait_stage(c, wf["id"], ("hotovo", "stop"), timeout=40)
        finally:
            chain_module.serie.write_texts = original
        while not done["serie"] and done["stage"] != "stop":
            done = wait_stage(c, wf["id"], ("hotovo", "stop"))
        assert done["stage"] == "hotovo", done["stop_reason"]
        assert [(p["stranka"], p["nazev"]) for p in done["serie"]] == [(1, "Proč stojí"), (2, "Co je jinak")]
        second = done["serie"][1]
        assert any("fakt mimo panel" in note for note in second["hlaseni"])
        assert any("bez obrazu" in note for note in second["hlaseni"])
        for page in done["serie"]:
            doc = c.get(f"/api/v2/infographics/{page['doc']}").json()
            assert doc["size"] == "1080x1350" and doc["pismo"]["jednotek"] == pn.MOBIL["jednotek"] and doc["serie"]["celkem"] == 2
            found = [row for row in c.get(f"/api/v2/infographics/{page['doc']}/kontrola").json() if not row["ok"]]
            assert not [row for row in found if "mobil" in row["text"] or "zasahuje" in row["text"] or "přetéká" in row["text"]], found
            assert "Blender" not in doc["ai_note"]      # obrazy z dossieru, žádný render
        assert done["navrhy"][0]["panely"][0]["predloha"] is None or "Dehio, CC0" in c.get(f"/api/v2/infographics/{done['serie'][0]['doc']}").json()["ai_note"]
        assert c.post(f"/api/v2/workflows/{wf['id']}/stranky").status_code == 409     # složené se znovu neplatí
        assert dossier["facts"]


def test_a_number_the_fact_does_not_have_drops_the_item():
    fact = {"tvrzeni": "Narození: 10. 7. 1856", "hodnota": "1856-07-10", "zdroje": [{"citace": "postavil 1 000 cívek a 2,5 km vedení"}]}
    assert sr.documented({"value": "1856", "text": "narodil se 10. 7."}, fact) == []
    assert sr.documented({"value": "1 000", "text": "cívek a 2,5 km"}, fact) == []
    assert sr.documented({"value": "1857", "text": "narodil se"}, fact) == ["1857"]
    proposal = pp.clean(SERIES, SERIES_DOSSIER)[0]
    answer = {"stranky": [{"stranka": 1, "titulek": "T", "panely": [{"panel": 1, "nadpis": "N", "polozky": [{"fakt": "f1", "value": "1801", "text": "doloženo"}, {"fakt": "f1", "value": "1999", "text": "vymyšleno"}]}]}]}
    out = sr.write_texts(SERIES_DOSSIER, proposal, [1], ask=lambda *a, **k: claude.Answer(json.dumps(answer), "m", 1, 1, 0.0, "end_turn"))
    assert [i["value"] for i in out["stranky"][1]["panely"][1]["polozky"]] == ["1801"]
    assert any("1999" in note for note in out["hlaseni"][1])
    with pytest.raises(claude.ClaudeError):
        sr.write_texts(SERIES_DOSSIER, proposal, [1], ask=lambda *a, **k: claude.Answer("{}", "m", 1, 1, 0.0, "end_turn"))


def test_same_picture_is_not_used_twice_and_a_missing_one_is_reported():
    proposal = pp.clean({"navrhy": [{"nazev": "S", "panely": [series_panel("f1", predloha="portret"), series_panel(poradi=2, predloha="portret", obrazek="obraz")],
                                     "dalsi_stranky": [{"nazev": "D", "panely": [series_panel("f2", druh="hlavni", obrazek="model")]}]}]}, {**SERIES_DOSSIER, "images": [{"role": "portret", "ref_id": "r1"}]})[0]
    images, notes = sr.pick_images(SERIES_DOSSIER, proposal, [1, 2])
    assert images[(1, 1)]["ref_id"] == "r1" and (1, 2) not in images and (2, 1) not in images
    assert any("krok 3f" in note for note in notes[2])


def picture(res=(1200, 800), poradi=1):
    return {"id": "o1", "typ": "obraz", "poradi": poradi, "nazev": "Obraz", "rect": [0, 0, 1, 1], "zdroj": {"ref_id": "r"}, "_res": res}


def words(kind="text", count=2, text="Věta o tom, co se stalo a proč na tom záleží."):
    return {"id": "t1", "typ": kind, "poradi": 2, "nazev": "Text", "titulek": {"text": "Nadpis"}, "rect": [0, 0, 1, 1], "fakta": [], "items": [{"value": "1891", "text": text} for _ in range(count)], **({"smer": "radek"} if kind == "fakta" else {})}


@pytest.mark.parametrize("res", [(1200, 800), (800, 1200), (2200, 300)])
@pytest.mark.parametrize("size", ["1080x1350", "1080x1620", "1080x1080"])
def test_layout_keeps_everything_on_the_page(size, res):
    placed, dropped = sr.arrange("Krátký titulek", "Obraz: autor, licence; schéma a popisky redakčně.", "Wikipedia (cs).", [picture(res)], [words()], size)
    assert not dropped
    W, H = (int(v) for v in size.split("x"))
    k = W / pn.MOBIL["jednotek"]
    for panel in placed:
        x, y, w, h = panel["rect"]
        assert x >= 0 and y > 0 and x + w <= W + 0.5 and y + h <= H + 0.5, panel["rect"]
    doc = {"size": size, "title": "Krátký titulek", "sources": "Wikipedia (cs).", "ai_note": "Obraz: autor, licence; schéma a popisky redakčně.", "pismo": pn.MOBIL, "panels": placed}
    pic = next(p for p in placed if p["typ"] == "obraz")["rect"]
    text = next(p for p in placed if p["typ"] == "text")
    top = pn.footer(doc, pn.MOBIL, k, W, H)[1]
    assert text["rect"][1] + pn.text_height(text, pn.MOBIL, k) < top
    assert pic[1] + pic[3] < top


def test_what_does_not_fit_is_reported_not_shrunk():
    long = words(count=3, text="Dlouhá věta, která se na stránku nevejde ani omylem, " * 6)
    placed, dropped = sr.arrange("Titulek", "Poznámka.", "Zdroj.", [picture()], [long], "1080x1080")
    assert dropped and all(d.startswith("Text:") for d in dropped)
    remaining = next((p for p in placed if p["typ"] == "text"), None)
    assert remaining is None or len(remaining["items"]) < 3


def test_row_of_values_turns_into_a_list_when_they_would_collide():
    row = words("fakta", count=3)
    for item in row["items"]:
        item["value"] = "278 až 300 patentů"
    placed, _dropped = sr.arrange("Titulek", "Poznámka.", "Zdroj.", [picture()], [row], "1080x1350")
    assert next(p for p in placed if p["id"] == "t1")["typ"] == "text"
    fields, _notes = sr.page_fields(1, {"format": "4:5", "panely": [series_panel("f1", predloha="portret", druh="hlavni", obrazek="obraz")]},
                                    {"titulek": "T", "panely": {1: {"nadpis": "N", "polozky": [{"value": "1", "text": "a"}]}}},
                                    {(1, 1): {"ref_id": "r1"}}, SERIES_DOSSIER, lambda ref, name: f"{name}: autor", lambda image: {"zdroj": {"ref_id": image["ref_id"]}, "_res": (800, 600), "_alpha": None, "_points": {}})
    assert all(not key.startswith("_") for panel in fields["panels"] for key in panel)


def test_own_3d_picture_wins_over_an_old_photo_and_carries_its_labels(settings):
    own = [{"id": "motor", "nazev": "Motor", "slozka": "rendery/motor", "popisky": {"rotor": "Rotor", "neni": "Bod, který model nemá"}},
           {"id": "figura", "nazev": "Tesla, 3D figura", "slozka": "rendery/figura", "ai": "FLUX 3 Klein"}]
    proposal = pp.clean({"navrhy": [{"nazev": "S", "format": "4:5", "panely": [series_panel("f1", predloha="dilo", vlastni="motor", druh="hlavni", obrazek="model"), series_panel(poradi=2, vlastni="cizi")],
                                     "dalsi_stranky": [{"nazev": "D", "panely": [series_panel("f2", vlastni="motor", predloha="portret", druh="hlavni"), series_panel(poradi=2, vlastni="figura")]}]}]}, SERIES_DOSSIER, own)[0]
    assert proposal["panely"][1]["vlastni"] is None         # neznámý vlastní obraz vypadne
    images, notes = sr.pick_images(SERIES_DOSSIER, proposal, [1, 2], own)
    assert images[(1, 1)]["id"] == "motor" and images[(2, 1)]["role"] == "portret" and images[(2, 2)]["id"] == "figura"    # stejný model se neopakuje
    assert 1 not in notes
    alpha = Image.new("L", (400, 400), 0)
    alpha.paste(255, (120, 120, 280, 280))
    def picture_of(image):
        return {"zdroj": {"slozka": image["slozka"]}, "_res": (400, 400), "_alpha": alpha, "_points": {"rotor": [200, 200]}}
    fields, said = sr.page_fields(1, proposal, {"titulek": "Motor", "panely": {1: {"nadpis": "Jak funguje", "polozky": [{"value": "1888", "text": "patent"}]}}}, images, SERIES_DOSSIER, lambda r, n: "", picture_of)
    hero = next(p for p in fields["panels"] if p["typ"] == "obraz")
    assert [label["text"] for label in hero["labels"]] == ["Rotor"] and "Popisek se nevešel: Bod, který model nemá" in said
    x, y = hero["labels"][0]["pos"]
    k = 1080 / pn.MOBIL["jednotek"]
    box = pn._text_box(hero["labels"][0], pn.MOBIL["popisek"] * k)
    assert not sr._occupied({**hero, "_res": (400, 400), "_alpha": alpha}, box)      # text leží vedle modelu, ne přes něj
    assert fields["template"] == "light"


def test_own_pictures_file_is_read_and_a_broken_one_stops_the_chain(settings, tmp_path):
    dossier = {"entita": {"qid": "Q9036"}}
    assert sr.own_pictures(tmp_path, dossier) == []
    (tmp_path / "tema" / "Q9036").mkdir(parents=True)
    path = tmp_path / "tema" / "Q9036" / "obrazy.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(pn.InfoError):
        sr.own_pictures(tmp_path, dossier)
    path.write_text(json.dumps({"obrazy": [{"id": "motor", "nazev": "Motor", "slozka": "rendery/motor"}]}), encoding="utf-8")
    with pytest.raises(pn.InfoError, match="motor"):
        sr.own_pictures(tmp_path, dossier)
    (tmp_path / "rendery" / "motor").mkdir(parents=True)
    (tmp_path / "rendery" / "motor" / "obraz.png").write_bytes(b"x")
    assert sr.own_pictures(tmp_path, dossier)[0]["id"] == "motor"
    assert "motor: Motor" in pp.dossier_text({**SERIES_DOSSIER, "entita": {**SERIES_DOSSIER["entita"], "popis": "x"}}, sr.own_pictures(tmp_path, dossier))
