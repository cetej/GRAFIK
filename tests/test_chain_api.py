"""Řetězec infografika z tématu: jedna cena předem, doběhne k výběru bez kliknutí, zastaví se nad rozpočtem, přežije restart."""
import json
import time
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

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
CHAIN_USD = pp.estimate_usd(pp.DEFAULT_MODEL) + 0.07 + sr.estimate_usd(pp.DEFAULT_MODEL)


class FakeAsk:
    """Na návrhy i kontrolu; pamatuje si volání, cena z konstruktoru."""

    def __init__(self, usd=0.01, reply=None):
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
    ("osoba", ("portret|zivot|dilo", "Životopis sám nestačí", "První stránka o člověku je životopisná", "predloha portret"), ("hlavni|rez|pudorys", "Jediný velký řez", "rekonstrukce")),
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


def test_web_is_the_default_and_print_changes_the_prompt():
    from engine import proposals
    assert proposals.system_prompt("vec") == proposals.system_prompt("vec", "web")
    assert "360 px" in proposals.system_prompt("vec") and "PRO_KOHO" not in proposals.system_prompt("vec")
    assert "tisková příloha" in proposals.system_prompt("vec", "tisk") and "360 px" not in proposals.system_prompt("vec", "tisk")


FACTS = [{"id": f"f{i}", "stav": "jediny_zdroj", "tema": "dilo", "tvrzeni": f"Fakt {i}, rok 18{i:02d}.", "zdroje": [{"nazev": "Wikipedia (cs): Nikola Tesla", "citace": f"citace {i}", "url": "u"}]} for i in range(1, 13)]
SERIES_DOSSIER = {"facts": FACTS, "images": [{"role": "portret", "ref_id": "r1"}, {"role": "dilo", "ref_id": "r2"}, {"role": "nezarazeno", "ref_id": "r3"}], "entita": {"label": "Tesla", "druh": "osoba"}, "tema": "Tesla"}


def series_panel(*facts, **over):
    return {"titulek": "Panel", "co": "co", "druh": "text", "x": 0, "y": 0, "w": 100, "h": 40, "poradi": 1, "fakta": list(facts), "predloha": None, **over}


SERIES = {"navrhy": [{"nazev": "Série", "veta": "Věta.", "format": "4:5", "panely": [series_panel("f1", "f2", predloha="portret", druh="hlavni")],
                      "dalsi_stranky": [{"nazev": "Druhá", "veta": "Jiná.", "panely": [series_panel("f2", "f3", predloha="dilo", druh="hlavni"), series_panel("f4", "f999", poradi=2)]},
                                        {"nazev": "Prázdná", "panely": []}, "rozbité",
                                        {"nazev": "Třetí", "format": "2:3", "panely": [series_panel("f5")]}, {"nazev": "Čtvrtá", "panely": [series_panel("f1")]}, {"nazev": "Navíc", "panely": [series_panel("f6")]}]}]}


def test_proposal_is_a_series_and_a_fact_stays_on_one_page():
    proposal = pp.clean(SERIES, SERIES_DOSSIER)[0]
    pages = pp.pages(proposal)
    assert [p["nazev"] for p in pages] == ["Série", "Druhá", "Třetí", "Čtvrtá"]       # prázdná a rozbitá vypadly, série má nejvýš 4 stránky
    assert pages[1]["format"] == "4:5" and pages[2]["format"] == "2:3"      # bez formátu jako první stránka
    assert pages[0]["panely"][0]["fakta"] == ["f1", "f2"] and pages[1]["panely"][0]["fakta"] == ["f3"]
    assert proposal["opakovana_fakta"] == 2 and proposal["neznama_fakta"] == 1 and proposal["fakta"] == 5
    assert pp.pages({"nazev": "starý návrh", "panely": []}) == [{"nazev": "starý návrh", "panely": []}]
    assert "stránka 2: Druhá" in pp.layout_text(proposal, [1, 2]) and "stránka 3" not in pp.layout_text(proposal, [1, 2])


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
    reply = {"navrhy": [{"nazev": "Série", "veta": "Věta.", "format": "4:5", "panely": [{**PANEL, "predloha": None, "druh": "text", "fakta": ["f1"]}],
                         "dalsi_stranky": [{"nazev": "Druhá", "veta": "Jiná.", "panely": [{**PANEL, "predloha": None, "druh": "text", "fakta": ["f2"]}]}]}]}
    texts = {"stranky": [{"stranka": 1, "titulek": "Proč stojí", "uvod": "Stojí v Římě.", "polozky": [{"fakt": "f1", "bod": None, "value": "Stavba", "text": "stojí v Římě"}]},
                         {"stranka": 2, "titulek": "Co je jinak", "polozky": [{"fakt": "f2", "value": "Text", "text": "jen text bez obrazu"}, {"fakt": "f1", "value": "Cizí", "text": "fakt z jiné stránky"}]}]}

    class Ask(FakeAsk):
        def __call__(self, content, system, *, what, model, effort="low", max_tokens=16000):
            self.calls.append({"what": what, "model": model, "content": content})
            data = LOGIC if what == "kontrola logiky" else texts if what == "texty stránek" else self.reply
            return claude.Answer(json.dumps(data, ensure_ascii=False), model, 1000, 500, self.usd, "end_turn")

    ask = Ask(reply=reply)
    with TestClient(make(settings, sd, ask)) as c:
        first = wait_stage(c, start(c)["id"], ("vyber",))
        role = next(i["role"] for i in c.get(f"/api/v2/research/{first['research_id']}").json()["dossier"]["images"] if i.get("ref_id") and i["role"] != "nezarazeno")
        reply["navrhy"][0]["panely"][0]["predloha"] = role          # první stránka má předlohu z dossieru, druhá jen text
        wf = wait_stage(c, start(c, research=first["research_id"])["id"], ("vyber",))
        assert c.post(f"/api/v2/workflows/{wf['id']}/stranky").status_code == 409     # ještě není vybráno
        c.post(f"/api/v2/workflows/{wf['id']}/pick", json={"navrh": 1})
        wait_stage(c, wf["id"], ("hotovo",))
        assert c.post(f"/api/v2/workflows/{wf['id']}/stranky").status_code == 200
        deadline = time.time() + 40
        done = c.get(f"/api/v2/workflows/{wf['id']}").json()
        while not done["serie"] and done["stage"] != "stop" and time.time() < deadline:
            time.sleep(0.05)
            done = c.get(f"/api/v2/workflows/{wf['id']}").json()
        assert done["stage"] == "hotovo", done["stop_reason"]
        assert [(p["stranka"], p["nazev"]) for p in done["serie"]] == [(1, "Proč stojí"), (2, "Co je jinak")]
        second = done["serie"][1]
        assert any("fakt mimo stránku" in note for note in second["hlaseni"]) and any("bez obrazu" in note for note in second["hlaseni"])
        for page in done["serie"]:
            doc = c.get(f"/api/v2/infographics/{page['doc']}").json()
            assert doc["size"] in ("1080x1350", "1080x1620", "1080x1080") and doc["pismo"]["jednotek"] == pn.MOBIL["jednotek"] and doc["serie"]["celkem"] == 2
            found = [row for row in c.get(f"/api/v2/infographics/{page['doc']}/kontrola").json() if not row["ok"]]
            assert not [row for row in found if "mobil" in row["text"] or "zasahuje" in row["text"] or "přetéká" in row["text"]], found
            assert doc["sources"] and doc["sources"] not in c.get(f"/api/v2/infographics/{page['doc']}/svg").text      # zdroj je v dokumentu, na stránce ne
        first = c.get(f"/api/v2/infographics/{done['serie'][0]['doc']}").json()
        assert "Dehio, CC0" in first["ai_note"] and "Dehio, CC0" in first["na_strance"] and "Dehio, CC0" in c.get(f"/api/v2/infographics/{first['id']}/svg").text      # autor cizího obrazu zůstává i na stránce
        assert c.post(f"/api/v2/workflows/{wf['id']}/stranky").status_code == 409     # složené se znovu neplatí


def test_a_number_the_fact_does_not_have_drops_the_item():
    fact = {"tvrzeni": "Narození: 10. 7. 1856", "hodnota": "1856-07-10", "zdroje": [{"citace": "postavil 1 000 cívek a 2,5 km vedení, 150,000 USD"}]}
    assert sr.documented({"value": "1856", "text": "narodil se 10. 7."}, fact) == []
    assert sr.documented({"value": "1 000", "text": "cívek a 2,5 km, 150 000 USD"}, fact) == []
    assert sr.documented({"value": "1857", "text": "narodil se"}, fact) == ["1857"]
    proposal = pp.clean(SERIES, SERIES_DOSSIER)[0]
    answer = {"stranky": [{"stranka": 1, "titulek": "T", "uvod": "Věta.", "polozky": [{"fakt": "f1", "value": "1801", "text": "doloženo", "bod": "rotor"}, {"fakt": "f1", "value": "1999", "text": "vymyšleno"}, {"fakt": "f9", "value": "Cizí", "text": "fakt z jiné stránky"}]}]}
    out = sr.write_texts(SERIES_DOSSIER, proposal, [1], ask=lambda *a, **k: claude.Answer(json.dumps(answer), "m", 1, 1, 0.0, "end_turn"))
    page = out["stranky"][1]
    assert [i["value"] for i in page["polozky"]] == ["1801"] and page["polozky"][0]["bod"] == "rotor" and page["uvod"] == "Věta."
    assert any("1999" in note for note in out["hlaseni"][1]) and any("mimo stránku" in note for note in out["hlaseni"][1])
    with pytest.raises(claude.ClaudeError):
        sr.write_texts(SERIES_DOSSIER, proposal, [1], ask=lambda *a, **k: claude.Answer("{}", "m", 1, 1, 0.0, "end_turn"))


def test_same_picture_is_not_used_twice_and_a_missing_one_is_reported():
    proposal = pp.clean({"navrhy": [{"nazev": "S", "panely": [series_panel("f1", predloha="portret"), series_panel(poradi=2, predloha="portret", obrazek="obraz")],
                                     "dalsi_stranky": [{"nazev": "D", "panely": [series_panel("f2", druh="hlavni", obrazek="model")]}]}]}, {**SERIES_DOSSIER, "images": [{"role": "portret", "ref_id": "r1"}]})[0]
    images, notes = sr.pick_images(SERIES_DOSSIER, proposal, [1, 2])
    assert images[(1, 1)]["ref_id"] == "r1" and (1, 2) not in images and (2, 1) not in images
    assert any("krok 3f" in note for note in notes[2])


def picture(res=(800, 800), points=None, solid=(300, 100, 500, 700)):
    """Obraz s průhledným okolím, objekt je obdélník uprostřed."""
    alpha = Image.new("L", res, 0)
    alpha.paste(255, solid)
    return {"id": "o1", "typ": "obraz", "poradi": 1, "nazev": "Obraz", "rect": [0, 0, 1, 1], "zdroj": {"slozka": "x"}, "_res": res, "_alpha": alpha, "_points": points or {"horni": [400, 200], "dolni": [400, 600]}}


ITEMS = [{"value": "Horní díl", "text": "krátké vysvětlení k věci", "bod": "horni"}, {"value": "Dolní díl", "text": "další krátké vysvětlení", "bod": "dolni"}, {"value": "1891", "text": "patent bez místa na obraze", "bod": None}]


def boxes_of(fields):
    k = int(fields["size"].split("x")[0]) / pn.MOBIL["jednotek"]
    labels = [pn._text_box(label, pn.MOBIL["popisek"] * k) for p in fields["panels"] if p["typ"] == "obraz" for label in p["labels"]]
    texts = [(*p["rect"][:3], pn.text_height(p, pn.MOBIL, k)) for p in fields["panels"] if p["typ"] == "text"]
    return labels, texts


@pytest.mark.parametrize("res,solid", [((800, 800), (300, 100, 500, 700)), ((800, 1400), (300, 40, 500, 1360)), ((1400, 500), (40, 100, 1360, 400))])
@pytest.mark.parametrize("size", ["1080x1350", "1080x1620", "1080x1080"])
def test_page_puts_the_callouts_next_to_the_object_and_keeps_all_on_the_page(size, res, solid):
    hero = picture(res, {"horni": [res[0] // 2, res[1] // 3], "dolni": [res[0] // 2, 2 * res[1] // 3]}, solid)
    fields, dropped = sr.compose("Krátký titulek", "Jedna věta, co čtenář z obrazu pochopí.", "", hero, ITEMS, {}, size)
    assert not dropped
    W, H = (int(v) for v in fields["size"].split("x"))
    assert W == 1080
    main = next(p for p in fields["panels"] if p["typ"] == "obraz")
    assert all(0 <= v for v in main["rect"]) and main["rect"][0] + main["rect"][2] <= W + 0.5 and main["rect"][1] + main["rect"][3] <= H + 0.5
    assert [label["text"] for label in main["labels"]] == ["Horní díl", "Dolní díl"] and all(label["small"] for label in main["labels"])
    labels, texts = boxes_of(fields)
    assert texts, "fakt bez bodu jde do volné plochy"
    every = labels + texts
    assert all(not (a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]) for i, a in enumerate(every) for b in every[i + 1:])
    for box in every:
        assert box[0] >= 0 and box[0] + box[2] <= W and box[1] + box[3] <= H and box[1] > fields["nadpis"]["y"]
    place = panels_place(main, hero)
    for box in labels:     # text leží vedle objektu, ne přes něj
        x0, y0 = (box[0] - place[0]) / place[2], (box[1] - place[1]) / place[2]
        x1, y1 = (box[0] + box[2] - place[0]) / place[2], (box[1] + box[3] - place[1]) / place[2]
        assert x1 <= solid[0] + 2 or x0 >= solid[2] - 2 or y1 <= solid[1] + 2 or y0 >= solid[3] - 2


def panels_place(main, hero):
    x, y, w, h = main["rect"]
    return x, y, w / hero["_res"][0]


def test_picture_grows_as_far_as_the_callouts_allow():
    small_text = sr.compose("Titulek", "", "", picture(), ITEMS[:1], {}, "1080x1350")[0]
    much_text = sr.compose("Titulek", "", "", picture(), ITEMS[:1] + [{"value": f"Popisek {i}", "text": "s vysvětlením na dva řádky pod ním", "bod": "dolni"} for i in range(4)], {}, "1080x1350")[0]
    width = lambda fields: next(p for p in fields["panels"] if p["typ"] == "obraz")["rect"][2]
    assert width(small_text) >= width(much_text) and width(small_text) > 900


def test_what_does_not_fit_is_reported_not_shrunk():
    long = [{"value": f"Položka {i}", "text": "Dlouhá věta, která se na stránku nevejde ani omylem, když je jich tolik. " * 3, "bod": None} for i in range(9)]
    fields, dropped = sr.compose("Titulek", "", "", picture(), long, {}, "1080x1080")
    assert dropped and all(d.startswith("Položka") for d in dropped)
    assert all(p.get("small_size", pn.MOBIL["veta"] * 1080 / 546) * 360 / 1080 >= pn.PHONE_MIN_PX for p in fields["panels"] if p["typ"] == "text")


def test_long_title_takes_two_lines_short_one_is_big():
    k = 1080 / pn.MOBIL["jednotek"]
    assert sr._title_size("Motor", 1080, pn.MOBIL, k) == pytest.approx(1080 / 9, rel=0.02)
    long = sr._title_size("Jak se z malého chlapce ze Smiljanu stal vynálezce střídavého proudu", 1080, pn.MOBIL, k)
    assert long >= pn.MOBIL["titulek"] * k


def test_small_pictures_go_with_their_items_in_a_column():
    small = {key: {**picture(), "id": key} for key in ("motor", "civka")}
    items = [{"value": "1888", "text": "motor", "bod": None, "obraz": "motor", "fakt": "f"}, {"value": "1891", "text": "cívka", "bod": None, "obraz": "civka", "fakt": "f"}]
    fields, dropped = sr.compose("Muž za vynálezy", "Věta.", "Figura: AI", picture((400, 1400), {}, (20, 20, 380, 1380)), items, small, "1080x1350")
    assert not dropped
    insets = [p for p in fields["panels"] if p["id"].startswith("obr")]
    texts = [p for p in fields["panels"] if p["typ"] == "text"]
    assert len(insets) == 2 and all(p["pruhledny"] for p in insets) and insets[0]["rect"][1] < texts[0]["rect"][1] < insets[1]["rect"][1] < texts[1]["rect"][1]     # po sobě, chronologicky


def test_picture_keeps_its_size_and_the_weakest_label_goes():
    """Operátor 2. 11.: „Často zmenšíš hlavní grafiku na úkor pitomých, blbě zalomených popisků s nulovou informační hodnotou.“"""
    wide = picture((1000, 1000), {"horni": [500, 300], "dolni": [500, 700]}, (60, 60, 940, 940))
    crowd = [{"value": f"Popisek {i}", "text": "s dlouhým vysvětlením na několik řádků pod názvem", "bod": "horni" if i % 2 else "dolni"} for i in range(5)]
    fields, dropped = sr.compose("Titulek", "Věta.", "", wide, crowd, {}, "1080x1350")
    main = next(p for p in fields["panels"] if p["typ"] == "obraz")
    W = int(fields["size"].split("x")[0])
    assert sorted(dropped) == [f"Popisek {i} s dlouhým vysvětlením na několik řádků pod názvem" for i in range(len(main["labels"]), 5)]
    assert main["rect"][2] * 0.88 >= 0.55 * W      # objekt zůstane přes půl stránky


def test_label_of_the_picture_outranks_loose_facts_and_the_big_page_wins():
    """Model dal fakty před popisek motoru: popisek zmizel a stránka se kvůli faktům zmenšila na čtverec."""
    wide = picture((1000, 1000), {"cast": [400, 300]}, (40, 40, 960, 960))
    items = [{"value": "Niagarská elektrárna", "text": "Podle Teslovy rady vsadila na střídavý proud.", "bod": None},
             {"value": "60 000 dolarů", "text": "Hotovost a akcie za práva na jeho motor.", "bod": None},
             {"value": "Cívky", "text": "Střídavý proud v nich roztáčí magnetické pole.", "bod": "cast"}]
    fields, dropped = sr.compose("Titulek", "Věta.", "", wide, items, {}, "1080x1620")
    main = next(p for p in fields["panels"] if p["typ"] == "obraz")
    assert [label["text"] for label in main["labels"]] == ["Cívky"] and "Cívky Střídavý proud v nich roztáčí magnetické pole." not in dropped
    assert fields["size"] == "1080x1620" and main["rect"][2] > 900


def test_leader_to_the_text_does_not_run_across_the_object():
    tall = picture((1000, 1000), {"osa": [420, 500]}, (360, 40, 640, 960))     # válec uprostřed, bod blíž levé straně
    item = {"value": "Válec", "text": "Vysvětlení pod názvem.", "bod": "osa"}
    fields, _ = sr.compose("Titulek", "Věta.", "", tall, [item], {}, "1080x1620")
    main = next(p for p in fields["panels"] if p["typ"] == "obraz")
    assert [label["align"] for label in main["labels"]] == ["right"]     # z pravé strany by čára přešla přes celý válec
    place = {"x": main["rect"][0], "y": main["rect"][1], "k": main["rect"][2] / 1000, "info": {"points": {"osa": [420, 500]}, "res": (1000, 1000)}}
    sheet = pn.Sheet(1080, 1620)
    sheet.add_picture(tuple(main["rect"]), tall["_alpha"])
    size = pn.MOBIL["popisek"] * 1080 / pn.MOBIL["jednotek"]
    assert not sr._crosses_object(pn.leader_points(main["labels"][0], place, size, main["id"]), sheet, size * sr.LEADER_OVER)
    assert sr._crosses_object([(420, 500), (700, 500)], sr_sheet_with_block(), size)


def sr_sheet_with_block():
    sheet = pn.Sheet(1080, 1620)
    sheet.add_box((400, 400, 280, 200))
    return sheet


def test_number_in_another_fact_of_the_page_keeps_the_label():
    dossier = {"facts": [{"id": "a", "stav": "shoda", "tvrzeni": "Věž: výška 57 m"}, {"id": "b", "stav": "shoda", "tvrzeni": "Morgan slíbil peníze na stavbu."}], "entita": {"label": "T"}}
    proposal = {"nazev": "V", "veta": "", "format": "2:3", "panely": [{"fakta": ["a", "b"], "poradi": 1}], "dalsi_stranky": []}
    answer = {"stranky": [{"stranka": 1, "titulek": "T", "uvod": "", "polozky": [{"fakt": "b", "value": "57 metrů", "text": "Vysoká věž", "bod": "vez"}, {"fakt": "b", "value": "99 metrů", "text": "Vymyšleno"}]}]}
    out = sr.write_texts(dossier, proposal, [1], ask=lambda *a, **k: claude.Answer(json.dumps(answer), "m", 1, 1, 0.0, "end_turn"))
    assert [item["value"] for item in out["stranky"][1]["polozky"]] == ["57 metrů"] and out["stranky"][1]["polozky"][0]["fakt"] == "a"
    assert out["hlaseni"][1] == ["Číslo 99 není ve faktu b, položka vypadla."]


def test_proposal_says_which_own_pictures_have_no_page():
    """„A co ty další dvě karty. Ty jsi je zahodil?“ Malý doprovod stránku nedá."""
    own = [{"id": "motor", "nazev": "Motor"}, {"id": "civka", "nazev": "Cívka"}, {"id": "vez", "nazev": "Věž"}, {"id": "figura", "nazev": "Figura"}]
    reply = {"navrhy": [{"nazev": "S", "panely": [series_panel("f1", vlastni="motor"), series_panel(poradi=2, vlastni="civka")],
                         "dalsi_stranky": [{"nazev": "D", "panely": [series_panel("f2", vlastni="figura")]}]}]}
    assert pp.clean(reply, SERIES_DOSSIER, own)[0]["bez_stranky"] == ["Cívka", "Věž"]


def test_small_own_picture_stays_after_it_was_the_main_one_on_an_earlier_page():
    own = [{"id": "motor", "nazev": "Motor"}, {"id": "figura", "nazev": "Figura"}]
    dossier = {**SERIES_DOSSIER, "images": [{"role": "portret", "ref_id": "fotka"}]}
    reply = {"navrhy": [{"nazev": "Život", "panely": [series_panel("f1", vlastni="figura")],
                         "dalsi_stranky": [{"nazev": "Motor", "panely": [series_panel("f2", vlastni="motor"), series_panel(poradi=2, vlastni="figura", druh="portret")]}]}]}
    images, _ = sr.pick_images(dossier, pp.clean(reply, dossier, own)[0], [1, 2], own)
    assert images[(2, 2)]["id"] == "figura"     # životopis jde první, dobová fotka ho na další stránce nenahradí


def test_own_3d_picture_wins_over_an_old_photo():
    own = [{"id": "motor", "nazev": "Motor", "slozka": "rendery/motor", "popisky": {"rotor": "Rotor"}},
           {"id": "figura", "nazev": "Tesla, 3D figura", "kratce": "Figura", "slozka": "rendery/figura", "ai": "FLUX 3 Klein"}]
    proposal = pp.clean({"navrhy": [{"nazev": "S", "format": "4:5", "panely": [series_panel("f1", predloha="dilo", vlastni="motor", druh="hlavni", obrazek="model"), series_panel(poradi=2, vlastni="cizi")],
                                     "dalsi_stranky": [{"nazev": "D", "panely": [series_panel("f2", vlastni="motor", predloha="portret", druh="hlavni"), series_panel(poradi=2, vlastni="figura")]},
                                                       {"nazev": "T", "panely": [series_panel("f3", vlastni="figura", druh="hlavni"), series_panel(poradi=2, vlastni="figura")]}]}]}, SERIES_DOSSIER, own)[0]
    assert proposal["panely"][1]["vlastni"] is None         # neznámý vlastní obraz vypadne
    images, notes = sr.pick_images(SERIES_DOSSIER, proposal, [1, 2, 3], own)
    assert images[(1, 1)]["id"] == "motor" and images[(2, 1)]["role"] == "portret" and images[(2, 2)]["id"] == "figura" and images[(3, 1)]["id"] == "figura"       # hlavní obraz jednou, malý doprovod smí znovu
    assert 1 not in notes
    alpha = Image.new("L", (400, 400), 0)
    alpha.paste(255, (120, 120, 280, 280))
    def picture_of(image):
        return {"zdroj": {"slozka": image["slozka"], **({"ai": image["ai"]} if image.get("ai") else {})}, "_res": (400, 400), "_alpha": alpha, "_points": {"rotor": [200, 200]}}
    fields, said = sr.page_fields(3, pp.pages(proposal)[2], {"titulek": "Muž", "uvod": "", "polozky": [{"value": "1888", "text": "patent", "bod": None, "fakt": "f3"}]}, images, SERIES_DOSSIER, picture_of)
    assert fields["template"] == "dark" and fields["sources"] == "Wikipedia (cs)" and [note for note in said if "Formát" not in note] == ["Hlavní obraz nemá žádný popisek."]


def page_with_picture(root, rect, picture, res=(400, 800)):
    folder = root / "panely" / "p"
    folder.mkdir(parents=True)
    picture.save(folder / "obraz.png")
    (folder / "body.json").write_text(json.dumps({"res": list(res), "points": {}}), encoding="utf-8")
    doc = {"size": "1080x1350", "title": "T", "subtitle": "Věta", "nadpis": {"y": 80, "size": 80}, "sources": "x", "ai_note": "x", "na_strance": "", "pismo": pn.MOBIL, "template": "dark",
           "panels": [{"id": "p", "typ": "obraz", "nazev": "Obraz", "rect": rect, "zdroj": {"slozka": "x"}, "poradi": 1, "pruhledny": True}]}
    doc["panels"] = pn.validate(doc)
    return doc


def test_empty_band_and_a_lattice_lost_on_the_dark_page_are_found(tmp_path):
    """Dvě výtky operátora z 2. 11. jako měření: tmavá kupole na tmavé stránce a prázdný pruh nad motorem."""
    picture = Image.new("RGBA", (400, 800), (0, 0, 0, 0))
    draw = ImageDraw.Draw(picture)
    for x in range(0, 400, 50):
        draw.line([(x, 0), (x, 180)], fill=(44, 47, 52, 255), width=4)
    draw.rectangle((100, 200, 300, 800), fill=(200, 180, 150, 255))
    doc = page_with_picture(tmp_path, [0, 800, 250, 500], picture)
    assert pn.faint_parts({"id": "p"}, tmp_path, pn.THEMES["dark"]["bg"]) == ["horní"]
    assert pn.empty_share(doc, tmp_path) > pn.MAX_EMPTY
    found = [row["text"] for row in pn.checks(doc, tmp_path) if not row["ok"]]
    assert any("prázdná plocha" in text for text in found) and any("splývá" in text for text in found)
    full = Image.new("RGBA", (400, 800), (200, 180, 150, 255))
    other = tmp_path / "plny"
    other.mkdir()
    filled = page_with_picture(other, [40, 240, 1000, 1070], full)
    assert pn.empty_share(filled, other) < pn.MAX_EMPTY and pn.faint_parts({"id": "p"}, other, pn.THEMES["dark"]["bg"]) == []


def test_loose_fact_never_wraps_into_a_narrow_column_or_shrinks_the_picture():
    """Stránka o motoru 2. 11.: „60 000 dolarů“ na pět úzkých řádků vedle obrazu."""
    wide = picture((1000, 1000), {"horni": [500, 300], "dolni": [500, 700]}, (60, 60, 940, 940))
    label = {"value": "Točivé pole", "text": "dvě cívky v pravém úhlu", "bod": "horni"}
    long = {"value": "60 000 dolarů", "text": "licence Westinghouse roku 1888 a k tomu ještě 2,50 dolaru za každou koňskou sílu, kterou motor vyrobí", "bod": None}
    alone = sr._compose("Titulek", "Věta.", "", wide, [label], {}, "1080x1350", pn.MOBIL)[0]
    fields, dropped, _ = sr._compose("Titulek", "Věta.", "", wide, [label, long], {}, "1080x1350", pn.MOBIL)
    width = lambda doc: next(p for p in doc["panels"] if p["typ"] == "obraz")["rect"][2]
    assert width(fields) == width(alone) and dropped == [f"{long['value']} {long['text']}"] and not [p for p in fields["panels"] if p["typ"] == "text"]
    short = {"value": "1888", "text": "licence pro Westinghouse", "bod": None}
    fields, dropped, _ = sr._compose("Titulek", "Věta.", "", wide, [label, short], {}, "1080x1620", pn.MOBIL)
    assert not dropped and [p for p in fields["panels"] if p["typ"] == "text"]


def test_long_labels_go_in_a_row_above_a_wide_object_and_the_picture_stays_big():
    wide = picture((1000, 800), {"cast": [300, 300], "druha": [700, 400]}, (20, 20, 980, 780))
    items = [{"value": "Cívky", "text": "střídavý proud v nich žene magnetické pole dokola", "bod": "cast"}, {"value": "Rotor", "text": "běží za tím polem, a tak se celý motor točí", "bod": "druha"}]
    fields, dropped = sr.compose("Motor", "Věta.", "", wide, items, {}, "1080x1620")
    main = next(p for p in fields["panels"] if p["typ"] == "obraz")
    assert not dropped and main["rect"][2] > 950 and all(label["nad"] for label in main["labels"])
    k = 1080 / pn.MOBIL["jednotek"]
    place = {"x": main["rect"][0], "y": main["rect"][1], "k": main["rect"][2] / 1000, "info": {"points": wide["_points"], "res": (1000, 800)}}
    for label in main["labels"]:
        (ax, ay), (bx, by) = pn.leader_points(label, place, pn.MOBIL["popisek"] * k)
        x, y, w, h = pn._text_box(label, pn.MOBIL["popisek"] * k)
        assert ax == bx and by >= y + h and x <= ax <= x + w and ay > by     # čára rovně dolů z vlastního textu


def test_no_label_wraps_into_a_narrow_column():
    wide = picture((1000, 1000), {"horni": [500, 300], "dolni": [500, 700]}, (60, 60, 940, 940))
    long = [{"value": "Část", "text": "velmi dlouhé vysvětlení, které by se na úzkém sloupku zalomilo na mnoho krátkých řádků vedle obrazu", "bod": "horni"}]
    fields, _ = sr.compose("Titulek", "Věta.", "", wide, long, {}, "1080x1350")
    labels = next(p for p in fields["panels"] if p["typ"] == "obraz")["labels"]
    assert all(len(label["small"]) <= sr.MAX_FACT_LINES for label in labels)


def test_death_of_a_relative_is_not_a_life_fact():
    dossier = {"facts": [{"id": "a", "tvrzeni": "Tesla died alone in 1943."}, {"id": "b", "tvrzeni": "Tesla's father died in 1879."}, {"id": "c", "tvrzeni": "Narození: 10. 7. 1856"}]}
    assert sr.life_facts(dossier) == ["a", "c"]


def test_no_line_ends_with_a_one_letter_word():
    text = sr._no_orphan("Střídavý proud v nich žene pole a točí se k rotoru u osy.")
    for chars in range(10, 40):
        rows = pn.wrap(text, chars)
        assert [row for row in rows[:-1] if len(row.split()[-1]) == 1] == [], chars
        assert " ".join(rows).split() == text.split()
    for chars in range(6, 30):      # „slíbil 150 / 000 dolarů“, „občanství, 30. / července“
        rows = pn.wrap(sr._no_orphan("Bankéř slíbil 150 000 dolarů a občanství přišlo 30. července."), chars)
        assert not [row for row in rows if row.endswith(("150", "30."))] and not [row for row in rows if row.startswith("000")], chars


def test_a_life_turn_without_a_year_keeps_the_timeline():
    hero = picture((400, 1000), {}, (20, 20, 380, 980))
    items = [{"value": value, "text": "událost v životě člověka", "bod": None, "fakt": "f1"} for value in ("1856", "Paříž", "Červen 1884", "1891", "1943")]
    fields, _ = sr.compose("Nikola Tesla", "Kdo byl.", "", hero, items, {}, "1080x1350")
    assert next(p for p in fields["panels"] if p["typ"] != "obraz")["typ"] == "osa"


def test_format_follows_the_picture_instead_of_leaving_a_hole():
    tall = picture((600, 1400), {"horni": [300, 400], "dolni": [300, 1000]}, (200, 20, 400, 1380))
    wide = picture((1400, 700), {"horni": [500, 200], "dolni": [900, 500]}, (20, 20, 1380, 680))
    fields, dropped = sr.compose("Věž", "Věta.", "", tall, ITEMS[:2], {}, "1080x1080")
    assert not dropped and fields["size"] == "1080x1620"
    fields, _ = sr.compose("Stroj", "Věta.", "", wide, [], {}, "1080x1620")
    assert fields["size"] in ("1080x1080", "1080x1350")     # nízký obraz na vysoké stránce by nechal díru


def test_life_page_has_a_timeline_and_birth_and_death_are_always_offered():
    facts = [*FACTS, {"id": "f90", "tvrzeni": "Narození: 10. 7. 1856", "stav": "shoda", "zdroje": []}, {"id": "f91", "tvrzeni": "Tesla died alone in a hotel in 1943.", "stav": "jediny_zdroj", "zdroje": []}]
    dossier = {**SERIES_DOSSIER, "facts": facts}
    assert sr.life_facts(dossier) == ["f90", "f91"]
    figure = {"id": "figura", "nazev": "Tesla, 3D figura", "kratce": "Figura", "druh": "osoba", "slozka": "x", "ai": "FLUX", "popisky": {"ruka": "Ruka"}}
    page = {"nazev": "Život", "veta": "Kdo byl.", "format": "4:5", "panely": [series_panel("f1", vlastni="figura", druh="hlavni")]}
    proposal = {**page, "dalsi_stranky": []}
    images = {(1, 1): figure}
    assert sr.is_life_page(1, page, images) and not sr.is_life_page(1, page, {(1, 1): {"id": "motor"}})
    request = sr.request_text(dossier, proposal, [1], images)
    assert "ŽIVOTOPISNÁ STRÁNKA" in request and "f90" in request and "f91" in request
    answer = {"stranky": [{"stranka": 1, "titulek": "Tesla", "uvod": "Kdo byl.", "polozky": [{"fakt": "f90", "value": "1856", "text": "narozen"}]}]}
    out = sr.write_texts(dossier, proposal, [1], ask=lambda *a, **k: claude.Answer(json.dumps(answer), "m", 1, 1, 0.0, "end_turn"), images=images)
    assert [i["value"] for i in out["stranky"][1]["polozky"]] == ["1856"] and not out["hlaseni"][1]      # fakt o narození návrh nevybral, a přesto smí
    answer["stranky"][0]["polozky"] = [{"fakt": "f1", "value": "Práce", "text": "bez dat ze života"}]
    out = sr.write_texts(dossier, proposal, [1], ask=lambda *a, **k: claude.Answer(json.dumps(answer), "m", 1, 1, 0.0, "end_turn"), images=images)
    assert any("narození ani smrt" in note for note in out["hlaseni"][1])
    hero = picture((400, 1000), {}, (20, 20, 380, 980))
    items = [{"value": year, "text": "událost v životě člověka", "bod": None, "fakt": "f1"} for year in ("1856", "1884", "1888", "1891", "1943")]
    fields, dropped = sr.compose("Nikola Tesla", "Kdo byl.", "Figura: AI", hero, items, {}, "1080x1350")
    axis = next(p for p in fields["panels"] if p["typ"] == "osa")
    W, H = (int(v) for v in fields["size"].split("x"))
    assert not dropped and axis["pod_sebou"] and len(axis["items"]) == 5 and axis["rect"][3] > 0.6 * H      # po celé výšce, ne hromádka nahoře
    body = next(p for p in fields["panels"] if p["typ"] == "obraz")
    assert axis["rect"][0] >= body["rect"][0] + body["rect"][2] - 40 and axis["rect"][0] + axis["rect"][2] <= W


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
