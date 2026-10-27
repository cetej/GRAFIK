"""3D scenes offline with the fake Blender (docs/plans/2026-10-27-3d-sceny.md, S1–S3, S5)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import scenes3d as sc
from tests.test_models3d import api, settings, trace, upload, wait  # noqa: F401  (fixtures)

CAM = {"target": [0, 2, -8], "azimuth": 305, "elevation": 22, "distance": 88, "lens": 50}


def harbour(**over) -> dict:
    body = {"title": "Loď u mola", "objects": [
        {"model": "lod", "rozmer": 45, "rozmer_zdroj": "Wikipedie: Quinquereme", "misto": [-4, 16]},
        {"tvar": "kvadr", "rozmery": [30, 6, 1.5], "nazev": "Molo", "misto": [4, 1]},
        {"model": "amfora", "rozmer": 0.7, "misto": [6, 1.5], "na": "molo"},
        {"model": "amfora", "rozmer": 0.7, "misto": [6.9, 1.1], "na": "molo"}],
        "postava": {"misto": [2.5, 1.2], "na": "molo"}}
    return {**body, **over}


@pytest.fixture
def models(api):
    for title in ("Loď", "Amfora"):
        wait(api, upload(api, title)["job_id"])
    return api


def test_save_fills_ids_names_and_versions(models):
    r = models.post("/api/v2/scenes3d", json=harbour())
    assert r.status_code == 201, r.text
    m = r.json()
    assert (m["id"], m["version"]) == ("lod-u-mola", "v1")
    assert [o["id"] for o in m["objects"]] == ["lod", "molo", "amfora", "amfora-2"]
    assert m["objects"][0]["nazev"] == "Loď" and m["objects"][0]["model_version"] == "v1"
    assert sc.short_title("Římská kvinquerema (TRELLIS 2)") == "Římská kvinquerema"   # method dropped
    assert m["problems"] == [] and len(m["unchecked"]) == 3
    # a change is a new version, the camera is metadata of the version
    v2 = models.post("/api/v2/scenes3d", json=harbour(scene_id="lod-u-mola")).json()
    assert v2["version"] == "v2" and v2["title"] == "Loď u mola"
    assert models.post("/api/v2/scenes3d/lod-u-mola/v1/camera", json={"camera": CAM}).json()["camera"] == CAM
    assert [v["version"] for v in models.get("/api/v2/scenes3d/lod-u-mola").json()["versions"]] == ["v1", "v2"]


def test_size_comes_from_stretch_or_from_an_earlier_scene(models, settings):
    wait(models, upload(models, "Tatra 87")["job_id"])
    st = models.post("/api/v2/models3d/tatra-87/v1/stretch", json={"dims": [4.74, 1.67, 1.5], "source": "Wikipedia"})
    wait(models, st.json()["job_id"])
    m = models.post("/api/v2/scenes3d", json={"title": "Náměstí", "objects": [{"model": "tatra-87"}]}).json()
    o = m["objects"][0]
    assert (o["model_version"], o["rozmer"]) == ("v2", 4.74) and "Wikipedia" in o["rozmer_zdroj"]
    # a size typed by hand goes to the model (Q2) and the next scene has it
    models.post("/api/v2/scenes3d", json=harbour())
    meta = json.loads((settings.library_dir / "3d" / "lod" / "v1" / "model.json").read_text(encoding="utf-8"))
    assert meta["rozmer_m"] == 45 and meta["rozmer_zdroj"] == "Wikipedie: Quinquereme"
    again = models.post("/api/v2/scenes3d", json={"objects": [{"model": "lod"}]}).json()["objects"][0]
    assert again["rozmer"] == 45 and again["rozmer_zdroj"] == "Wikipedie: Quinquereme"


def test_missing_size_saves_but_does_not_render(models):
    m = models.post("/api/v2/scenes3d", json={"title": "Bez rozměru", "objects": [{"model": "lod"}]}).json()
    assert m["problems"] == ["Loď: chybí rozměr (nejdelší strana v metrech)"]
    r = models.post("/api/v2/scenes3d/bez-rozmeru/v1/render", json={"camera": CAM})
    assert r.status_code == 409 and "chybí rozměr" in r.json()["detail"]


@pytest.mark.parametrize("obj, needle", [
    ({"model": "lod", "tvar": "kvadr", "rozmery": [1, 1, 1]}, "buď model"),
    ({"tvar": "kvadr", "rozmery": [1, 1]}, "délka, šířka a výška"),
    ({"tvar": "valec", "rozmery": [1, 0]}, "průměr a výška"),
    ({"tvar": "koule", "rozmery": [1]}, "tvar musí být"),
    ({"model": "lod", "rozmer": -1}, "kladný"),
    ({"model": "lod", "rozmer": 1, "na": "molo"}, "výš v seznamu"),
    ({"model": "neni-tu", "rozmer": 1}, "neexistuje"),
])
def test_impossible_objects_are_refused_in_czech(models, obj, needle):
    r = models.post("/api/v2/scenes3d", json={"title": "x", "objects": [obj]})
    assert r.status_code in (400, 404) and needle in r.json()["detail"], r.text


def test_bad_place_and_aspect(models):
    assert models.post("/api/v2/scenes3d", json={"objects": [{"tvar": "kvadr", "rozmery": [1, 1, 1],
                                                              "misto": [1]}]}).status_code == 422
    assert models.post("/api/v2/scenes3d", json={"aspect": "5:1", "objects": []}).status_code == 400


def test_render_under_lock_reuses_file_and_figure_only_on_request(models, settings):
    models.post("/api/v2/scenes3d", json=harbour())
    base = "/api/v2/scenes3d/lod-u-mola/v1"
    r = models.post(f"{base}/render", json={"camera": CAM})
    assert r.status_code == 202, r.text
    job = wait(models, r.json()["job_id"])
    assert job["status"] == "done", job["error"]
    key = r.json()["key"]
    call = [c for c in trace(settings) if "--scene" in c["args"]][-1]
    assert call["lock"] and "--cpu" in call["args"]
    spec = json.loads(Path(call["args"][call["args"].index("--scene") + 1]).read_text(encoding="utf-8"))
    assert [o["id"] for o in spec["objects"]] == ["lod", "molo", "amfora", "amfora-2"]   # no figure by default
    assert spec["objects"][0]["rozmer"] == 45 and spec["objects"][0]["glb"].endswith("model.glb")
    assert spec["objects"][1] | {} == {"id": "molo", "misto": [4, 1], "otoceni": 0, "na": None,
                                       "kind": "kvadr", "rozmery": [30, 6, 1.5]}
    assert spec["size"] == [1600, 1000] and spec["camera"] == CAM
    assert models.get(f"{base}/files/snaps/{key}.png").content[:4] == b"\x89PNG"
    assert models.get(base).json()["snaps"][0]["key"] == key
    # the same still again: no second job; with the figure: a new still with the figure on the pier
    assert models.post(f"{base}/render", json={"camera": CAM}).json() == {
        "key": key, "job_id": None, "file": f"snaps/{key}.png"}
    fig = models.post(f"{base}/render", json={"camera": CAM, "postava": True, "aspect": "1:1"}).json()
    assert fig["key"] != key and wait(models, fig["job_id"])["status"] == "done"
    spec = json.loads(Path([c for c in trace(settings) if "--scene" in c["args"]][-1]["args"][1]).read_text(encoding="utf-8"))
    assert spec["objects"][-1]["id"] == "postava" and spec["objects"][-1]["rozmer"] == 1.72
    assert spec["objects"][-1]["na"] == "molo" and Path(spec["objects"][-1]["glb"]) == sc.FIGURE_GLB
    assert spec["size"] == [1600, 1600]


def test_empty_still_is_an_error(models, settings, monkeypatch):
    models.post("/api/v2/scenes3d", json=harbour())
    monkeypatch.setenv("FAKE_BLENDER_MODE", "empty")
    r = models.post("/api/v2/scenes3d/lod-u-mola/v1/render", json={"camera": CAM}).json()
    job = wait(models, r["job_id"])
    assert job["status"] == "failed" and "mimo záběr" in job["error"]
    assert not list((settings.library_dir / "scenes3d" / "lod-u-mola" / "v1" / "snaps").glob("*.png"))


def test_ref_only_with_every_model_checked_and_with_the_size_sentence(models):
    models.post("/api/v2/scenes3d", json=harbour())
    base = "/api/v2/scenes3d/lod-u-mola/v1"
    key = models.post(f"{base}/render", json={"camera": CAM}).json()
    wait(models, key["job_id"])
    models.post("/api/v2/models3d/lod/v1/review", json={"reviewed": True})
    r = models.get(f"{base}/as-ref?snap={key['key']}")
    assert r.status_code == 409 and "Amfora (amfora v1)" in r.json()["detail"]
    models.post("/api/v2/models3d/amfora/v1/review", json={"reviewed": True})
    ref = models.get(f"{base}/as-ref?snap={key['key']}").json()
    assert ref["role"] == "geometry" and Path(ref["path"]).name == f"{key['key']}.png"
    assert "Loď, Molo, Amfora" in ref["source"]
    assert ref["hint"]["cs"] == "měřítko: člověk 1,72 m, Loď 45 m (asi 26× výška člověka), Amfora 0,7 m; postavy nezvětšuj"
    assert ref["hint"]["en"].startswith("a person is 1.72 m tall, about 1/26 of the Loď (45 m)")
    assert models.get(f"{base}/as-ref?snap=snap-0000000000").status_code == 404


def test_figure_asset_is_172_m():
    import struct
    raw = sc.FIGURE_GLB.read_bytes()
    n = struct.unpack("<I", raw[12:16])[0]
    gltf = json.loads(raw[20:20 + n])
    pos = next(a for a in gltf["accessors"] if "max" in a and len(a["max"]) == 3)
    assert abs(pos["max"][1] - pos["min"][1] - 1.72) < 0.005   # glTF Y up
