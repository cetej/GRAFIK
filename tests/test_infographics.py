"""G5 infographics: document, schema templates, SVG cleaning, export, label proposal."""
import base64
import hashlib
import json
import os
import re
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from engine.infographics import InfoError, ai_note, clean_svg, for_vectorcraft, rasterize
from ngm_shared.heavy_lock import HeavyBusy
from ngm_shared.textlayer.vc_client import VectorCraftError
from tests.test_engine_v2 import _first_image, api, sd, settings  # noqa: F401  (fixtures)

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="990"><rect width="1280" height="990" fill="#1d2532"/>'
       '<text x="40" y="60">Římská kvinquerema</text><text x="40" y="980">{note}</text></svg>')


def test_upload_from_computer_starts_an_infographic_without_touching_the_job_list(api):
    from base64 import b64encode
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (64, 48), (20, 50, 110)).save(buf, "PNG")
    doc = api.post("/api/v2/infographics/upload", json={"b64": b64encode(buf.getvalue()).decode(), "name": "mapa.png"})
    assert doc.status_code == 201, doc.text
    d = doc.json()
    assert d["title"] == "mapa"
    img = api.get("/api/v2/jobs/" + d["base"].replace("/", "/images/"))
    assert img.status_code == 200 and Image.open(BytesIO(img.content)).size == (64, 48)
    assert all(j["job_id"] != d["base"].split("/")[0] for j in api.get("/api/v2/jobs").json())
    assert api.post("/api/v2/infographics/upload", json={"b64": "bm90IGFuIGltYWdl"}).status_code == 400
    assert d["ai_note"].startswith("Ilustrace: AI")   # a picture from outside may be generated, the footer stays careful


def test_library_upload_shows_in_the_job_list_with_its_origin(api):
    from base64 import b64encode

    buf = BytesIO()
    Image.new("RGB", (64, 96), (20, 50, 110)).save(buf, "PNG")
    r = api.post("/api/v2/library/upload", json={"b64": b64encode(buf.getvalue()).decode(), "name": "plakat.png",
                                                 "title": "Pantheon", "blender_render": True})
    assert r.status_code == 201, r.text
    job = next(j for j in api.get("/api/v2/jobs").json() if j["job_id"] == r.json()["job_id"])
    assert job["status"] == "done" and len(job["images"]) == 1 and job["request"]["prompt"] == "Pantheon"
    prov = api.get("/api/v2/jobs/" + r.json()["ref"].replace("/", "/images/") + "/provenance").json()
    assert prov["ai_generated"] is False and prov["render"] == "Blender"
    # the history panel reads these right after the upload; one missing key blanked the whole Studio on 1 Nov
    assert prov["backend"] == "Blender" and prov["cost_usd"] == 0 and prov["params"]["size"] == "64x96"
    assert prov["refs"] == [] and prov["timing_s"]["generate"] is None and prov["prompt_sent"] == "Pantheon"
    assert api.get("/api/v2/infographics").json() == []   # a picture for the library is not a document to edit
    assert api.post("/api/v2/library/upload", json={"b64": "bm90IGFuIGltYWdl"}).status_code == 400


def _upload(api, route, size, **extra):
    from base64 import b64encode

    buf = BytesIO()
    Image.new("RGB", size, (20, 50, 110)).save(buf, "PNG")
    return api.post(route, json={"b64": b64encode(buf.getvalue()).decode(), "name": "plakat.png", **extra})


def test_new_document_keeps_the_whole_picture(api):
    # a 2:3 poster opened as 16:9 lost two thirds of the page, in the editor and in VectorCraft (operator 1 Nov)
    route = "/api/v2/infographics/upload"
    doc = _upload(api, route, (1600, 2400)).json()
    assert doc["size"] == "1600x2400"
    assert _upload(api, route, (1344, 768)).json()["size"] == "1920x1080"   # within 3 %: the preset, as before
    assert _upload(api, route, (800, 1000)).json()["size"] == "1080x1350"
    assert _upload(api, route, (64, 96)).json()["size"] == "1080x1620"
    r = api.post(f"/api/v2/infographics/{doc['id']}/export", json={"svg": SVG.format(note=doc["ai_note"]), "format": "png"})
    assert r.status_code == 201, r.text
    assert Image.open(BytesIO(api.get(r.json()["url"]).content)).size == (1600, 2400)
    assert api.put(f"/api/v2/infographics/{doc['id']}", json={**doc, "size": "obrovsky"}).status_code == 400


def test_pdf_has_one_page_for_a_tall_canvas():
    pdf = rasterize('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600"><rect width="400" height="600"/></svg>', 400, 600, "pdf")
    assert pdf.startswith(b"%PDF") and pdf.count(b"/MediaBox") == 1


def test_picture_with_layers_opens_whole_in_the_window(api, settings, vc_window):
    layered = ('<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="2400" viewBox="0 0 1600 2400">'
               '<g id="Grafika"><rect width="1600" height="2400"/></g><g id="Texty"><text x="9" y="9">Pantheon</text></g></svg>')
    ref = _upload(api, "/api/v2/library/upload", (64, 96), title="Plakát", blender_render=True, svg=layered).json()["ref"]
    base = "/api/v2/jobs/" + ref.replace("/", "/images/")
    assert api.get(base + "/provenance").json()["vectorcraft_svg"] == "image-0.svg"
    first = api.post(base + "/vectorcraft", json={})
    assert first.status_code == 200, first.text
    copy = vc_window[0]
    text = copy.read_text(encoding="utf-8")
    assert 'viewBox="0 0 1600 2400"' in text and 'id="Grafika"' in text and 'id="Texty"' in text
    assert api.post(base + "/vectorcraft", json={}).json() == {**first.json(), "created": False}
    copy.write_text(text + "<!-- ruční úprava -->", encoding="utf-8")
    assert api.post(base + "/vectorcraft", json={}).status_code == 409
    assert api.post(base + "/vectorcraft", json={"mode": "edited"}).json()["opened"] == copy.name
    assert api.post(base + "/vectorcraft", json={"mode": "new"}).json()["opened"] != copy.name
    assert copy.read_text(encoding="utf-8").endswith("<!-- ruční úprava -->")
    plain = _upload(api, "/api/v2/library/upload", (64, 96)).json()["ref"]
    assert api.post("/api/v2/jobs/" + plain.replace("/", "/images/") + "/vectorcraft", json={}).status_code == 404
    assert _upload(api, "/api/v2/library/upload", (64, 96), svg="<html/>").status_code == 400


def test_blender_render_is_not_labelled_as_ai(api, settings):
    from base64 import b64encode

    buf = BytesIO()
    Image.new("RGB", (64, 48), (20, 50, 110)).save(buf, "PNG")
    doc = api.post("/api/v2/infographics/upload", json={"b64": b64encode(buf.getvalue()).decode(), "name": "rez.png",
                                                        "blender_render": True}).json()
    assert doc["ai_note"] == "Model a render: Blender, bez AI; schéma a popisky redakčně."
    r = api.post(f"/api/v2/infographics/{doc['id']}/export", json={"svg": SVG.format(note=doc["ai_note"]), "format": "svg"})
    assert r.status_code == 201, r.text
    prov = json.loads(next((settings.library_dir / "infographics" / doc["id"] / "exports").glob("*.svg.json")).read_text(encoding="utf-8"))
    assert prov["ai_generated"] is False and prov["base_provenance"]["render"] == "Blender"


def test_export_goes_to_the_library_once_with_its_origin(api, settings, monkeypatch):
    from base64 import b64encode

    from engine import infographics as ig

    buf = BytesIO()
    Image.new("RGB", (64, 48), (20, 50, 110)).save(buf, "PNG")
    monkeypatch.setattr(ig, "rasterize", lambda svg, w, h, fmt: buf.getvalue())

    def export(doc):
        r = api.post(f"/api/v2/infographics/{doc['id']}/export", json={"svg": SVG.format(note=doc["ai_note"]), "format": "png"})
        assert r.status_code == 201, r.text
        return r.json()["file"]

    # a picture from outside: the footer says AI, so the copy in the Knihovna tab says it too
    doc = api.post("/api/v2/infographics/upload", json={"b64": b64encode(buf.getvalue()).decode(), "name": "mapa.png"}).json()
    name = export(doc)
    first = api.post(f"/api/v2/infographics/{doc['id']}/exports/{name}/library", json={})
    assert first.status_code == 201 and first.json()["created"] is True, first.text
    ref = first.json()["ref"]
    prov = api.get("/api/v2/jobs/" + ref.replace("/", "/images/") + "/provenance").json()
    assert prov["ai_generated"] is True and prov["infographic"] == doc["id"] and prov["params"]["size"] == "64x48"
    assert any(j["job_id"] == ref.split("/")[0] for j in api.get("/api/v2/jobs").json())
    assert api.get(f"/api/v2/infographics/{doc['id']}").json()["in_library"] == {name: ref}

    again = api.post(f"/api/v2/infographics/{doc['id']}/exports/{name}/library", json={})
    assert again.json() == {"ref": ref, "created": False}
    # saving the document from the Studio sends in_library back; it stays derived from the files
    saved = api.put(f"/api/v2/infographics/{doc['id']}", json={**api.get(f"/api/v2/infographics/{doc['id']}").json(), "in_library": {}})
    assert saved.json()["in_library"] == {name: ref}

    # a Blender render stays without the AI label
    doc2 = api.post("/api/v2/infographics/upload", json={"b64": b64encode(buf.getvalue()).decode(), "name": "rez.png",
                                                         "blender_render": True}).json()
    ref2 = api.post(f"/api/v2/infographics/{doc2['id']}/exports/{export(doc2)}/library", json={}).json()["ref"]
    prov2 = api.get("/api/v2/jobs/" + ref2.replace("/", "/images/") + "/provenance").json()
    assert prov2["ai_generated"] is False and prov2["render"] == "Blender" and prov2["backend"] == "Blender"

    assert api.post(f"/api/v2/infographics/{doc['id']}/exports/neni.png/library", json={}).status_code == 404


def test_clean_svg_drops_scripts_handlers_and_external_links():
    dirty = ('<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(2)</script>'
             '<a href="https://evil.example"><rect onclick="x()" width="1" height="1"/></a>'
             '<use href="#r"/><image href="data:image/png;base64,AAAA"/><foreignObject><div/></foreignObject></svg>')
    out = clean_svg(dirty)
    assert "script" not in out and "onload" not in out and "onclick" not in out and "evil" not in out
    assert "foreignObject" not in out and 'href="#r"' in out and "data:image" not in out
    assert "data:image/png" in clean_svg(dirty, allow_data_images=True)
    svg_uri = '<svg xmlns="http://www.w3.org/2000/svg"><image href="data:image/svg+xml;base64,AAAA"/></svg>'
    assert "data:image" not in clean_svg(svg_uri, allow_data_images=True)   # only raster data URIs
    with pytest.raises(InfoError):
        clean_svg("<html/>")


def test_ai_note_from_provenance():
    assert ai_note({"backend": "flux-local", "refs": [{"sent_as": "image"}]}) == \
        "Ilustrace: FLUX 3 Klein (AI) podle předlohy, schéma a popisky redakčně."
    assert ai_note({"backend": "flux-local", "refs": []}).startswith("Ilustrace: FLUX 3 Klein (AI), ")
    # fal backends get the product name, not the endpoint path (model: "fal-ai/nano-banana-pro/edit")
    assert ai_note({"backend": "fal:fal-ai/nano-banana-pro", "model": "fal-ai/nano-banana-pro/edit", "refs": []}) \
        .startswith("Ilustrace: Nano Banana Pro (AI), ")


def test_infographic_document_lifecycle(api, settings):
    base = _first_image(api)
    ref = f"{base['job_id']}/0"
    assert api.post("/api/v2/infographics", json={"base": "nope-1/0"}).status_code == 404
    doc = api.post("/api/v2/infographics", json={"base": ref, "title": "Římská kvinquerema"}).json()
    assert doc["ai_note"].startswith("Ilustrace: FLUX 3 Klein (AI)") and doc["size"] == "1080x540"   # the whole 2:1 test picture
    assert doc["layout"] == "pruh"   # new documents: image over the whole canvas, facts in a bar
    labels = [{"text": "Corvus", "small": "sklopný most", "anchor": [210, 540], "pos": [120, 296]}]
    doc = api.put(f"/api/v2/infographics/{doc['id']}", json={**doc, "labels": labels, "ai_note": "smazáno",
                                                              "schema": {"title": "Řez", "svg": '<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>'}}).json()
    assert doc["labels"][0]["text"] == "Corvus" and doc["ai_note"].startswith("Ilustrace:")  # AI label stays
    assert "script" not in doc["schema"]["svg"]
    raster = '<svg xmlns="http://www.w3.org/2000/svg"><image href="data:image/jpeg;base64,AAAA"/></svg>'
    doc = api.put(f"/api/v2/infographics/{doc['id']}", json={**doc, "schema": {"title": "Řez", "svg": raster}}).json()
    assert "data:image/jpeg" in doc["schema"]["svg"]   # a raster cross-section may sit in the schema box
    assert api.put(f"/api/v2/infographics/{doc['id']}", json={**doc, "size": "5x5"}).status_code == 400
    assert api.put(f"/api/v2/infographics/{doc['id']}", json={**doc, "layout": "mozaika"}).status_code == 400
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
    assert Image.open(BytesIO(out["png"].content)).size == (1080, 540)   # the document keeps the shape of its picture
    assert out["pdf"].content.startswith(b"%PDF") and "Římská" in out["svg"].text
    ex = settings.library_dir / "infographics" / doc["id"] / "exports"
    prov = json.loads(next(ex.glob("*.png.json")).read_text(encoding="utf-8"))
    assert prov["ai_generated"] is True and prov["base"] == f"{base['job_id']}/0" and prov["base_provenance"]["backend"] == "flux-local"
    assert len(api.get(f"/api/v2/infographics/{doc['id']}").json()["exports"]) == 3
    assert api.post(f"/api/v2/infographics/{doc['id']}/export", json={"svg": svg, "format": "gif"}).status_code == 400


@pytest.fixture
def vc_window(monkeypatch, tmp_path):
    """Records instead of starting the window app (the real one is checked by hand, docs/spikes/2026-10-31-vectorcraft-okno.md)."""
    opened = []
    app_path = tmp_path / "vectorcraft.exe"
    monkeypatch.setattr("engine.app.find_desktop_app", lambda: app_path)
    monkeypatch.setattr("engine.app.open_in_window", lambda app, path: opened.append(path))
    return opened


def _info_with_note(api):
    base = _first_image(api)
    doc = api.post("/api/v2/infographics", json={"base": f"{base['job_id']}/0", "title": "Test"}).json()
    return doc, SVG.format(note=doc["ai_note"]), f"/api/v2/infographics/{doc['id']}/vectorcraft"


def test_vectorcraft_opens_a_saved_copy_and_reuses_it_while_unchanged(api, settings, vc_window):
    doc, svg, url = _info_with_note(api)
    assert api.get(url).json() == {"available": True, "edits": []}
    r = api.post(url, json={"svg": svg})
    assert r.status_code == 200 and r.json()["created"] is True
    path = settings.library_dir / "infographics" / doc["id"] / "vectorcraft" / r.json()["opened"]
    assert "Římská" in path.read_text(encoding="utf-8")
    assert vc_window == [path]
    again = api.post(url, json={"svg": svg}).json()
    assert again["opened"] == r.json()["opened"] and again["created"] is False and len(vc_window) == 2
    changed = api.post(url, json={"svg": svg.replace("Římská", "Řecká")}).json()
    assert changed["opened"] != r.json()["opened"] and "Římská" in path.read_text(encoding="utf-8")   # older copy untouched


def test_vectorcraft_never_overwrites_a_manual_edit(api, settings, vc_window):
    doc, svg, url = _info_with_note(api)
    first = api.post(url, json={"svg": svg}).json()
    d = settings.library_dir / "infographics" / doc["id"] / "vectorcraft"
    (d / first["opened"]).write_text("<svg>ruční úprava</svg>", encoding="utf-8")
    assert api.get(url).json()["edits"][0]["file"] == first["opened"]
    conflict = api.post(url, json={"svg": svg})
    assert conflict.status_code == 409 and conflict.json()["edited"] == first["opened"] and "nepřepíše" in conflict.json()["detail"]
    assert len(vc_window) == 1   # the question comes first, nothing opens
    assert api.post(url, json={"svg": svg, "mode": "edited"}).json()["opened"] == first["opened"]
    new = api.post(url, json={"svg": svg, "mode": "new"}).json()
    assert new["opened"] != first["opened"] and new["created"] is True
    assert (d / first["opened"]).read_text(encoding="utf-8") == "<svg>ruční úprava</svg>"
    (d / "kopie.vectorcraft").write_text("{}", encoding="utf-8")   # Save As next to the copies counts too
    assert api.post(url, json={"svg": svg, "mode": "edited"}).json()["opened"] == "kopie.vectorcraft"


def test_vectorcraft_refusals_are_in_czech_and_open_nothing(api, vc_window, monkeypatch):
    doc, svg, url = _info_with_note(api)
    assert api.post(url, json={"svg": SVG.format(note="")}).status_code == 400   # AI label required, same as export
    assert api.post(url, json={"svg": svg, "mode": "edited"}).status_code == 400   # no manual edit yet
    assert api.post(url, json={"svg": svg, "mode": "pozdeji"}).status_code == 400
    assert api.post("/api/v2/infographics/neni/vectorcraft", json={"svg": svg}).status_code == 404
    monkeypatch.setattr("engine.app.find_desktop_app", lambda: None)
    assert api.get(url).json()["available"] is False
    missing = api.post(url, json={"svg": svg})
    assert missing.status_code == 503 and "není nainstalovaná" in missing.json()["detail"]
    assert vc_window == []


class FakeVectorCraft:
    """Headless session: exports what the file says. The real app: test below, GRAFIK_VECTORCRAFT_TESTS=1."""
    seen: list = []
    server = {"version": "test"}

    def __init__(self, **kw):
        type(self).seen.append(kw)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def tool(self, name, path=None, **kw):
        if name == "open_file":
            self.text = Path(path).read_text(encoding="utf-8")
            return {"warnings": ["jedno varování"], "missingLinks": []}
        if name == "inspect_document":
            # data-v / data-y in the test file stand for what a person does to a text in the window
            kids = [{"kind": "Type", "text": t, "visible": "hidden" not in a,
                     "bounds": {"x": 40, "y": 2000 if "off" in a else 60, "width": 500, "height": 20}}
                    for a, t in re.findall(r"<text([^>]*)>([^<]*)</text>", self.text)]
            return {"artboards": [{"x": 0, "y": 0, "width": 1280, "height": 990}],
                    "layers": [{"kind": "Layer", "visible": True, "children": kids[::-1]}]}
        p = Path(path)
        if p.suffix == ".png":
            Image.new("RGB", (1920, 1080), (9, 9, 9)).save(p)
        elif p.suffix == ".pdf":
            p.write_bytes(b"%PDF-fake")
        else:
            p.write_text("<svg xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M0 0\"/></svg>", encoding="utf-8")
        return {"warnings": []}


@pytest.fixture
def edited(api, settings, vc_window, monkeypatch):
    FakeVectorCraft.seen = []
    monkeypatch.setattr("engine.infographics.VectorCraft", FakeVectorCraft)
    monkeypatch.setattr("engine.app.find_cli", lambda: Path("vectorcraft-cli.exe"))
    doc, svg, url = _info_with_note(api)
    first = api.post(url, json={"svg": svg}).json()
    d = settings.library_dir / "infographics" / doc["id"] / "vectorcraft"
    return doc, svg, url, d / first["opened"]


def test_manual_edit_becomes_new_exports_with_provenance(api, settings, edited):
    doc, svg, url, copy = edited
    # an untouched copy is not an edit, there is nothing to take over
    none = api.post(f"{url}/export", json={})
    assert none.status_code == 400 and "uložte" in none.json()["detail"]
    older = api.post(f"/api/v2/infographics/{doc['id']}/export", json={"svg": svg, "format": "png"}).json()
    ex = settings.library_dir / "infographics" / doc["id"] / "exports"
    older_bytes = (ex / older["file"]).read_bytes()
    text = svg.replace("Římská kvinquerema", "Řecká triéra")
    copy.write_text(text, encoding="utf-8")
    assert api.get(url).json()["edits"] == [{"file": copy.name, "modified": api.get(url).json()["edits"][0]["modified"], "can_export": True, "exported": None}]

    r = api.post(f"{url}/export", json={})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["source"] == copy.name and [f["format"] for f in out["files"]] == ["png", "svg", "pdf"]
    assert out["warnings"] == ["jedno varování"]
    png = api.get(out["files"][0]["url"])
    assert png.status_code == 200 and Image.open(BytesIO(png.content)).size == (1920, 1080)
    assert api.get(out["files"][2]["url"]).content.startswith(b"%PDF")
    kw = FakeVectorCraft.seen[0]
    # its own lock owner: the Engine's owner would count as already holding the lock while a FLUX job runs
    assert kw["lock_owner"] != "grafik-engine" and kw["lock_path"] == settings.gpu_lock_path

    prov = json.loads((ex / f"{out['files'][0]['file']}.json").read_text(encoding="utf-8"))
    assert prov["manual_edit"]["file"] == copy.name and prov["manual_edit"]["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert prov["ai_generated"] is True and prov["ai_note"] == doc["ai_note"] and prov["ai_note_checked"] is True
    assert prov["base"] == doc["base"] and prov["base_provenance"]["backend"] == "flux-local"
    assert "Řecká triéra" in prov["texts"] and "labels" not in prov   # what the file says, not the editor's fields
    assert prov["reviewed_by"] is None and prov["manual_edit"]["vectorcraft"] == "test"

    # nothing overwritten: the source, the older export; a second take-over adds new files
    assert copy.read_text(encoding="utf-8") == text and (ex / older["file"]).read_bytes() == older_bytes
    assert api.get(url).json()["edits"][0]["exported"] == out["files"][0]["file"]
    again = api.post(f"{url}/export", json={"file": copy.name}).json()
    assert {f["file"] for f in again["files"]}.isdisjoint(f["file"] for f in out["files"])
    assert len(api.get(f"/api/v2/infographics/{doc['id']}").json()["exports"]) == 7


def test_manual_edit_without_the_ai_label_saves_nothing(api, settings, edited):
    doc, _svg, url, copy = edited
    note = doc["ai_note"]
    sources = (SVG.format(note="Ilustrace: redakce."),                                       # reworded
               SVG.format(note=note).replace('y="980"', 'y="980" data-v="hidden"'),          # hidden layer or object
               SVG.format(note=note).replace('y="980"', 'y="980" data-y="off"'))             # moved off the canvas
    for text in sources:
        copy.write_text(text, encoding="utf-8")
        r = api.post(f"{url}/export", json={})
        assert r.status_code == 400 and "označení AI" in r.json()["detail"] and note in r.json()["detail"]
        assert api.get(f"/api/v2/infographics/{doc['id']}").json()["exports"] == []


def test_manual_export_refusals(api, settings, edited, monkeypatch):
    doc, svg, url, copy = edited
    copy.write_text(svg + " ", encoding="utf-8")
    (copy.parent / "pohled.png").write_bytes(b"png")   # exported from the window next to the copies: not a document
    states = {e["file"]: e["can_export"] for e in api.get(url).json()["edits"]}
    assert states == {copy.name: True, "pohled.png": False}
    assert api.post(f"{url}/export", json={"file": "pohled.png"}).status_code == 400
    assert api.post(f"{url}/export", json={"file": "../info.json"}).status_code == 400
    assert api.post("/api/v2/infographics/neni/vectorcraft/export", json={}).status_code == 404

    class Busy(FakeVectorCraft):
        def __init__(self, **kw):
            raise HeavyBusy("Stroj je obsazený těžkou prací (gpu pro grafik-engine).")

    class Broken(FakeVectorCraft):
        def tool(self, name, **kw):
            raise VectorCraftError("spadl")

    class Missing(FakeVectorCraft):
        def tool(self, name, **kw):
            return {"missingLinks": ["obraz.png"], "warnings": []}

    for cls, code, word in ((Busy, 503, "za chvíli"), (Broken, 502, "spadl"), (Missing, 400, "obraz.png")):
        monkeypatch.setattr("engine.infographics.VectorCraft", cls)
        r = api.post(f"{url}/export", json={})
        assert r.status_code == code and word in r.json()["detail"]
    monkeypatch.setattr("engine.app.find_cli", lambda: None)
    assert api.post(f"{url}/export", json={}).status_code == 503
    assert api.get(f"/api/v2/infographics/{doc['id']}").json()["exports"] == []


@pytest.mark.skipif(not os.environ.get("GRAFIK_VECTORCRAFT_TESTS"), reason="skutečný VectorCraft, GRAFIK_VECTORCRAFT_TESTS=1")
def test_manual_export_with_the_real_vectorcraft(api, settings, vc_window, monkeypatch):
    from ngm_shared.textlayer.vc_client import VectorCraft
    doc, svg, url = _info_with_note(api)
    first = api.post(url, json={"svg": svg}).json()
    copy = settings.library_dir / "infographics" / doc["id"] / "vectorcraft" / first["opened"]
    with VectorCraft(lock_owner="grafik-test", lock_path=settings.gpu_lock_path) as vc:   # same steps as a person in the window
        vc.tool("open_file", path=str(copy))
        target = next(c for c in vc.tool("inspect_document")["layers"][0]["children"] if c.get("text") == "Římská kvinquerema")
        vc.cmd("text.setText", id=target["id"], text="Řecká triéra")
        vc.tool("save_file", path=str(copy.with_suffix(".vectorcraft")))
    sha = hashlib.sha256(copy.read_bytes()).hexdigest()
    r = api.post(f"{url}/export", json={"file": copy.with_suffix(".vectorcraft").name})
    assert r.status_code == 201, r.text
    assert hashlib.sha256(copy.read_bytes()).hexdigest() == sha
    assert Image.open(BytesIO(api.get(r.json()["files"][0]["url"]).content)).size == (1280, 990)
    ex = settings.library_dir / "infographics" / doc["id"] / "exports"
    prov = json.loads(next(ex.glob("*-rucni-*.png.json")).read_text(encoding="utf-8"))
    assert "Řecká triéra" in prov["texts"] and prov["size"] == "1280x990"
    assert "<text" not in api.get(r.json()["files"][1]["url"]).text   # outlined


def test_for_vectorcraft_names_the_condensed_font_with_its_weight():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg"><g font-family="Bahnschrift, sans-serif" font-stretch="semi-condensed">'
           '<text font-weight="700">A</text><text>B<tspan font-weight="700">C</tspan></text></g>'
           '<text font-family="Segoe UI, sans-serif" font-weight="700">D</text></svg>')
    out = for_vectorcraft(svg)
    assert out.count('font-family="Bahnschrift Bold SemiCondensed"') == 2
    assert out.count('font-family="Bahnschrift SemiCondensed"') == 1
    assert 'font-family="Segoe UI, sans-serif"' in out   # other fonts stay as they are


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
