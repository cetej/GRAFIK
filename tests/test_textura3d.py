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
    assert body["seedy"] == {"kuze": 62, "vnitrek": 61} and body["vrstvy"] == ["vrstva-kuze.png", "vrstva-vnitrek.png"]
    out = versions(settings) / body["dir"]
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
