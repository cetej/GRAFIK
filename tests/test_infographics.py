"""G5 infographics: document, schema templates, SVG cleaning, export, label proposal."""
import base64
import json
from io import BytesIO

import pytest
from PIL import Image

from engine.infographics import InfoError, ai_note, clean_svg
from tests.test_engine_v2 import _first_image, api, sd, settings  # noqa: F401  (fixtures)

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="990"><rect width="1280" height="990" fill="#1d2532"/>'
       '<text x="40" y="60">Římská kvinquerema</text><text x="40" y="980">{note}</text></svg>')


def test_clean_svg_drops_scripts_handlers_and_external_links():
    dirty = ('<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(2)</script>'
             '<a href="https://evil.example"><rect onclick="x()" width="1" height="1"/></a>'
             '<use href="#r"/><image href="data:image/png;base64,AAAA"/><foreignObject><div/></foreignObject></svg>')
    out = clean_svg(dirty)
    assert "script" not in out and "onload" not in out and "onclick" not in out and "evil" not in out
    assert "foreignObject" not in out and 'href="#r"' in out and "data:image" not in out
    assert "data:image/png" in clean_svg(dirty, allow_data_images=True)
    with pytest.raises(InfoError):
        clean_svg("<html/>")


def test_ai_note_from_provenance():
    assert ai_note({"backend": "flux-local", "refs": [{"sent_as": "image"}]}) == \
        "Ilustrace: FLUX 3 Klein (AI) podle předlohy, schéma a popisky redakčně."
    assert ai_note({"backend": "flux-local", "refs": []}).startswith("Ilustrace: FLUX 3 Klein (AI), ")


def test_infographic_document_lifecycle(api, settings):
    base = _first_image(api)
    ref = f"{base['job_id']}/0"
    assert api.post("/api/v2/infographics", json={"base": "nope-1/0"}).status_code == 404
    doc = api.post("/api/v2/infographics", json={"base": ref, "title": "Římská kvinquerema"}).json()
    assert doc["ai_note"].startswith("Ilustrace: FLUX 3 Klein (AI)") and doc["size"] == "1280x990"
    labels = [{"text": "Corvus", "small": "sklopný most", "anchor": [210, 540], "pos": [120, 296]}]
    doc = api.put(f"/api/v2/infographics/{doc['id']}", json={**doc, "labels": labels, "ai_note": "smazáno",
                                                              "schema": {"title": "Řez", "svg": '<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>'}}).json()
    assert doc["labels"][0]["text"] == "Corvus" and doc["ai_note"].startswith("Ilustrace:")  # AI label stays
    assert "script" not in doc["schema"]["svg"]
    assert api.put(f"/api/v2/infographics/{doc['id']}", json={**doc, "size": "5x5"}).status_code == 400
    assert [d["id"] for d in api.get("/api/v2/infographics").json()] == [doc["id"]]
    moved = api.delete(f"/api/v2/infographics/{doc['id']}").json()["moved_to"]
    assert ".trash" in moved and api.get(f"/api/v2/infographics/{doc['id']}").status_code == 404


def test_export_svg_png_pdf_with_provenance(api, settings):
    base = _first_image(api)
    doc = api.post("/api/v2/infographics", json={"base": f"{base['job_id']}/0", "title": "Test"}).json()
    svg = SVG.format(note=doc["ai_note"])
    assert api.post(f"/api/v2/infographics/{doc['id']}/export", json={"svg": SVG.format(note=""), "format": "png"}).status_code == 400
    out = {}
    for fmt in ("svg", "png", "pdf"):
        r = api.post(f"/api/v2/infographics/{doc['id']}/export", json={"svg": svg, "format": fmt})
        assert r.status_code == 201, r.text
        out[fmt] = api.get(r.json()["url"])
    assert Image.open(BytesIO(out["png"].content)).size == (1280, 990)
    assert out["pdf"].content.startswith(b"%PDF") and "Římská" in out["svg"].text
    ex = settings.library_dir / "infographics" / doc["id"] / "exports"
    prov = json.loads(next(ex.glob("*.png.json")).read_text(encoding="utf-8"))
    assert prov["ai_generated"] is True and prov["base"] == f"{base['job_id']}/0" and prov["base_provenance"]["backend"] == "flux-local"
    assert len(api.get(f"/api/v2/infographics/{doc['id']}").json()["exports"]) == 3
    assert api.post(f"/api/v2/infographics/{doc['id']}/export", json={"svg": svg, "format": "gif"}).status_code == 400


def test_schema_templates(api, settings):
    r = api.post("/api/v2/schemas", json={"title": "Řez trupem", "svg": '<svg xmlns="http://www.w3.org/2000/svg" onload="x()"><rect/></svg>'})
    assert r.status_code == 201 and r.json()["slug"] == "rez-trupem"
    lst = api.get("/api/v2/schemas").json()
    assert lst[0]["title"] == "Řez trupem" and "onload" not in lst[0]["svg"]


def test_repo_schema_template_is_clean():
    from pathlib import Path
    svg = (Path(__file__).parents[1] / "schemas" / "rez-trupem-kvinquerema.svg").read_text(encoding="utf-8")
    assert clean_svg(svg).count("<use") == 10


def test_suggest_labels_paid_and_parsed(api, settings, monkeypatch):
    from engine import app as app_mod
    from engine import backends
    base = _first_image(api)
    doc = api.post("/api/v2/infographics", json={"base": f"{base['job_id']}/0", "title": "loď"}).json()
    r = api.post(f"/api/v2/infographics/{doc['id']}/suggest-labels", json={})
    assert r.status_code == 402 and r.json()["estimate_usd"] == 0.01
    sent = []
    monkeypatch.setattr(backends, "claude_text", lambda c, mt, what: sent.append(c) or
                        'Here: [{"text": "Kloun", "small": "bronz", "x": 120, "y": 930}, {"text": "", "x": 1, "y": 1},'
                        ' {"text": "Věž", "x": "700", "y": 2000}, {"text": "bez bodu"}]')
    monkeypatch.setattr(app_mod, "suggest_labels", backends.suggest_labels)
    out = api.post(f"/api/v2/infographics/{doc['id']}/suggest-labels", json={"confirm_cost": True}).json()
    assert out["labels"] == [{"text": "Kloun", "small": "bronz", "anchor": [120, 930]},
                             {"text": "Věž", "small": "", "anchor": [700, 1000]}]
    assert "loď" in sent[0][1]["text"] and max(Image.open(BytesIO(base64.b64decode(sent[0][0]["source"]["data"]))).size) <= 1024
    assert api.get("/api/v2/costs").json()["entries"][-1]["backend"] == "claude:labels"
