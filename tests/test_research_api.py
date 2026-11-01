"""Dossier přes Engine: úloha ve frontě, nové verze, placená část jen s confirm_cost, obrázky v knihovně předloh."""
import json
import time
from io import BytesIO
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from engine.app import create_app
from engine.jobs import load_costs
from engine.backends import FluxLocal
from engine.reflib import RefLibError
from ngm_shared import research as rs
from tests.test_engine_v2 import api, sd, settings  # noqa: F401  (fixtures)

PAGE_EN = ("The Pantheon's dome is still the world's largest unreinforced concrete dome.\n\n"
           "== Structure ==\nThe oculus is 9.1 metres (30 ft) in diameter.\nThe dome features sunken panels (coffers), in five rings of 28.\n")
PAGE_CS = "Pantheon je chrám v Římě.\n\n== Popis ==\nV jeho středu je otvor (okulus) o průměru 9 m.\n"
PAGE_DE = "== Technische Daten ==\nDurchmesser Opaion (DO): 8,95 m\n"


def fake_get(host, params):
    """Wikipedia, Wikidata a Commons bez sítě, tvar z odpovědí MediaWiki API."""
    if "wikidata" in host:
        if params["ids"] == "Q99309":
            return {"entities": {"Q99309": {
                "labels": {"cs": {"value": "Pantheon"}, "en": {"value": "Pantheon"}}, "descriptions": {"cs": {"value": "chrám v Římě"}},
                "sitelinks": {"cswiki": {"title": "Pantheon"}, "enwiki": {"title": "Pantheon, Rome"}, "dewiki": {"title": "Pantheon (Rom)"}},
                "modified": "2026-10-20T10:00:00Z",
                "claims": {"P373": [{"mainsnak": {"datavalue": {"value": "Pantheon (Rome)"}}}],
                           "P2048": [{"mainsnak": {"datavalue": {"value": {"amount": "+43.3", "unit": "http://www.wikidata.org/entity/Q11573"}}}}],
                           "P84": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]}}}}
        return {"entities": {"Q5": {"labels": {"cs": {"value": "Apollodóros"}}}}}
    if host == "commons.wikimedia.org":
        if params.get("list") == "categorymembers":
            return {"query": {"categorymembers": []}}
        return {"query": {"pages": [
            {"title": "File:Pantheon Floor plan.jpg", "index": 1, "imageinfo": [{"url": "https://u/plan.jpg", "thumburl": "https://u/t.jpg", "descriptionurl": "https://c/plan", "width": 2000, "height": 1500,
             "extmetadata": {"Artist": {"value": "<a href='x'>Dehio</a>"}, "LicenseShortName": {"value": "CC0"}}}]},
            {"title": "File:Pantheon malý.jpg", "index": 2, "imageinfo": [{"url": "https://u/m.jpg", "width": 200, "height": 150, "extmetadata": {}}]},
            {"title": "File:Pantheon, vadny soubor, plan.jpg", "index": 3, "imageinfo": [{"url": "https://u/v.jpg", "width": 2000, "height": 900, "extmetadata": {}}]},
        ]}}
    if params.get("generator") == "search":
        return {"query": {"pages": [{"title": "Pantheon", "index": 1, "pageprops": {"wikibase_item": "Q99309"}, "extract": "Chrám v Římě."}]}}
    if params.get("list") == "search":
        return {"query": {"search": []}}
    lang = host.split(".")[0]
    text = {"cs": PAGE_CS, "en": PAGE_EN, "de": PAGE_DE}.get(lang)
    if not text:
        return {"query": {"pages": [{"missing": True}]}}
    return {"query": {"pages": [{"title": params["titles"], "extract": text, "fullurl": f"https://{host}/wiki/{params['titles']}",
                                 "revisions": [{"revid": 7, "timestamp": "2026-10-22T10:00:00Z"}]}]}}


@pytest.fixture
def lab(settings, sd):
    """Engine s Researcherem bez sítě: Wikipedia ze souboru, obrázky z paměti, hledání na webu zamockované."""
    app = create_app(settings, backends={"flux-local": FluxLocal(settings, sd)}, server=sd)
    researcher = next(h.__self__ for k, h in app.state.worker.handlers.items() if k == "research")
    buf = BytesIO()
    Image.new("RGB", (2000, 1500), (90, 70, 60)).save(buf, "JPEG")
    reflib = researcher.reflib

    def fetch_image(file):
        if "vadny" in file:
            raise RefLibError("Commons neodpovídá")
        return reflib.add(buf.getvalue(), origin="commons", title=file, author="Dehio", license="CC0", page_url="https://c/plan")

    researcher.get = fake_get
    researcher.fetch_image = fetch_image
    with TestClient(app) as c:
        c.researcher = researcher
        yield c


def wait_done(c, research_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = c.get(f"/api/v2/research/{research_id}").json()
        if state["status"] in ("done", "failed"):
            return state
        time.sleep(0.05)
    raise AssertionError(f"{research_id} nedoběhla: {state}")


def web_reply(text, urls):
    results = NS(type="web_search_tool_result", content=[NS(type="web_search_result", url=u, title=u) for u in urls])
    return NS(content=[results, NS(type="text", text=text, citations=None)], stop_reason="end_turn", model="claude-sonnet-5-5",
              usage=NS(input_tokens=20000, output_tokens=2000, server_tool_use=NS(web_search_requests=3)))


def test_free_dossier_runs_as_a_queued_job_and_never_overwrites(lab, settings):
    assert lab.get("/api/v2/research/estimate").json()["total_usd"] == 0
    r = lab.post("/api/v2/research", json={"topic": "Pantheon, Řím"})
    assert r.status_code == 202 and r.json()["id"] == "pantheon-rim-v1" and r.json()["estimate_usd"] == 0
    state = wait_done(lab, "pantheon-rim-v1")
    assert state["status"] == "done", state
    d = state["dossier"]
    assert d["entita"]["qid"] == "Q99309" and d["cost_usd"] == 0.0 and "pages" not in d
    oculus = next(f for f in d["facts"] if f["predmet"] == "okulus" and f["velicina"] == "průměr")
    assert oculus["stav"] == "rozpor" and oculus["hodnota"] == [8.95, 9.1] and d["facts"][0]["stav"] == "rozpor"
    assert all(z["url"].startswith("https://") and z["citace"] and z["datum"] for f in d["facts"] for z in f["zdroje"])
    assert any("five rings of 28" in f["tvrzeni"] for f in d["facts"])
    # obrázky: role, autor a licence, v knihovně předloh, ve Schránce se nehlásí jako nové; vadný soubor běh nezastaví
    plan = next(i for i in d["images"] if i["nazev"] == "Pantheon Floor plan.jpg")
    assert plan["role"] == "pudorys" and plan["autor"] == "Dehio" and plan["licence"] == "CC0" and plan["ref_id"]
    assert lab.get("/api/v2/refs").json()[0]["seen"] is True
    assert any(i.get("chyba") for i in d["images"])
    assert not any(i["nazev"] == "Pantheon malý.jpg" for i in d["images"])
    assert "Chybí obrázek: řez." in d["otazky_bez_odpovedi"]
    # přehled obrázků a texty stránek pro kontrolu faktů
    page = lab.get(state["page"])
    assert page.status_code == 200 and "Podklady: Pantheon" in page.text
    assert lab.get("/api/v2/research/pantheon-rim-v1/obr-01.jpg").status_code == 200
    assert lab.get("/api/v2/research/pantheon-rim-v1/dossier.json").status_code == 404
    assert (settings.library_dir / "research" / "pantheon-rim-v1" / "pages" / "en-pantheon-rome.txt").exists()
    # úloha nepřidala nic do výpisu obrázků ani do útraty
    assert lab.get("/api/v2/jobs").json() == [] and not settings.costs_path.exists()
    before = (settings.library_dir / "research" / "pantheon-rim-v1" / "dossier.json").read_bytes()
    assert lab.post("/api/v2/research", json={"topic": "Pantheon, Řím"}).json()["id"] == "pantheon-rim-v2"
    wait_done(lab, "pantheon-rim-v2")
    assert (settings.library_dir / "research" / "pantheon-rim-v1" / "dossier.json").read_bytes() == before
    assert {r["id"] for r in lab.get("/api/v2/research").json()} == {"pantheon-rim-v1", "pantheon-rim-v2"}


def test_paid_extension_needs_confirmation_and_goes_to_the_ledger_after_each_reply(lab, settings):
    lab.post("/api/v2/research", json={"topic": "Pantheon, Řím", "images": False})
    wait_done(lab, "pantheon-rim-v1")
    assert lab.get("/api/v2/research/estimate?paid=true").json()["total_usd"] == rs.WEB_USD
    called = []

    def turn(text, system, *, on_reply, **kw):
        called.append(text)
        answer = json.dumps({"facts": [{"tvrzeni": "Okulus má 8,2 m.", "predmet": "okulus", "velicina": "průměr", "hodnota": 8.2, "jednotka": "m",
                                        "zdroje": [{"url": "https://moore", "nazev": "Moore 2002", "citace": "8.2 m"}]}], "otazky_bez_odpovedi": ["Hustoty."]}, ensure_ascii=False)
        reply = web_reply(answer, ["https://moore"])
        on_reply(reply)
        return [reply]

    lab.researcher.web_turn = turn
    no = lab.post("/api/v2/research", json={"extends": "pantheon-rim-v1"})
    assert no.status_code == 402 and no.json()["estimate_usd"] == rs.WEB_USD and called == []
    assert lab.post("/api/v2/research", json={"extends": "neni-v1", "confirm_cost": True}).status_code == 404
    r = lab.post("/api/v2/research", json={"extends": "pantheon-rim-v1", "confirm_cost": True})
    assert r.status_code == 202 and r.json()["id"] == "pantheon-rim-v2"
    state = wait_done(lab, "pantheon-rim-v2")
    assert state["status"] == "done", state
    assert "Rozpor mezi zdroji: Okulus" in called[0]        # ptá se na rozpory a otázky bez odpovědi z dossieru
    d = state["dossier"]
    oculus = next(f for f in d["facts"] if f["predmet"] == "okulus" and f["velicina"] == "průměr")
    assert oculus["hodnota"] == [8.2, 9.1] and any(z["url"] == "https://moore" for z in oculus["zdroje"])
    assert d["cost_usd"] == 0.09      # 20 000 / 2 000 tokenů Sonnet 5.5 = 0,06 + 3 hledání
    rows = load_costs(settings.costs_path)
    assert len(rows) == 1 and rows[0]["status"] == "ok" and rows[0]["usd"] == 0.09 and rows[0]["backend"] == "claude:research"
    assert lab.get("/api/v2/research/pantheon-rim-v1").json()["dossier"]["cost_usd"] == 0.0


def test_paid_failure_keeps_what_was_spent_in_the_ledger(lab, settings):
    from ngm_shared.claude import ClaudeError
    lab.post("/api/v2/research", json={"topic": "Pantheon", "images": False})
    wait_done(lab, "pantheon-v1")

    def turn(text, system, *, on_reply, **kw):
        on_reply(web_reply("", ["https://x"]))
        raise ClaudeError("rešerše na webu: odpověď nedokončena")

    lab.researcher.web_turn = turn
    lab.post("/api/v2/research", json={"extends": "pantheon-v1", "confirm_cost": True})
    state = wait_done(lab, "pantheon-v2")
    assert state["status"] == "failed" and "nedokončena" in state["error"]
    rows = load_costs(settings.costs_path)
    assert rows[-1]["status"] == "failed" and rows[-1]["usd"] == 0.09


def test_unknown_topic_fails_with_a_readable_reason(lab):
    lab.researcher.get = lambda host, params: {"query": {"pages": []}}
    lab.post("/api/v2/research", json={"topic": "xqzw"})
    state = wait_done(lab, "xqzw-v1")
    assert state["status"] == "failed" and "nic nenašel" in state["error"]
    assert lab.post("/api/v2/research", json={"topic": "  "}).status_code == 400
    assert lab.get("/api/v2/research/neni-v9").status_code == 404
    assert lab.get("/api/v2/research/../../etc").status_code in (400, 404)


def test_image_used_directly_has_its_author_and_licence_in_the_footer(lab):
    buf = BytesIO()
    Image.new("RGB", (640, 480), (90, 70, 60)).save(buf, "PNG")
    meta = lab.researcher.reflib.add(buf.getvalue(), origin="commons", title="Pantheon Floor plan.jpg", author="Dehio", license="CC BY-SA 4.0", page_url="https://c/plan")
    r = lab.post("/api/v2/infographics/from-ref", json={"ref_id": meta["id"]})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["ai_note"] == "Obraz: Dehio, CC BY-SA 4.0, Wikimedia Commons; schéma a popisky redakčně."
    assert doc["title"] == "Pantheon Floor plan"
    prov = lab.get("/api/v2/jobs/" + doc["base"].replace("/", "/images/") + "/provenance").json()
    assert prov["ai_generated"] is False and prov["license"] == "CC BY-SA 4.0" and prov["cost_usd"] == 0
    assert lab.post("/api/v2/infographics/from-ref", json={"ref_id": "neni"}).status_code == 404
