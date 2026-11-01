"""Model z dílů a barevný render jako úlohy Engine, s falešným Blenderem; skutečný Blender je v tests/test_parts_spec.py."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from engine import parts3d
from tests.test_models3d import api, settings, trace, upload, wait  # noqa: F401  (fixtures)

SPEC = {"nazev": "věž", "dim": {"length": 20, "width": 16, "height": 5}, "dily": [
    {"typ": "prstenec", "nazev": "zed", "osy": [10, 8], "profil": [[-1, 0], [0, 0], [0, 5], [-1, 5]]},
    {"typ": "disk", "nazev": "podlaha", "osy": [10, 8], "z0": -1, "z1": 0},
    {"typ": "arkady", "nazev": "oblouky", "cil": "zed", "osy": [10, 8], "odsazeni": [-1, 0], "vyska": 3, "sirka": 2, "pocet": 8}]}


def model(api, **over):
    r = api.post("/api/v2/models3d/parts", json={"title": "Věž", "spec": SPEC, **over})
    assert r.status_code == 202, r.text
    assert r.json()["estimate_usd"] == 0.0
    return r.json()


@pytest.fixture
def built(api):
    m = model(api)
    assert wait(api, m["job_id"])["status"] == "done"
    return m


def versions(settings, mid="vez", ver="v1") -> Path:
    return settings.library_dir / "3d" / mid / ver


def test_parts_model_is_built_under_the_lock_and_gets_a_viewer(api, settings, built):
    d = versions(settings)
    assert (d / "model.glb").read_bytes().startswith(b"glTF") and (d / "popis.json").is_file() and (d / "dily.json").is_file()
    assert not list(d.glob("model.tmp*"))
    meta = api.get("/api/v2/models3d/vez").json()["versions"][0]
    assert meta["method"] == "parts" and meta["dily"] == ["podlaha", "zed"] and meta["bez_kontaktu"] == [] and meta["cost_usd"] == 0.0
    jobs = [j["kind"] for j in meta["jobs"]]
    assert jobs[0] == "parts3d" and "viewer3d" in jobs
    calls = [c for c in trace(settings) if c["script"] == "lod_parts.py"]
    assert len(calls) == 1 and calls[0]["lock"] is not None


def test_bad_description_stops_before_anything_is_saved(api, settings):
    bad = {**SPEC, "dily": [{**SPEC["dily"][0], "typ": "python"}]}
    r = api.post("/api/v2/models3d/parts", json={"title": "Věž", "spec": bad})
    assert r.status_code == 400 and "neznámý typ" in r.json()["detail"]
    assert not (settings.library_dir / "3d" / "vez").exists()


def test_failed_build_says_so_and_leaves_no_half_model(api, settings, monkeypatch):
    monkeypatch.setenv("FAKE_BLENDER_MODE", "crash")
    m = model(api)
    assert wait(api, m["job_id"])["status"] == "failed"
    meta = api.get("/api/v2/models3d/vez").json()["versions"][0]
    assert meta["status"] == "failed" and "GLB import failed" in meta["error"]
    assert not (versions(settings) / "model.glb").exists()


def render(api, **body):
    return api.post("/api/v2/models3d/vez/v1/render", json=body)


def test_render_is_a_job_and_never_overwrites(api, settings, built):
    first = render(api, pohled="rez", res=[640, 360], samples=16)
    assert first.status_code == 202 and first.json()["estimate_usd"] == 0.0
    assert wait(api, first.json()["job_id"])["status"] == "done"
    png = versions(settings) / "renders" / "r-1" / "obraz.png"
    before = png.read_bytes()
    wait(api, render(api, pohled="rez", res=[640, 360], samples=16).json()["job_id"])
    assert png.read_bytes() == before and (versions(settings) / "renders" / "r-2" / "obraz.png").is_file()
    meta = api.get("/api/v2/models3d/vez").json()["versions"][0]
    assert [r["id"] for r in meta["renders"]] == ["r-1", "r-2"]
    assert meta["renders"][0]["file"] == "renders/r-1/obraz.png" and meta["renders"][0]["pohled"] == "rez"
    # soubory i kotvy jdou přes stávající cestu k souborům modelu
    assert api.get("/api/v2/models3d/vez/v1/files/renders/r-1/obraz.png").status_code == 200
    assert api.get("/api/v2/models3d/vez/v1/files/renders/r-1/body.json").json()["points"]["zed"] == [10, 10]
    call = [c for c in trace(settings) if c["script"] == "render_parts.py"][0]
    assert call["lock"] is not None and '"pohled": "rez"' in call["args"][2]


def test_render_stops_own_sd_server_first(api, settings, built, monkeypatch):
    stops = []
    monkeypatch.setattr(api.app.state.models3d.sd, "stop", lambda reason: stops.append(reason))
    wait(api, render(api).json()["job_id"])
    assert stops == ["barevný render v Blenderu"]


def test_layers_by_part_and_own_groups(api, settings, built):
    wait(api, render(api, vrstvy=True).json()["job_id"])
    d = versions(settings) / "renders"
    assert (d / "r-1" / "vrstva-zed.png").is_file() and (d / "r-1" / "vrstva-podlaha.png").is_file()
    wait(api, render(api, skupiny={"stavba": ["zed", "podlaha"]}).json()["job_id"])
    assert (d / "r-2" / "vrstva-stavba.png").is_file()
    meta = api.get("/api/v2/models3d/vez").json()["versions"][0]
    assert meta["renders"][1]["vrstvy"] == {"stavba": ["zed", "podlaha"]}


@pytest.mark.parametrize("body, message", [
    ({"pohled": "zezadu"}, "neznámý pohled"),
    ({"res": [10, 10]}, "rozměr"),
    ({"res": [9000, 1000]}, "rozměr"),
    ({"samples": 1}, "vzorků"),
    ({"pohled": "rozklad"}, "posuny"),
    ({"posuny": {"neni": 3}}, "takový díl"),
    ({"posuny": {"oblouky": 3}}, "takový díl"),     # řez není díl
    ({"skupiny": {"stavba": ["zed"]}}, "každý díl právě jednou"),
    ({"skupiny": {"a": ["zed", "podlaha"], "b": ["zed"]}}, "každý díl právě jednou"),
    ({"skupiny": {"../a": ["zed", "podlaha"]}}, "název vrstvy"),
])
def test_bad_render_request_is_refused_right_away(api, built, body, message):
    r = render(api, **body)
    assert r.status_code == 400 and message in r.json()["detail"]


def test_render_needs_a_parts_model(api):
    wait(api, upload(api, "Tatra")["job_id"])
    r = api.post("/api/v2/models3d/tatra/v1/render", json={})
    assert r.status_code == 400 and "z dílů" in r.json()["detail"]
    assert api.post("/api/v2/models3d/neni/v1/render", json={}).status_code == 404


@pytest.mark.parametrize("mode, message", [("crash", "GLB import failed"), ("empty", "prázdný")])
def test_failed_render_leaves_no_folder_and_keeps_the_log(api, settings, built, monkeypatch, mode, message):
    monkeypatch.setenv("FAKE_BLENDER_MODE", mode)
    job = wait(api, render(api).json()["job_id"])
    assert job["status"] == "failed" and message in job["error"]
    root = versions(settings) / "renders"
    assert not (root / "r-1").exists() and (root / "r-1.log").is_file()
    assert api.get("/api/v2/models3d/vez").json()["versions"][0].get("renders") is None
    # další render dostane nové číslo, log zůstává
    monkeypatch.delenv("FAKE_BLENDER_MODE")
    wait(api, render(api).json()["job_id"])
    assert (root / "r-2" / "obraz.png").is_file() and (root / "r-1.log").is_file()


def test_view_names_match_the_blender_script():
    source = (Path(parts3d.__file__).parent / "blender" / "render_parts.py").read_text(encoding="utf-8")
    block = source[source.index("VIEWS = {"):source.index("MARGIN =")]
    assert tuple(re.findall(r'"(\w+)": \{', block)) == parts3d.POHLEDY
