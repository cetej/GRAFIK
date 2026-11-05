"""Povrch vrstev 3D renderu z lokálního FLUXu (engine/textura3d.py), s falešným Blenderem a FLUXem, který vrátí předlohu."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from engine import textura3d
from tests.test_models3d import api, settings, wait  # noqa: F401  (fixtures)
from tests.test_parts3d import built, model, render, versions  # noqa: F401  (fixtures)

GROUPS = {"kuze": ["zed"], "vnitrek": ["podlaha"]}
LAYERS = {"kuze": {"prompt": "Photorealistic wrinkled grey skin", "slozeni": "okno"},
          "vnitrek": {"prompt": "Wet pink organs with exactly the shape of <ref_image_0>", "slozeni": "pod"}}


@pytest.fixture
def renders(api, built):
    colour = render(api, vrstvy=True, samostatne=True, skupiny=GROUPS, perspektiva=True).json()["job_id"]
    clay = render(api, vrstvy=True, samostatne=True, skupiny=GROUPS, perspektiva=True, hlina=True).json()["job_id"]
    assert wait(api, colour)["status"] == "done" and wait(api, clay)["status"] == "done"
    return "r-1", "r-2"


@pytest.fixture
def flux(api, settings, monkeypatch):
    """FLUX, který tvar předlohy dodrží přesně: vrátí zelené plátno s předlohou, jen zmenšené na zadanou velikost."""
    calls = []

    def process(job_id, req, created):
        calls.append((job_id, req))
        w, h = (int(v) for v in req.size.split("x"))
        out = settings.library_dir / "flux" / f"{job_id}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.open(req.refs[0].path).convert("RGB").resize((w, h)).save(out)
        return {"files": [str(out)]}

    monkeypatch.setattr(api.app.state.worker, "process", process)
    return calls


def texture(api, **over):
    return api.post("/api/v2/models3d/vez/v1/textura", json={"render": "r-1", "predloha": "r-2", "vrstvy": LAYERS, "seeds": [61, 62], **over})


def test_texture_is_one_job_with_a_flux_run_per_layer_and_seed(api, settings, renders, flux):
    library_before = api.get("/api/v2/library").json()["total"]
    r = texture(api)
    assert r.status_code == 202 and r.json()["estimate_usd"] == 0.0 and r.json()["obrazu"] == 4
    job = wait(api, r.json()["job_id"])
    assert job["status"] == "done", job.get("error")
    assert [c[0].rsplit("-", 2)[1:] for c in flux] == [["kuze", "61"], ["kuze", "62"], ["vnitrek", "61"], ["vnitrek", "62"]]
    req = flux[0][1]
    assert req.prompt.startswith(textura3d.SCREEN) and req.prompt.endswith(textura3d.SHAPE)     # tvar podle předlohy, když ho prompt neříká
    assert flux[2][1].prompt.count("<ref_image_0>") == 1
    assert req.refs[0].role == "geometry" and req.translate == "off" and req.backend == "flux-local" and req.seed == 61
    assert req.size == "1536x1536"      # falešný render je čtverec 64 × 64
    folder = versions(settings) / "renders" / "r-1" / "textura-1"
    info = json.loads((folder / "textura.json").read_text(encoding="utf-8"))
    assert info["id"] == "r-1-textura-1" and info["vrstvy"]["kuze"]["slozeni"] == "okno"
    assert all(s["iou"] > 0.95 for layer in info["vrstvy"].values() for s in layer["seedy"].values())
    assert info["vrstvy"]["kuze"]["tvar_drzi"] and (folder / "flux-vnitrek-62.png").is_file() and (folder / "predloha-kuze-zelena.png").is_file()
    assert Image.open(folder / "flux-kuze-61.png").size == (64, 64)
    assert api.get("/api/v2/library").json()["total"] == library_before     # pokusy FLUXu Knihovnu nezaplaví
    assert api.get("/api/v2/models3d/vez").json()["versions"][0]["textury"][0]["id"] == "r-1-textura-1"
    wait(api, texture(api).json()["job_id"])
    assert (versions(settings) / "renders" / "r-1" / "textura-2").is_dir() and (folder / "textura.json").is_file()   # nic se nepřepisuje


def test_pick_composes_layers_with_the_colour_render_and_turns_to_portrait(api, settings, renders, flux):
    wait(api, texture(api).json()["job_id"])
    r = api.post("/api/v2/models3d/vez/v1/textura/r-1-textura-1/vyber", json={"seedy": {"kuze": 62}, "na_vysku": True})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["seedy"] == {"kuze": 62, "vnitrek": 61} and body["vrstvy"] == ["vrstva-vnitrek.png", "vrstva-kuze.png"]   # zdola nahoru: pod je dole
    out = versions(settings) / body["dir"]
    assert (out / "obraz.png").is_file() and (versions(settings) / body["na_vysku"] / "obraz.png").is_file()     # dokument s panely ho potřebuje
    assert (out / "vrstva-kuze.png").is_file() and json.loads((out / "body.json").read_text(encoding="utf-8"))["textura"]["seedy"]["kuze"] == 62
    tall = versions(settings) / body["na_vysku"]
    assert json.loads((tall / "body.json").read_text(encoding="utf-8"))["points"]["zed"] == [10, 10]
    second = api.post("/api/v2/models3d/vez/v1/textura/r-1-textura-1/vyber", json={"seedy": {}}).json()
    assert second["dir"].endswith("hotovo-2") and (out / "vrstva-kuze.png").is_file()


def test_window_keeps_the_blender_outline_and_cavity_stays_under_the_organs():
    colour = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    colour.paste((50, 0, 0, 255), (0, 0, 5, 10))
    flux = Image.new("RGBA", (10, 10), (200, 200, 200, 255))
    window = textura3d.compose("okno", flux, colour)
    assert window.getpixel((2, 2))[3] == 255 and window.getpixel((8, 2))[3] == 0      # mimo obrys z Blenderu nic
    organs = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    organs.paste((220, 120, 120, 255), (0, 0, 2, 2))
    under = textura3d.compose("pod", organs, colour)
    assert under.getpixel((1, 1))[:3] == (220, 120, 120) and under.getpixel((3, 3))[:3] == (50, 0, 0)


def test_portrait_goes_to_flux_lying_and_points_turn_with_the_picture():
    assert textura3d.flux_size(2400, 1000) == (1536, 640) and textura3d.flux_size(900, 2200) == (1536, 624)
    turned = textura3d.transpose_points({"res": [2400, 1000], "points": {"a": [100, 20]}, "ramecky": {"a": [1, 2, 3, 4]}})
    assert turned["res"] == [1000, 2400] and turned["points"]["a"] == [20, 100] and turned["ramecky"]["a"] == [2, 1, 4, 3]


@pytest.mark.parametrize("over, status, message", [
    ({"render": "r-9"}, 404, "neexistuje"),
    ({"vrstvy": {"kost": {"prompt": "bone"}}}, 400, "nemá vrstvu"),
    ({"vrstvy": {"kuze": {"prompt": "skin", "slozeni": "nad"}}}, 400, "slozeni"),
    ({"seeds": list(range(7))}, 400, "seedů"),
    ({"seeds": [1, 1]}, 400, "seedů"),
])
def test_bad_texture_request_is_refused_right_away(api, renders, over, status, message):
    r = texture(api, **over)
    assert r.status_code == status and message in r.json()["detail"]


def test_pick_of_unknown_texture_or_seed_is_refused(api, renders, flux):
    assert api.post("/api/v2/models3d/vez/v1/textura/r-1-textura-1/vyber", json={"seedy": {}}).status_code == 404
    wait(api, texture(api).json()["job_id"])
    r = api.post("/api/v2/models3d/vez/v1/textura/r-1-textura-1/vyber", json={"seedy": {"kuze": 99}})
    assert r.status_code == 400 and "seedem 99" in r.json()["detail"]


def test_clay_option_reaches_the_blender_script(api, settings, renders):
    from tests.test_models3d import trace
    args = [c for c in trace(settings) if c["script"] == "render_parts.py"][1]["args"][2]
    assert '"hlina": true' in args and '"samostatne": true' in args


def test_failed_flux_leaves_no_half_texture(api, settings, renders, monkeypatch):
    def broken(job_id, req, created):
        raise RuntimeError("sd-server spadl")

    monkeypatch.setattr(api.app.state.worker, "process", broken)
    job = wait(api, texture(api).json()["job_id"])
    assert job["status"] == "failed" and "sd-server" in job["error"]
    assert not (versions(settings) / "renders" / "r-1" / "textura-1").exists()


def test_whale_recipe_names_layers_the_render_makes():
    spec = json.loads((Path(__file__).resolve().parents[1] / "scripts" / "3d" / "dily" / "vorvan.json").read_text(encoding="utf-8"))
    assert set(spec["textura"]) <= set(spec["render"]["skupiny"]) and spec["predloha"]["hlina"] and spec["predloha"]["kamera"] == spec["render"]["kamera"]


def test_page_goes_to_infographics_in_both_formats_without_credit(api, settings, renders, flux):
    wait(api, texture(api).json()["job_id"])
    hotovo = api.post("/api/v2/models3d/vez/v1/textura/r-1-textura-1/vyber", json={"seedy": {}, "na_vysku": True}).json()["dir"].split("/")[-1]
    r = api.post("/api/v2/models3d/vez/v1/textura/r-1-textura-1/stranka", json={
        "hotovo": hotovo, "titulek": "Věž zevnitř", "popisky": {"zed": "Zeď\npískovec, 2 m", "podlaha": "", "neni": "Nic"}, "nazvy_vrstev": {"kuze": "Kůže"}})
    assert r.status_code == 201, r.text
    docs = r.json()["dokumenty"]
    assert [d["size"] for d in docs] == ["1920x1080", "1080x1920"]
    doc = api.get(f"/api/v2/infographics/{docs[0]['id']}").json()
    panel = doc["panels"][0]
    assert doc["na_strance"] == "" and doc["title"] == "Věž zevnitř"
    assert panel["vrstvy"] == {"vnitrek": "vnitrek", "kuze": "Kůže"} and panel["orez"] == {"vnitrek": "kuze"} and panel["hrana"] is False
    assert [lb["kotva"] for lb in panel["labels"]] == ["zed"] and panel["labels"][0]["small"] == ["pískovec, 2 m"]     # prázdný a neznámý bod vypadly
    assert panel["zdroj"]["slozka"].endswith(f"{hotovo}/stranka-16x9")
    assert api.get(f"/api/v2/infographics/{docs[1]['id']}").json()["panels"][0]["zdroj"]["slozka"].endswith("stranka-9x16")
    svg = api.get(f"/api/v2/infographics/{docs[0]['id']}/svg").text
    assert "Zeď" in svg and "(AI)" not in svg and "AI)" not in svg


def test_creature_goes_to_the_topic_and_the_chain_builds_its_page_from_layers(api, settings, renders, flux):
    from engine import serie
    from engine.chain import Chain
    from engine.workflows import Workflow
    wait(api, texture(api).json()["job_id"])
    hotovo = api.post("/api/v2/models3d/vez/v1/textura/r-1-textura-1/vyber", json={"seedy": {}, "na_vysku": True}).json()["dir"].split("/")[-1]
    body = {"qid": "Q81214", "hotovo": hotovo, "nazev": "Věž s průhledem dovnitř", "popisky": {"zed": "Zeď", "podlaha": " "}}
    r = api.post("/api/v2/models3d/vez/v1/textura/r-1-textura-1/tema", json=body)
    assert r.status_code == 201, r.text
    assert api.post("/api/v2/models3d/vez/v1/textura/r-1-textura-1/tema", json={**body, "nazev": "Věž znovu"}).status_code == 201
    own = serie.own_pictures(settings.library_dir, {"entita": {"qid": "Q81214"}})
    assert [o["nazev"] for o in own] == ["Věž znovu"]       # stejný model a textura přepíše svůj řádek
    assert own[0]["popisky"] == {"zed": "Zeď"} and own[0]["tvor3d"]["hotovo"] == hotovo and own[0]["druh"] == "zvire"
    # stránka řetězce: položka s bodem jde na 3D obraz, bez bodu se ohlásí; na výšku první
    chain = api.app.state.chain
    wf = Workflow(id="wf-test", kind="infografika", urceni="web", stranky=[1])
    text = {"titulek": "Věž zevnitř", "polozky": [{"value": "Zeď", "text": "pískovec, 2 m", "bod": "zed"}, {"value": "1850", "text": "postavena", "bod": None}]}
    page = Chain._page_3d(chain, wf, 1, own[0]["tvor3d"], text, ["dřívější hlášení"])
    assert [d["size"] for d in page["dokumenty"]] == ["1080x1920", "1920x1080"] and page["doc"] == page["dokumenty"][0]["id"]
    assert page["hlaseni"] == ["dřívější hlášení", "Na 3D obraz se nevešlo: 1850 postavena"]
    doc = api.get(f"/api/v2/infographics/{page['doc']}").json()
    assert doc["serie"] == {"wf": "wf-test", "stranka": 1, "celkem": 1} and doc["na_strance"] == ""
    assert [lb["kotva"] for lb in doc["panels"][0]["labels"]] == ["zed"] and doc["panels"][0]["orez"] == {"vnitrek": "kuze"}
    empty = Chain._page_3d(chain, wf, 1, own[0]["tvor3d"], {"titulek": "x", "polozky": [text["polozky"][1]]}, [])
    assert empty["doc"] is None and "nemíří na bod" in empty["hlaseni"][-1]


@pytest.mark.parametrize("over, message", [({"qid": "vorvan"}, "Wikidaty"), ({"popisky": {"neni": "Nic"}}, "bodům"), ({"nazev": " "}, "co obraz ukazuje"), ({"hotovo": "hotovo-9"}, "obraz.png")])
def test_bad_topic_request_says_what_is_wrong(api, renders, flux, over, message):
    wait(api, texture(api).json()["job_id"])
    api.post("/api/v2/models3d/vez/v1/textura/r-1-textura-1/vyber", json={"seedy": {}})
    r = api.post("/api/v2/models3d/vez/v1/textura/r-1-textura-1/tema", json={"qid": "Q81214", "hotovo": "hotovo-1", "nazev": "Věž", "popisky": {"zed": "Zeď"}, **over})
    assert r.status_code == 400 and message in r.json()["detail"]


@pytest.mark.parametrize("body, status, message", [
    ({"hotovo": "hotovo-9", "titulek": "x", "popisky": {"zed": "Zeď"}}, 400, "obraz.png"),
    ({"hotovo": "../x", "titulek": "x", "popisky": {"zed": "Zeď"}}, 400, "hotovo"),
    ({"hotovo": "hotovo-1", "titulek": "x", "popisky": {"zed": " "}}, 400, "popisek"),
    ({"hotovo": "hotovo-1", "titulek": "x", "popisky": {"zed": "Zeď"}, "formaty": ["4:3"]}, 400, "formáty"),
])
def test_bad_page_request_says_what_is_wrong(api, renders, flux, body, status, message):
    wait(api, texture(api).json()["job_id"])
    api.post("/api/v2/models3d/vez/v1/textura/r-1-textura-1/vyber", json={"seedy": {}})
    r = api.post("/api/v2/models3d/vez/v1/textura/r-1-textura-1/stranka", json=body)
    assert r.status_code == status and message in r.json()["detail"]


def test_points_behind_see_through_skin_count_as_visible(tmp_path):
    for name, box, alpha in (("vnitrek", (2, 2, 8, 8), 255), ("kuze", (0, 0, 10, 10), 60)):
        im = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        im.paste((90, 90, 90, alpha), box)
        im.save(tmp_path / f"vrstva-{name}.png")
    opaque = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    opaque.paste((90, 90, 90, 255), (0, 0, 3, 3))
    opaque.save(tmp_path / "vrstva-potapec.png")
    body = {"vrstvy": {"vnitrek": [], "kuze": [], "potapec": []}, "points": {"organ": [5, 5], "zakryty": [2, 2], "voda": [20, 20], "kuze": [9, 9]}}
    assert textura3d.visible_points(tmp_path, body) == ["organ", "kuze"]


def test_crop_keeps_points_on_the_same_pixels(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    im = Image.new("RGBA", (100, 50), (0, 0, 0, 0))
    im.paste((200, 0, 0, 255), (40, 10, 60, 30))
    im.save(src / "obraz.png")
    im.save(src / "vrstva-a.png")
    (src / "body.json").write_text(json.dumps({"res": [100, 50], "points": {"p": [50, 20]}, "vrstvy": {"a": []}, "origin": [50, 25]}), encoding="utf-8")
    textura3d.crop_to_content(src, dst)
    body = json.loads((dst / "body.json").read_text(encoding="utf-8"))
    x, y = body["points"]["p"]
    assert body["res"][0] < 30 and Image.open(dst / "obraz.png").getpixel((int(x), int(y)))[0] == 200 and body["viditelne"] == ["p"]
