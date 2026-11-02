"""Dokument s panely (krok 3c): API, vykreslení po vrstvách, kontroly, export. Rendery jsou malé obrázky, Blender tu neběží."""
from __future__ import annotations

import base64
import json
import re
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from engine import panels
from engine.infographics import InfoError
from tests.test_models3d import api, settings, trace, upload, wait  # noqa: F401  (fixtures)
from tests.test_parts3d import SPEC, built, model, render, versions  # noqa: F401

REPO = Path(__file__).resolve().parents[1]
SVG = "{http://www.w3.org/2000/svg}"
BODY = {"res": [200, 100], "points": {"vez": [100, 50]}, "viditelne": ["vez"], "origin": [100, 50], "basis": {"x": [2, 0], "y": [0, 1], "z": [0, -2]}, "kruh": [[10, 10], [20, 10], [20, 20]], "dim": {}}


def shot(folder: Path, layers=()) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (200, 100), (200, 180, 150, 255)).save(folder / "obraz.png")
    (folder / "body.json").write_text(json.dumps(BODY), encoding="utf-8")
    for name in layers:
        im = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
        im.paste((90, 90, 90, 255), (20, 20, 80, 80))
        im.save(folder / f"vrstva-{name}.png")


def label(text="Věž", kotva="vez", **over) -> dict:
    return {"text": text, "small": "z kamene", "kotva": kotva, "pos": [760, 200], "align": "left", **over}


def fields(**over) -> dict:
    return {"title": "Věž", "subtitle": "první řádek\ndruhý", "size": "1600x2400", "sources": "Wikipedie", "pismo": "plakat", "panels": [
        {"id": "hlavni", "typ": "obraz", "poradi": 1, "nazev": "Hlavní", "rect": [0, 100, 800, 400], "zdroj": {"slozka": "strely/hlavni"}, "vrstvy": {"zed": "Zeď"}, "labels": [label()],
         "prekryvy": [{"typ": "krivka", "body": "kruh"}, {"typ": "usecka", "od": "vez", "do": [1, 1, 1]}]},
        {"id": "detail", "typ": "obraz", "poradi": 3, "rect": [0, 600, 400, 200], "zdroj": {"slozka": "strely/detail"}, "titulek": "Detail", "pod": {"text": "Popis", "small": "drobně"}},
        {"id": "cisla", "typ": "fakta", "poradi": 2, "rect": [50, 900, 700, 100], "items": [{"value": "12 m", "text": "výška"}], "fakta": ["f1"]},
        {"id": "sloupec", "typ": "fakta", "poradi": 5, "rect": [50, 1100, 700, 100], "smer": "sloupec", "items": [{"value": "12 m", "text": "výška"}, {"value": "3 t", "text": "váha"}]},
        {"id": "proc", "typ": "text", "poradi": 4, "rect": [50, 1300, 700, 200], "titulek": {"text": "Proč", "x": 50, "y": 1290}, "items": [{"value": "Lehčí", "text": "beton < nahoře"}]},
        {"id": "osa", "typ": "osa", "poradi": 6, "rect": [50, 1600, 700, 200], "items": [{"value": "80", "text": "otevření"}, {"value": "217", "text": "požár"}]},
        {"id": "plan", "typ": "kresba", "poradi": 7, "rect": [800, 900, 200, 200], "kresba": '<rect width="10" height="10" onclick="x()"/><script>alert(1)</script>', "texty": '<text x="1" y="1">řez</text>'},
    ], **over}


@pytest.fixture
def doc(api, settings):
    shot(settings.library_dir / "strely" / "hlavni", ["zed"])
    shot(settings.library_dir / "strely" / "detail")
    r = api.post("/api/v2/infographics/panels", json=fields())
    assert r.status_code == 201, r.text
    return r.json()


def test_panel_document_copies_renders_and_says_blender(api, settings, doc):
    assert doc["schema_version"] == 2 and doc["size"] == "1600x2400" and doc["ai_note"].startswith("Model a render: Blender")
    assert "/" in doc["base"]
    folder = settings.library_dir / "infographics" / doc["id"] / "panely" / "hlavni"
    assert (folder / "obraz.png").is_file() and (folder / "body.json").is_file() and (folder / "vrstva-zed.png").is_file()
    # pozdější render zdroje dokument nezmění
    Image.new("RGBA", (200, 100), (0, 0, 0, 255)).save(settings.library_dir / "strely" / "hlavni" / "obraz.png")
    assert Image.open(folder / "obraz.png").getpixel((5, 5))[0] == 200


def test_old_documents_stay_as_they_are_and_list_hides_panels_for_now(api, settings, doc):
    r = api.get("/api/v2/infographics")
    assert doc["id"] not in [d["id"] for d in r.json()]
    assert doc["id"] in [d["id"] for d in api.get("/api/v2/infographics?panely=true").json()]
    assert api.get(f"/api/v2/infographics/{doc['id']}").json()["panels"][0]["id"] == "hlavni"
    # dokument bez schema_version: žádný panel, žádná kontrola panelů, náhled kreslí Studio
    buf = BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, "PNG")
    old = api.post("/api/v2/infographics/upload", json={"b64": base64.b64encode(buf.getvalue()).decode(), "name": "a.png"}).json()
    assert "schema_version" not in old and "panels" not in old
    assert api.get(f"/api/v2/infographics/{old['id']}/svg").status_code == 404
    assert api.get(f"/api/v2/infographics/{old['id']}/kontrola").status_code == 404
    assert api.post(f"/api/v2/infographics/{old['id']}/export", json={"format": "svg"}).status_code == 400   # staré SVG posílá Studio


def groups(root, parent: str) -> list[str]:
    layer = next(g for g in root if g.get("id") == parent)
    return [g.get("id") for g in layer]


def test_svg_has_layers_for_vectorcraft_and_preview_links_pictures(api, doc):
    r = api.get(f"/api/v2/infographics/{doc['id']}/svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")
    root = ET.fromstring(r.text)
    assert [g.get("id") for g in root] == ["Grafika", "Texty"]
    assert {"Pozadí", "Hlavní", "Vodítka Hlavní", "Překryv Hlavní", "detail", "Osa osa", "plan"} <= set(groups(root, "Grafika"))
    assert {"Nadpis", "Popisky Hlavní", "Nadpis Detail", "Popisek detail", "cisla", "Patička"} <= set(groups(root, "Texty"))
    assert "<script" not in r.text and "onclick" not in r.text and "beton &lt; nahoře" in r.text
    assert "data:image" not in r.text
    links = re.findall(r'href="(/api/v2/infographics/[^"]+)"', r.text)
    assert len(links) == 2 and all(api.get(u).status_code == 200 for u in links)    # vrstva zdi a sloučený detail


def test_label_sits_on_the_point_of_the_model(tmp_path):
    place = panels.placement({"rect": [100, 200, 400, 200]}, BODY)
    assert place["k"] == 2.0 and (place["x"], place["y"]) == (100.0, 200.0)      # celý obraz, bez ořezu
    assert panels.to_page(place, "vez") == (300.0, 300.0)
    assert panels.to_page(place, [1, 0, 1]) == (304.0, 296.0)      # bod v metrech přes origin a basis
    with pytest.raises(InfoError, match="neni"):
        panels.to_page(place, "neni", "hlavni")
    wide = panels.placement({"rect": [0, 0, 400, 400]}, BODY)
    assert wide["k"] == 2.0 and wide["y"] == 100.0      # na střed rámce


def test_elbow_leader_goes_vertical_then_horizontal():
    place = {"x": 0, "y": 0, "k": 1, "info": BODY}
    assert panels.leader_points({"kotva": "vez", "pos": [200, 10], "align": "left"}, place, 20) == [(100, 50), (100, 24.4), (192, 24.4)]
    assert panels.leader_points({"kotva": "vez", "pos": [200, 36], "align": "left"}, place, 20) == [(100, 50), (192, 50.4)]


def test_export_png_svg_pdf_with_provenance_and_knihovna(api, settings, doc):
    d = settings.library_dir / "infographics" / doc["id"] / "exports"
    for fmt in ("png", "svg", "pdf"):
        r = api.post(f"/api/v2/infographics/{doc['id']}/export", json={"format": fmt})
        assert r.status_code == 201, r.text
    png = next(p for p in d.glob("*.png"))
    assert Image.open(png).size == (1600, 2400)
    prov = json.loads(png.with_name(f"{png.name}.json").read_text(encoding="utf-8"))
    assert prov["ai_generated"] is False and prov["panels"][0]["labels"][0]["text"] == "Věž" and prov["panels"][2]["fakta"] == ["f1"]
    assert (d / f"{png.name}.vrstvy").is_file() and all(not n.endswith(".vrstvy") for n in api.get(f"/api/v2/infographics/{doc['id']}").json()["exports"])
    svg = next(p for p in d.glob("*.svg")).read_text(encoding="utf-8")
    assert "data:image/png" in svg and "<script" not in svg and doc["ai_note"].split(",")[0] in svg
    lib = api.post(f"/api/v2/infographics/{doc['id']}/exports/{png.name}/library")
    assert lib.status_code == 201 and lib.json()["created"] is True
    job_id = lib.json()["ref"].split("/")[0]
    files = api.get(f"/api/v2/jobs/{job_id}").json()["result"]["files"]
    assert Path(files[0]).with_suffix(".svg").is_file()     # v Knihovně jde otevřít po vrstvách


def test_vectorcraft_copy_is_drawn_by_the_engine(api, settings, doc, monkeypatch):
    import engine.app as app_module
    opened = []
    monkeypatch.setattr(app_module, "find_desktop_app", lambda: Path("vectorcraft.exe"))
    monkeypatch.setattr(app_module, "open_in_window", lambda app, path: opened.append(path))
    r = api.post(f"/api/v2/infographics/{doc['id']}/vectorcraft", json={})
    assert r.status_code == 200, r.text
    text = opened[0].read_text(encoding="utf-8")
    assert 'id="Grafika"' in text and 'id="Texty"' in text and "data:image/png" in text and "Bahnschrift" in text


def test_save_keeps_the_panels_valid(api, doc):
    changed = {**doc, "title": "Jiná věž", "panels": [{**doc["panels"][0], "labels": [label("Nová")]}, *doc["panels"][1:]]}
    r = api.put(f"/api/v2/infographics/{doc['id']}", json=changed)
    assert r.status_code == 200 and r.json()["panels"][0]["labels"][0]["text"] == "Nová" and r.json()["schema_version"] == 2
    bad = {**doc, "panels": [{**doc["panels"][0], "rect": [0, 0, 9000, 10]}]}
    r = api.put(f"/api/v2/infographics/{doc['id']}", json=bad)
    assert r.status_code == 400 and "mimo plátno" in r.json()["detail"]
    assert api.put(f"/api/v2/infographics/{doc['id']}", json={**doc, "schema_version": 3}).status_code == 400


@pytest.mark.parametrize("panel, message", [
    ({"id": "../x", "typ": "obraz", "rect": [0, 0, 10, 10]}, "malá písmena"),
    ({"id": "a", "typ": "video", "rect": [0, 0, 10, 10]}, "typ je"),
    ({"id": "a", "typ": "obraz", "rect": [0, 0, 10]}, "4 čísla"),
    ({"id": "a", "typ": "obraz", "rect": [0, 0, 2000, 10]}, "mimo plátno"),
    ({"id": "a", "typ": "obraz", "rect": [0, 0, 10, 10], "labels": [{"small": "x"}]}, "potřebuje text"),
    ({"id": "a", "typ": "obraz", "rect": [0, 0, 10, 10], "labels": [label(kotva=[1, 2])]}, "3 čísla"),
    ({"id": "a", "typ": "obraz", "rect": [0, 0, 10, 10], "labels": [label(align="stred")]}, "align"),
    ({"id": "a", "typ": "obraz", "rect": [0, 0, 10, 10], "vrstvy": {"../x": "y"}}, "vrstvy"),
    ({"id": "a", "typ": "obraz", "rect": [0, 0, 10, 10], "prekryvy": [{"typ": "kruh"}]}, "překryv"),
    ({"id": "a", "typ": "fakta", "rect": [0, 0, 10, 10]}, "položky"),
    ({"id": "a", "typ": "fakta", "rect": [0, 0, 10, 10], "items": [{}]}, "value nebo text"),
    ({"id": "a", "typ": "fakta", "rect": [0, 0, 10, 10], "items": [{"value": "1"}], "smer": "kolem"}, "smer"),
])
def test_bad_panel_says_what_is_wrong(panel, message):
    with pytest.raises(InfoError, match=message):
        panels.validate({"size": "1600x2400", "panels": [panel]})


def test_document_needs_panels_and_a_known_size_and_unique_ids():
    with pytest.raises(InfoError, match="žádné panely"):
        panels.validate({"size": "1600x2400", "panels": []})
    with pytest.raises(InfoError, match="formát"):
        panels.validate({"size": "abc", "panels": [{}]})
    same = {"id": "a", "typ": "obraz", "rect": [0, 0, 10, 10]}
    with pytest.raises(InfoError, match="opakuje"):
        panels.validate({"size": "1600x2400", "panels": [same, same]})


def test_broken_source_leaves_no_half_document(api, settings):
    shot(settings.library_dir / "strely" / "hlavni", ["zed"])
    r = api.post("/api/v2/infographics/panels", json=fields())     # detail chybí
    assert r.status_code == 400 and "body.json" in r.json()["detail"]
    assert not [p for p in (settings.library_dir / "infographics").glob("*") if p.name != ".trash"]
    outside = fields()
    outside["panels"][0]["zdroj"] = {"slozka": "../.."}
    assert api.post("/api/v2/infographics/panels", json=outside).status_code == 400
    missing = fields()
    missing["panels"][0]["zdroj"] = {"model_id": "neni", "version": "v1", "render": "r-1"}
    assert api.post("/api/v2/infographics/panels", json=missing).status_code == 400


def test_checks_warn_on_all_panels(api, settings, doc):
    out = api.get(f"/api/v2/infographics/{doc['id']}/kontrola").json()
    texts = {c["text"]: c["ok"] for c in out}
    assert texts["7 panelů, 1 popisků"] and texts["zdroj vyplněn"] and texts["vodítka se nekříží"] and not texts["před zveřejněním zkontroluje člověk"]
    crossing = {**doc, "panels": [{**doc["panels"][0], "labels": [
        {"text": "A", "small": ["krátce"], "kotva": [-40, 0, 0], "pos": [500, 100], "align": "left"},
        {"text": "B", "small": [], "kotva": [40, 0, 0], "pos": [0, 300], "align": "left"},
        {"text": "C", "small": [], "kotva": "neni", "pos": [1, 1], "align": "left"},
        {"text": "D je příliš dlouhý popisek se spoustou slov navíc", "small": [], "kotva": "vez", "pos": [1590, 450], "align": "left"},
    ]}]}
    texts = {c["text"]: c["ok"] for c in panels.checks(crossing, settings.library_dir / "infographics" / doc["id"])}
    assert not texts["1× se vodítka kříží"] and not texts["popisky míří na neznámý bod: hlavni: C"]
    assert any(t.startswith("mimo plátno") for t in texts) and not texts["1 popisků delších než 40 znaků"]


def test_panel_from_a_model_render_through_the_api(api, settings, built):
    job = wait(api, render(api, pohled="rez", res=[640, 360], samples=16).json()["job_id"])
    assert job["status"] == "done"
    body = {"title": "Věž", "size": "1600x1000", "panels": [{"id": "hlavni", "typ": "obraz", "rect": [0, 0, 1600, 900], "zdroj": {"model_id": "vez", "version": "v1", "render": job["result"]["id"]},
                                                             "labels": [label("Zeď", "zed", pos=[100, 100])]}]}
    r = api.post("/api/v2/infographics/panels", json=body)
    assert r.status_code == 201, r.text
    assert api.get(f"/api/v2/infographics/{r.json()['id']}/svg").status_code == 200


def test_render_frame_on_a_part_of_the_model(api, built):
    job = render(api, zaber=[[-1, -1, 0], [1, 1, 2]])
    assert job.status_code == 202
    assert wait(api, job.json()["job_id"])["status"] == "done"
    for bad in ([[0, 0, 0]], [[0, 0], [1, 1]], [[0, 0, 0], [0, 0, 0]], [[0, 0, 0], [9000, 0, 0]]):
        assert "záběr" in render(api, zaber=bad).json()["detail"]


def test_ai_picture_and_foreign_painting_are_named_in_the_footer(api, settings):
    shot(settings.library_dir / "strely" / "hlavni", ["zed"])
    img = api.post("/api/v2/images", json={"prompt": "a scene", "size": "256x256", "seed": 1}).json()["job_id"]
    assert wait(api, img)["status"] == "done"
    buf = BytesIO()
    Image.new("RGB", (100, 80), "red").save(buf, "PNG")
    ref = api.post("/api/v2/refs", json={"b64": base64.b64encode(buf.getvalue()).decode(), "title": "Obraz", "author": "Gérôme", "license": "Public domain"})
    assert ref.status_code in (200, 201), ref.text
    body = {"title": "Věž", "size": "1600x1000", "pismo": "plakat", "panels": [
        {"id": "hlavni", "typ": "obraz", "nazev": "Model", "rect": [0, 0, 800, 400], "zdroj": {"slozka": "strely/hlavni"}},
        {"id": "scena", "typ": "obraz", "nazev": "Scéna", "rect": [800, 0, 800, 400], "zdroj": {"obraz": f"{img}/0"}, "labels": [label("Vítěz", [10, 20, 0], pos=[900, 100])]},
        {"id": "gerome", "typ": "obraz", "nazev": "Obraz", "rect": [0, 500, 400, 400], "zdroj": {"ref_id": ref.json()["id"], "vyrez": [10, 10, 50, 40]}}]}
    r = api.post("/api/v2/infographics/panels", json=body)
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["ai_note"] == "Model a render: Blender, bez AI; Scéna: FLUX 3 Klein (AI); Obraz: Gérôme, Public domain; schéma a popisky redakčně."
    assert doc["ai_generated"] is True
    root = settings.library_dir / "infographics" / doc["id"]
    assert Image.open(root / "panely" / "gerome" / "obraz.png").size == (50, 40)
    svg = api.get(f"/api/v2/infographics/{doc['id']}/svg").text
    assert "Vítěz" in svg
    assert re.sub(r"\s+", "", doc["ai_note"]) in re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", svg))
    png = api.post(f"/api/v2/infographics/{doc['id']}/export", json={"format": "png"}).json()["file"]
    assert json.loads((root / "exports" / f"{png}.json").read_text(encoding="utf-8"))["ai_generated"] is True
    lib = api.post(f"/api/v2/infographics/{doc['id']}/exports/{png}/library").json()
    picture = Path(api.get(f"/api/v2/jobs/{lib['ref'].split('/')[0]}").json()["result"]["files"][0])
    meta = json.loads(picture.with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["ai_generated"] is True and "render" not in meta       # v Knihovně se nevydává za render bez AI
    assert api.post("/api/v2/infographics/panels", json={**body, "panels": [{**body["panels"][0], "zdroj": {"obraz": "neni/0"}}]}).status_code in (400, 404)


def test_cut_out_removes_only_the_background_around_the_figure():
    pic = Image.new("RGBA", (60, 60), (20, 30, 60, 255))
    for x in range(20, 40):
        for y in range(20, 40):
            pic.putpixel((x, y), (200, 0, 40, 255))             # nulový zelený kanál není pozadí
    pic.putpixel((30, 30), (20, 30, 60, 255))                   # barva pozadí uvnitř postavy zůstane
    alpha = panels.cut_out(pic).getchannel("A")
    assert alpha.getpixel((0, 0)) == 0 and alpha.getpixel((59, 30)) == 0 and alpha.getpixel((19, 19)) == 0
    assert alpha.getpixel((25, 25)) == 255 and alpha.getpixel((30, 30)) == 255
    big = Image.new("RGBA", (120, 120), (20, 30, 60, 255))
    for x in range(20, 100):
        for y in range(20, 100):
            if not (35 <= x < 85 and 35 <= y < 85):
                big.putpixel((x, y), (200, 0, 40, 255))
    assert panels.cut_out(big).getchannel("A").getpixel((60, 60)) == 0      # velká plocha uzavřená postavou je pozadí
    for x in range(0, 20):
        for y in range(25, 35):
            pic.putpixel((x, y), (200, 150, 120, 255))          # předloktí vstupuje z levého okraje a zůstane
    alpha = panels.cut_out(pic).getchannel("A")
    assert alpha.getpixel((0, 30)) == 255 and alpha.getpixel((10, 30)) == 255 and alpha.getpixel((10, 10)) == 0 and alpha.getpixel((59, 30)) == 0


def test_green_screen_keeps_dark_metal_and_drops_the_screen():
    pic = Image.new("RGB", (100, 200), (40, 180, 60))
    for x in range(40, 60):
        for y in range(20, 180):
            pic.putpixel((x, y), (32, 34, 36) if y > 120 else (200, 150, 120))      # tmavý kov na noze, kůže nahoře
    for x in range(30, 80):
        for y in range(180, 188):
            pic.putpixel((x, y), (15, 70, 25))                                      # tmavá zelená ve stínu je pořád plátno
    cut = panels.cut_out(pic.convert("RGBA"))
    assert cut.getpixel((50, 150))[3] == 255 and cut.getpixel((50, 50))[3] == 255
    assert cut.getpixel((90, 50))[3] == 0 and cut.getpixel((70, 184))[3] == 0


def test_shadow_comes_from_the_picture_and_stays_where_it_was():
    pic = Image.new("RGB", (200, 300), (60, 170, 80))
    for xx in range(90, 110):
        for y in range(40, 260):
            pic.putpixel((xx, y), (200, 150, 120))
    for xx in range(40, 92):                                                         # stín padá doleva od chodidla
        for y in range(250, 262):
            pic.putpixel((xx, y), (30, 90, 40))
    cut = panels.cut_out(pic.convert("RGBA"), shadow=True)
    assert cut.getpixel((100, 100))[3] == 255
    assert cut.getpixel((60, 256))[3] > 60 and cut.getpixel((60, 256))[:3] == (0, 0, 0)      # vlevo, kde byl
    assert cut.getpixel((150, 256))[3] == 0 and cut.getpixel((100, 280))[3] == 0     # vpravo a pod chodidlem nic
    assert cut.getpixel((60, 60))[3] == 0
    assert panels.cut_out(pic.convert("RGBA")).getpixel((60, 256))[3] == 0


def test_dark_red_theme_colours_the_page(tmp_path):
    svg = panels.render_svg({"size": "1600x1000", "title": "Věž", "template": "ruda", "ai_note": "x", "panels": [
        {"id": "cisla", "typ": "fakta", "rect": [0, 0, 800, 100], "nazev": "Čísla", "smer": "radek", "items": [{"value": "1", "text": "a"}]}]}, tmp_path)
    assert f'fill="{panels.THEMES["ruda"]["bg"]}"' in svg


def test_dark_red_labels_have_a_soft_shadow_instead_of_an_outline(tmp_path):
    source = tmp_path / "a.png"
    Image.new("RGB", (100, 80), "red").save(source)
    panels.copy_image(source, tmp_path, "obr")
    doc = {"size": "1600x1000", "title": "Věž", "ai_note": "x", "panels": [{"id": "obr", "typ": "obraz", "rect": [0, 0, 800, 400], "nazev": "Obraz", "labels": [label("Vítěz", [10, 20, 0], pos=[900, 100])]}]}
    doc["panels"] = panels.validate(doc)
    red = panels.render_svg({**doc, "template": "ruda"}, tmp_path)
    assert 'filter="url(#stin-textu)"' in red and 'stroke="#000000"' not in red
    assert 'filter="url(#stin-textu)"' in panels.clean_svg(red, allow_data_images=True)
    dark = panels.render_svg({**doc, "template": "dark"}, tmp_path)
    assert "stin-textu" not in dark and 'stroke="#000000"' in dark


def test_caption_without_a_heading_is_plain_text(tmp_path):
    source = tmp_path / "a.png"
    Image.new("RGB", (100, 80), "red").save(source)
    panels.copy_image(source, tmp_path, "obr")
    doc = {"size": "1600x1000", "title": "Věž", "ai_note": "x", "accent": "#dcb062", "panels": [{"id": "obr", "typ": "obraz", "rect": [0, 0, 800, 400], "nazev": "Obraz", "pod": {"small": "Autor, rok"}}]}
    doc["panels"] = panels.validate(doc)
    caption = re.search(r"<text[^>]*>Autor, rok</text>", panels.render_svg(doc, tmp_path)).group(0)
    assert 'font-weight="400"' in caption and "#dcb062" not in caption and 'y="430.0"' in caption


def test_checks_catch_a_struck_label_and_a_second_view_of_the_same_model(tmp_path):
    source = tmp_path / "a.png"
    Image.new("RGB", (100, 100), "red").save(source)
    for panel_id in ("hlavni", "detail", "jiny"):
        panels.copy_image(source, tmp_path, panel_id)
    same = {"model_id": "m", "version": "v1", "render": "r-1"}
    doc = {"size": "1600x1000", "title": "Věž", "ai_note": "x", "sources": "zdroj", "panels": [
        {"id": "hlavni", "typ": "obraz", "poradi": 1, "rect": [0, 0, 100, 100], "nazev": "Hlavní", "zdroj": same,
         "labels": [label("Dlouhý popisek", [90, 50, 0], pos=[20, 44])]},           # bod vpravo, text doleva: vodítko jde přes něj
        {"id": "detail", "typ": "obraz", "poradi": 2, "rect": [200, 0, 100, 100], "nazev": "Detail", "zdroj": same},
        {"id": "jiny", "typ": "obraz", "poradi": 3, "rect": [400, 0, 100, 100], "nazev": "Obraz", "zdroj": {"ref_id": "x"}}]}
    doc["panels"] = panels.validate(doc)
    found = {c["text"]: c["ok"] for c in panels.checks(doc, tmp_path)}
    assert found["vodítko přeškrtává text: Dlouhý popisek"] is False
    assert found["opakují hlavní model a neříkají proč: Detail. Co ukážou víc než hlavní obraz?"] is False
    doc["panels"][1]["otazka"] = "Co je pod pískem?"
    doc["panels"][0]["labels"][0]["align"] = "right"
    doc["panels"][0]["labels"][0]["pos"] = [80, 44]
    found = {c["text"]: c["ok"] for c in panels.checks(doc, tmp_path)}
    assert found["vodítka nepřeškrtávají text"] is True and not any("opakují" in text for text in found)


def test_checks_measure_the_text_on_a_phone(tmp_path):
    source = tmp_path / "a.png"
    Image.new("RGB", (100, 100), "red").save(source)
    panels.copy_image(source, tmp_path, "hlavni")
    doc = {"size": "1800x2400", "title": "Studna", "ai_note": "x", "sources": "zdroj", "pismo": panels.MOBIL, "panels": [
        {"id": "hlavni", "typ": "obraz", "poradi": 1, "rect": [0, 0, 1800, 1400], "nazev": "Hlavní", "labels": [label("Muž", [50, 50, 0], pos=[100, 100], size=72)]},     # popis je 0,86 názvu
        {"id": "text", "typ": "text", "poradi": 2, "rect": [0, 1400, 1800, 1000], "nazev": "Text", "items": [{"value": "Nebyl sám", "text": "Kosti 20 lidí"}], "small_size": 60}]}
    doc["panels"] = panels.validate(doc)
    assert "písmo čitelné i na mobilu" in {c["text"] for c in panels.checks(doc, tmp_path) if c["ok"]}
    doc["panels"][1]["small_size"] = 26
    found = [c for c in panels.checks(doc, tmp_path) if not c["ok"] and "na mobilu" in c["text"]]
    assert found and "5.2 px" in found[0]["text"]


def test_new_document_has_phone_sizes_and_old_stays_as_it_was(api, settings, tmp_path):
    shot(settings.library_dir / "strely" / "hlavni", ["zed"])
    shot(settings.library_dir / "strely" / "detail")
    new = api.post("/api/v2/infographics/panels", json=fields(size="1080x1620", pismo="mobil", panels=[{**fields()["panels"][2], "rect": [50, 300, 900, 100]}, {"id": "obr", "typ": "obraz", "rect": [0, 500, 1080, 500], "zdroj": {"slozka": "strely/detail"}, "labels": [label("Věž", [10, 10, 0], pos=[50, 520])]}])).json()
    assert new["pismo"]["jednotek"] == panels.MOBIL["jednotek"]
    W = 1080
    svg = api.get(f"/api/v2/infographics/{new['id']}/svg").text
    sizes = {float(v) for v in re.findall(r'font-size="([\d.]+)"', svg)}
    assert round(W / 15, 1) in sizes and min(sizes) * panels.PHONE_W / W >= panels.PHONE_SOURCE_PX
    assert 22 * W / 546 * 0.86 * panels.PHONE_W / W >= panels.PHONE_MIN_PX        # popis pod popiskem je nejmenší text
    assert "Blender" in new["ai_note"]
    poster = api.post("/api/v2/infographics/panels", json=fields(pismo="plakat")).json()
    assert poster["pismo"] == "plakat"
    assert "88.0" in re.findall(r'font-size="([\d.]+)"', api.get(f"/api/v2/infographics/{poster['id']}/svg").text)
    old = {"size": "1600x1000", "title": "Dlouhý titulek starého plakátu, který se nikdy nezalomí", "ai_note": "x", "panels": [
        {"id": "text", "typ": "text", "rect": [0, 300, 800, 100], "titulek": "Nadpis panelu", "items": [{"value": "V", "text": "věta"}]},
        {"id": "osa", "typ": "osa", "rect": [800, 300, 800, 100], "items": [{"value": "1891", "text": "věta"}]}]}
    old["panels"] = panels.validate(old)
    drawn = panels.render_svg(old, tmp_path)
    assert 'font-size="88.0"' in drawn and 'font-size="25.0"' in drawn and 'font-size="17.0"' in drawn and 'font-size="21.0"' in drawn
    assert "DLOUHÝ TITULEK STARÉHO PLAKÁTU, KTERÝ SE NIKDY NEZALOMÍ<" in drawn
    assert panels.render_svg({**old, "pismo": "plakat"}, tmp_path) == drawn
    assert 'x="942.0"' in drawn      # osa: sloupec letopočtů 118 k


def test_new_page_has_no_source_line_only_the_ai_mark(api, settings):
    folder = settings.library_dir / "strely" / "hlavni"
    shot(folder)
    img = api.post("/api/v2/images", json={"prompt": "a scene", "size": "256x256", "seed": 1}).json()["job_id"]
    assert wait(api, img)["status"] == "done"
    picture = {"id": "obr", "typ": "obraz", "nazev": "Model", "rect": [0, 300, 1080, 600], "zdroj": {"slozka": "strely/hlavni"}}
    plain = api.post("/api/v2/infographics/panels", json={"title": "Věž", "size": "1080x1350", "sources": "Wikipedie", "panels": [picture]}).json()
    svg = api.get(f"/api/v2/infographics/{plain['id']}/svg").text
    assert plain["na_strance"] == "" and "Wikipedie" not in svg and "Zdroj" not in svg and "Blender" not in svg and "Blender" in plain["ai_note"]
    assert api.post(f"/api/v2/infographics/{plain['id']}/export", json={"format": "svg"}).status_code == 201
    ai = api.post("/api/v2/infographics/panels", json={"title": "Věž", "size": "1080x1350", "panels": [picture, {**picture, "id": "fig", "nazev": "Figura", "rect": [0, 900, 400, 300], "zdroj": {"obraz": f"{img}/0"}}]}).json()
    assert ai["na_strance"] == "Figura: AI" and ai["ai_generated"] is True and "Figura: AI" in api.get(f"/api/v2/infographics/{ai['id']}/svg").text
    assert api.post(f"/api/v2/infographics/{ai['id']}/export", json={"format": "svg"}).status_code == 201
    made = api.post("/api/v2/infographics/panels", json={"title": "Věž", "size": "1080x1350", "panels": [{**picture, "zdroj": {"slozka": "strely/hlavni", "ai": "FLUX 3 Klein"}, "nazev": "Figura"}]}).json()
    assert made["na_strance"] == "Figura: AI" and "FLUX 3 Klein" in made["ai_note"] and "Blender" not in made["ai_note"]


def test_see_through_picture_keeps_its_transparency_and_a_glow_behind_it(tmp_path):
    source = tmp_path / "a.png"
    Image.new("RGBA", (100, 80), (200, 0, 0, 128)).save(source)
    panels.copy_image(source, tmp_path, "obr")
    doc = {"size": "1080x1350", "title": "Věž", "ai_note": "x", "pismo": panels.MOBIL, "panels": [{"id": "obr", "typ": "obraz", "rect": [0, 300, 1000, 800], "nazev": "Obraz", "pruhledny": True, "zar": {"x": 500, "y": 700, "r": 400}}]}
    doc["panels"] = panels.validate(doc)
    svg = panels.render_svg(doc, tmp_path)
    assert (tmp_path / "panely" / "obr" / "orez" / "pruhledny.png").is_file() and "image/png" in svg and "radialGradient" in svg
    assert "radialGradient" in panels.clean_svg(svg, allow_data_images=True)
    doc["panels"][0].pop("zar")
    assert "radialGradient" not in panels.render_svg(doc, tmp_path)


def test_collision_with_a_picture_is_measured_on_the_object_not_its_frame(tmp_path):
    source = tmp_path / "a.png"
    pic = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    pic.paste((90, 90, 90, 255), (40, 40, 60, 60))
    pic.save(source)
    panels.copy_image(source, tmp_path, "obr")
    doc = {"size": "1080x1350", "title": "Věž", "ai_note": "x", "pismo": panels.MOBIL, "panels": [
        {"id": "obr", "typ": "obraz", "rect": [0, 200, 1000, 1000], "nazev": "Obraz"},
        {"id": "a", "typ": "text", "nazev": "Vedle", "rect": [20, 220, 300, 100], "items": [{"value": "V", "text": "x"}]}]}
    doc["panels"] = panels.validate(doc)
    assert not any("zasahuje" in c["text"] for c in panels.checks(doc, tmp_path))
    doc["panels"][1]["rect"] = [420, 620, 300, 100]
    assert any(c["text"] == "text panelu zasahuje jinam: Vedle × Obraz" for c in panels.checks(doc, tmp_path))


def test_long_title_and_heading_wrap_on_a_new_page(tmp_path):
    doc = {"size": "1080x1350", "title": "Jak se z malého chlapce ze Smiljanu stal vynálezce", "ai_note": "x", "pismo": panels.MOBIL, "panels": [
        {"id": "text", "typ": "text", "rect": [40, 400, 500, 100], "titulek": "Nadpis panelu který se nevejde na řádek", "items": [{"value": "V", "text": "věta"}]}]}
    doc["panels"] = panels.validate(doc)
    drawn = panels.render_svg(doc, tmp_path)
    title = re.search(r'<g id="Nadpis">(.*?)</g>', drawn).group(1)
    assert title.count("<text") >= 2 and "JAK SE" in title
    heading = re.search(r'<g id="Nadpis Nadpis panelu[^"]*">(.*?)</g>', drawn).group(1)
    assert heading.count("<text") >= 2
    last = float(re.findall(r'y="([\d.]+)"', heading)[-1])
    assert last == pytest.approx(400 - 12 * 1080 / 546, abs=0.1)     # poslední řádek zůstává těsně nad textem


def test_checks_count_words_and_collisions_and_every_kind_of_text(tmp_path):
    many = " ".join(["slovo"] * 40)
    doc = {"size": "1080x1350", "title": "Titulek", "ai_note": "x", "na_strance": "Figura: AI", "sources": "z", "pismo": panels.MOBIL, "panels": [
        {"id": "a", "typ": "text", "nazev": "První", "rect": [40, 200, 1000, 100], "items": [{"value": "V", "text": many} for _ in range(3)]},
        {"id": "b", "typ": "text", "nazev": "Druhý", "rect": [40, 240, 1000, 100], "items": [{"value": "V", "text": "krátce"}]}]}
    doc["panels"] = panels.validate(doc)
    found = {c["text"]: c["ok"] for c in panels.checks(doc, tmp_path)}
    assert any(t.startswith("na mobilu se na stránku vejde kolem 80 slov") and ok is False for t, ok in found.items())
    assert found["text panelu zasahuje jinam: První × Druhý"] is False
    doc["panels"] = panels.validate({**doc, "panels": [{"id": "a", "typ": "text", "nazev": "První", "rect": [40, 1200, 1000, 100], "items": [{"value": "V", "text": many}]}]})
    found = {c["text"]: c["ok"] for c in panels.checks(doc, tmp_path)}
    assert found["text panelu zasahuje jinam: První × patička"] is False and found["text panelu přetéká stránku: První"] is False
    small = {"size": "1080x1350", "title": "Titulek", "ai_note": "x", "sources": "z", "pismo": panels.MOBIL, "panels": [
        {"id": "k", "typ": "kresba", "nazev": "Plán", "rect": [0, 200, 1080, 500], "viewbox": [0, 0, 1080, 500], "kresba": "<rect width='9' height='9'/>", "texty": '<text font-size="20">řez</text>'}]}
    small["panels"] = panels.validate(small)
    assert any("nejmenší text 6.7 px" in c["text"] and not c["ok"] for c in panels.checks(small, tmp_path))
    plakat = {**small, "pismo": None, "panels": small["panels"]}
    low = next(c["text"] for c in panels.checks(plakat, tmp_path) if "na mobilu (" in c["text"])
    assert "titulek" in low and "zdroj" in low
    with pytest.raises(InfoError, match="pismo"):
        panels.validate({**small, "pismo": {"neznama": 1}})
    with pytest.raises(InfoError, match="pismo"):
        panels.validate({**small, "pismo": "maly"})


@pytest.mark.parametrize("kind", ["fakta", "text", "osa"])
def test_text_height_reaches_the_last_line(kind, tmp_path):
    doc = {"size": "1080x1350", "title": "T", "ai_note": "x", "pismo": panels.MOBIL, "panels": [
        {"id": "a", "typ": kind, "nazev": "A", "rect": [40, 200, 700, 100], "items": [{"value": "1891", "text": "Věta o tom, co se tehdy stalo a proč je to důležité pro čtenáře."} for _ in range(3)]}]}
    doc["panels"] = panels.validate(doc)
    k = 1080 / panels.MOBIL["jednotek"]
    drawn = ET.fromstring(panels.render_svg(doc, tmp_path))
    group = next(g for g in drawn.iter(f"{SVG}g") if g.get("id") == "A")
    last = max(float(t.get("y")) for t in group.iter(f"{SVG}text"))
    height = panels.text_height(doc["panels"][0], panels.MOBIL, k)
    assert 200 + height == pytest.approx(last + panels.MOBIL["veta"] * k * 0.3, abs=1.0)


def test_thresholds_match_the_editor():
    source = (REPO / "studio" / "src" / "Infographics.tsx").read_text(encoding="utf-8")
    assert f"const MAX_LABELS = {panels.MAX_LABELS}" in source and f"const MAX_LABEL_CHARS = {panels.MAX_LABEL_CHARS}" in source
    assert f"const LEADER_MEDIAN_MAX = {panels.LEADER_MEDIAN_MAX}" in source and f"const LEADER_MAX = {panels.LEADER_MAX}" in source


def test_examples_build_valid_documents():
    import importlib.util
    spec = importlib.util.spec_from_file_location("koloseum_infografika", REPO / "scripts" / "3d" / "koloseum_infografika.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model_spec = json.loads((REPO / "scripts" / "3d" / "dily" / "koloseum.json").read_text(encoding="utf-8"))
    names = {p["nazev"] for p in model_spec["dily"] if p["typ"] not in module.CUTS}
    groups_ = module.groups_of(model_spec)
    assert sorted(n for g in groups_.values() for n in g) == sorted(names)      # render odmítne vrstvy, kde díl chybí nebo je dvakrát
    from engine.parts3d import RenderIn, check_render
    from engine.parts_spec import validate
    clean = validate(model_spec)
    requests = module.renders(model_spec)
    for request in requests.values():
        check_render(RenderIn(**request), clean)
    page = module.page({k: {"slozka": k} for k in requests})
    checked = panels.validate(page)
    points = {a["nazev"] for a in clean["kotvy"]}
    assert all(label_["kotva"] in points for p in checked if p["typ"] == "obraz" for label_ in p["labels"] if isinstance(label_["kotva"], str))
    assert sorted(p["poradi"] for p in checked) == list(range(1, len(checked) + 1))


def test_reformat_makes_a_new_document_and_leaves_the_source(api, settings, doc):
    source = settings.library_dir / "infographics" / doc["id"] / "info.json"
    before = source.read_bytes()
    r = api.post(f"/api/v2/infographics/{doc['id']}/reformat", json={"size": "16:9"})
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["id"] != doc["id"] and new["predelano_z"] == {"id": doc["id"], "size": "1600x2400"}
    W, H = map(int, new["size"].split("x"))
    assert abs(W / H - 16 / 9) < 0.01 and abs(W * H - 1600 * 2400) < 0.01 * 1600 * 2400
    assert source.read_bytes() == before
    assert (settings.library_dir / "infographics" / new["id"] / "panely" / "hlavni" / "obraz.png").is_file()
    # stejné panely a texty, jen jinde
    assert [p["id"] for p in new["panels"]] == [p["id"] for p in doc["panels"]]
    assert api.get(f"/api/v2/infographics/{new['id']}/svg").text.count('<g id="Texty">') == 1
    assert [i["value"] for p in new["panels"] if "items" in p for i in p["items"]] == [i["value"] for p in doc["panels"] if "items" in p for i in p["items"]]
    for p in new["panels"]:
        x, y, w, h = p["rect"]
        assert x >= 0 and y >= 0 and x + w <= W + 0.5 and y + h <= H + 0.5
    assert api.get(f"/api/v2/infographics/{new['id']}/svg").status_code == 200
    assert api.get(f"/api/v2/infographics/{new['id']}/kontrola").status_code == 200


def test_reformat_keeps_labels_on_the_same_point_of_the_picture(api, doc):
    new = api.post(f"/api/v2/infographics/{doc['id']}/reformat", json={"size": "1080x1350"}).json()
    old_p, new_p = doc["panels"][0], new["panels"][0]
    s = new_p["rect"][2] / old_p["rect"][2]
    assert new_p["k"] == pytest.approx(s * 1.0)
    dx = new_p["labels"][0]["pos"][0] - new_p["rect"][0]
    assert dx == pytest.approx((old_p["labels"][0]["pos"][0] - old_p["rect"][0]) * s)


def test_reformat_again_scales_from_the_new_format(api, doc):
    one = api.post(f"/api/v2/infographics/{doc['id']}/reformat", json={"size": "1:1"}).json()
    two = api.post(f"/api/v2/infographics/{one['id']}/reformat", json={"size": "2:3"})
    assert two.status_code == 201, two.text
    assert two.json()["predelano_z"]["id"] == one["id"]


@pytest.mark.parametrize("size", ["nesmysl", "0:5", "1x1"])
def test_reformat_refuses_unknown_format(api, doc, size):
    assert api.post(f"/api/v2/infographics/{doc['id']}/reformat", json={"size": size}).status_code == 400


def test_reformat_refuses_documents_without_panels_and_missing_ones(api):
    buf = BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, "PNG")
    old = api.post("/api/v2/infographics/upload", json={"b64": base64.b64encode(buf.getvalue()).decode(), "name": "a.png"}).json()
    assert api.post(f"/api/v2/infographics/{old['id']}/reformat", json={"size": "1:1"}).status_code == 400
    assert api.post("/api/v2/infographics/20000101-000000-0000/reformat", json={"size": "1:1"}).status_code == 404


def test_reformatted_document_reports_the_phone_size_of_its_own_scale(api, doc):
    new = api.post(f"/api/v2/infographics/{doc['id']}/reformat", json={"size": "16:9"}).json()
    phone = [c for c in api.get(f"/api/v2/infographics/{new['id']}/kontrola").json() if "mobilu" in c["text"]]
    assert phone and not phone[0]["ok"]
    assert phone[0]["text"] != [c for c in api.get(f"/api/v2/infographics/{doc['id']}/kontrola").json() if "mobilu" in c["text"]][0]["text"]


def test_print_supplement_has_no_phone_finding_and_format_change_keeps_it(api, doc):
    assert any("mobilu" in c["text"] and not c["ok"] for c in api.get(f"/api/v2/infographics/{doc['id']}/kontrola").json())
    saved = api.put(f"/api/v2/infographics/{doc['id']}", json={**doc, "urceni": "tisk"})
    assert saved.status_code == 200, saved.text
    rows = api.get(f"/api/v2/infographics/{doc['id']}/kontrola").json()
    assert not any("mobilu" in c["text"] and not c["ok"] for c in rows) and any("tisková příloha" in c["text"] for c in rows)
    assert api.post(f"/api/v2/infographics/{doc['id']}/reformat", json={"size": "4:5"}).json()["urceni"] == "tisk"
    assert api.put(f"/api/v2/infographics/{doc['id']}", json={**doc, "urceni": "plakat"}).status_code == 400


def _tokens(panel: dict) -> set[str]:
    texts = [(panel.get("titulek") or {}).get("text", "")]
    for lab in panel.get("labels", []):
        texts += [lab["text"], *lab["small"]]
    if panel.get("pod"):
        texts += [panel["pod"]["text"], panel["pod"]["small"]]
    for item in panel.get("items", []):
        texts += [item["value"], item["text"]]
    return set(" ".join(texts).split())


def test_split_keeps_every_word_and_leaves_the_source(api, settings, doc):
    source = settings.library_dir / "infographics" / doc["id"] / "info.json"
    before = source.read_bytes()
    plan = api.post(f"/api/v2/infographics/{doc['id']}/rozdeleni", json={"stranky": None}).json()["stranky"]
    assert source.read_bytes() == before and len(api.get("/api/v2/infographics?panely=true").json()) == 1      # návrh nic nezapíše
    r = api.post(f"/api/v2/infographics/{doc['id']}/rozdelit", json={"stranky": None})
    assert r.status_code == 201, r.text
    pages = r.json()
    assert len(pages) == len(plan) and source.read_bytes() == before
    assert [p["serie"]["stranka"] for p in pages] == list(range(1, len(pages) + 1)) and {p["serie"]["celkem"] for p in pages} == {len(pages)}
    wanted = set().union(*(_tokens(p) for p in doc["panels"]))
    got = set().union(*(_tokens(q) for p in pages for q in p["panels"])) | {w for p in pages for w in p["title"].split()}
    assert wanted <= got, wanted - got
    for page in pages:
        W, H = map(int, page["size"].split("x"))
        assert W == 1080
        rows = api.get(f"/api/v2/infographics/{page['id']}/kontrola").json()
        assert all(c["ok"] for c in rows if "mobilu" in c["text"]), rows
        assert api.get(f"/api/v2/infographics/{page['id']}/svg").status_code == 200
        for p in page["panels"]:
            x, y, w, h = p["rect"]
            assert x >= 0 and x + w <= W + 0.5 and y + h <= H + 0.5


def test_split_keeps_labels_at_the_picture_and_only_a_short_note(api, settings, doc):
    pages = api.post(f"/api/v2/infographics/{doc['id']}/rozdelit", json={"stranky": None}).json()
    hero = next(p for page in pages for p in page["panels"] if p["id"] == "hlavni")
    assert hero["labels"][0]["text"] == "Věž" and hero["labels"][0]["kotva"] == "vez"
    assert hero["labels"][0]["size"] * 360 / 1080 >= 12 / 0.86 - 0.01
    assert "Wikipedie" not in api.get(f"/api/v2/infographics/{pages[0]['id']}/svg").text and pages[0]["sources"] == "Wikipedie"


def test_split_puts_extra_labels_on_a_crop_of_the_picture(api, settings):
    shot(settings.library_dir / "strely" / "hlavni", ["zed"])
    many = [label(text=f"Věc {n}", kotva=[n * 0.1, 0, 0]) for n in range(7)]
    fields_many = {"title": "Věž", "size": "1600x2400", "sources": "Wikipedie", "panels": [
        {"id": "hlavni", "typ": "obraz", "poradi": 1, "nazev": "Hlavní", "rect": [0, 100, 800, 400], "zdroj": {"slozka": "strely/hlavni"}, "labels": many}]}
    doc = api.post("/api/v2/infographics/panels", json=fields_many).json()
    before = (settings.library_dir / "infographics" / doc["id"] / "panely" / "hlavni" / "obraz.png").read_bytes()
    pages = api.post(f"/api/v2/infographics/{doc['id']}/rozdelit", json={"stranky": None}).json()
    views = [p for page in pages for p in page["panels"] if p["typ"] == "obraz"]
    assert [len(v["labels"]) for v in views] == [5, 2]
    assert sorted(lab["text"] for v in views for lab in v["labels"]) == [f"Věc {n}" for n in range(7)]
    crop = settings.library_dir / "infographics" / next(page["id"] for page in pages if any(p["id"] == "hlavni_v2" for p in page["panels"])) / "panely" / "hlavni_v2"
    assert (crop / "obraz.png").is_file() and json.loads((crop / "body.json").read_text(encoding="utf-8"))["res"][0] < 200
    assert (settings.library_dir / "infographics" / doc["id"] / "panely" / "hlavni" / "obraz.png").read_bytes() == before


def test_split_lets_the_editor_move_pieces_but_never_drop_one(api, doc):
    plan = api.post(f"/api/v2/infographics/{doc['id']}/rozdeleni", json={"stranky": None}).json()["stranky"]
    ids = [k["id"] for page in plan for k in page["kusy"]]
    one = api.post(f"/api/v2/infographics/{doc['id']}/rozdeleni", json={"stranky": [ids[:1], ids[1:]]})
    assert one.status_code == 200 and len(one.json()["stranky"]) == 2
    assert api.post(f"/api/v2/infographics/{doc['id']}/rozdeleni", json={"stranky": [ids[:1]]}).status_code == 400
    assert api.post(f"/api/v2/infographics/{doc['id']}/rozdelit", json={"stranky": [ids, ids[:1]]}).status_code == 400
    assert len(api.get("/api/v2/infographics?panely=true").json()) == 1


def test_split_refuses_documents_without_panels(api):
    buf = BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, "PNG")
    old = api.post("/api/v2/infographics/upload", json={"b64": base64.b64encode(buf.getvalue()).decode(), "name": "a.png"}).json()
    assert api.post(f"/api/v2/infographics/{old['id']}/rozdeleni", json={"stranky": None}).status_code == 400
    assert api.post(f"/api/v2/infographics/{old['id']}/rozdelit", json={"stranky": None}).status_code == 400
