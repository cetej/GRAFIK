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
    return {"title": "Věž", "subtitle": "první řádek\ndruhý", "size": "1600x2400", "sources": "Wikipedie", "panels": [
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
    body = {"title": "Věž", "size": "1600x1000", "panels": [
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
