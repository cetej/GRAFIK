"""Opotřebení v TextureCraftu (engine/texturecraft.py): kroky dávky ze složení GLB a úloha Engine s falešným CLI."""
from __future__ import annotations

import io
import json
import struct
from pathlib import Path

import pytest
from PIL import Image

from engine import texturecraft as tc
from tests.test_models3d import api, settings, upload, wait  # noqa: F401  (fixtures)


def make_glb(materials: list[dict], images: list[bytes] = ()) -> bytes:
    binc, views = b"", []
    for data in images:
        views.append({"buffer": 0, "byteOffset": len(binc), "byteLength": len(data)})
        binc += data + b"\x00" * (-len(data) % 4)
    g = {"asset": {"version": "2.0"}, "materials": materials, "bufferViews": views,
         "images": [{"bufferView": i, "mimeType": "image/png"} for i in range(len(images))],
         "textures": [{"source": i} for i in range(len(images))], "buffers": [{"byteLength": len(binc)}]}
    js = json.dumps(g).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(binc), 0x004E4942) + binc
    return b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body


def png(size=(8, 8), color=(10, 200, 50)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def ids(steps):
    return [s["id"] for s in steps]


def test_factor_materials_get_base_layer_and_metal_gets_edge_wear(tmp_path):
    g, binc = tc.read_glb(make_glb([
        {"name": "steel", "pbrMetallicRoughness": {"baseColorFactor": [0.2, 0.2, 0.2, 1], "roughnessFactor": 0.4}},
        {"name": "ebonite", "pbrMetallicRoughness": {"baseColorFactor": [0.05, 0.05, 0.05, 1], "metallicFactor": 0}},
    ]))
    steps = tc.build_steps(g, binc, tmp_path, "jemne", True, True)
    assert ids(steps)[0] == "bake.run" and ids(steps)[-2:] == ["file.exportTextures", "file.exportMesh"]
    fills = [s["params"] for s in steps if s["id"] == "layer.add.fill"]
    assert [f["name"] for f in fills] == ["zaklad", "odreni_hran", "spina", "zaklad", "spina"]
    assert fills[0]["color"] == "#7c7c7c" and fills[0]["metallic"] == 1.0   # lineární 0,2 → sRGB
    assert {s["params"]["opacity"] for s in steps if s["id"] == "layer.blend"} == {0.35}
    gens = [s["params"]["generator"] for s in steps if s["id"] == "effect.add.generator"]
    assert gens == ["edgeWear", "dirt", "dirt"]


def test_textured_material_imports_its_images_by_full_file_name(tmp_path):
    mr = png(color=(0, 180, 255))   # G = drsnost, B = kovovost
    g, binc = tc.read_glb(make_glb([{"name": "body", "pbrMetallicRoughness": {
        "baseColorTexture": {"index": 0}, "metallicRoughnessTexture": {"index": 1}}}], [png(), mr]))
    steps = tc.build_steps(g, binc, tmp_path, "stredni", True, False)
    image = next(s for s in steps if s["id"] == "layer.add.image")["params"]
    assert image["name"] == "m0_basecolor.png" and (tmp_path / "m0_basecolor.png").is_file()
    sets = {s["params"]["channel"]: s["params"]["image"] for s in steps if s["id"] == "layer.fill.set"}
    assert sets == {"roughness": "m0_roughness.png", "metallic": "m0_metallic.png"}
    assert Image.open(tmp_path / "m0_roughness.png").getpixel((0, 0)) == 180
    assert "edgeWear" not in json.dumps(steps)   # kov v textuře nejde odlišit od látky


def test_big_texture_keeps_4096_sets():
    g, binc = tc.read_glb(make_glb([{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}], [png((3000, 8))]))
    assert tc.resolution(g, binc) == 4096
    g, binc = tc.read_glb(make_glb([{"pbrMetallicRoughness": {}}]))
    assert tc.resolution(g, binc) == 2048


def test_bad_strength_is_refused(tmp_path):
    g, binc = tc.read_glb(make_glb([{"pbrMetallicRoughness": {}}]))
    with pytest.raises(tc.TextureCraftError):
        tc.build_steps(g, binc, tmp_path, "maximalni", True, True)


@pytest.fixture
def fake_tc(monkeypatch, tmp_path):
    cli = tmp_path / "craft" / "texturecraft" / "texturecraft-cli.exe"
    cli.parent.mkdir(parents=True)
    cli.write_bytes(b"")
    monkeypatch.setenv("CRAFT_HOME", str(tmp_path / "craft"))
    calls = []

    def run(src, work, sila, spina, hrany, timeout_s=0):
        calls.append({"src": Path(src).name, "sila": sila, "spina": spina, "hrany": hrany})
        work.mkdir(parents=True, exist_ok=True)
        (work / "model.glb").write_bytes(Path(src).read_bytes())
        return {"glb": work / "model.glb", "resolution": 2048, "materials": 1, "tracer": ["GPU (fake)"],
                "version": "TextureCraft fake"}

    monkeypatch.setattr(tc, "run", run)
    return calls


def test_opotrebeni_makes_new_version_with_colour_preview(api, fake_tc):
    wait(api, upload(api)["job_id"])
    r = api.post("/api/v2/models3d/tatra-87/v1/opotrebeni", json={"sila": "silne", "hrany": False})
    assert r.status_code == 202, r.text
    job = wait(api, r.json()["job_id"])
    assert job["status"] == "done", job["error"]
    assert wait(api, job["result"]["viewer_job"])["status"] == "done"
    v2 = api.get("/api/v2/models3d/tatra-87").json()["versions"][1]
    assert (v2["method"], v2["parent"], v2["status"]) == ("texturecraft", "v1", "ready")
    assert v2["opotrebeni"]["sila"] == "silne" and v2["opotrebeni"]["hrany"] is False
    assert v2["opotrebeni"]["nahled"] == ["nahled/pred-0.png", "nahled/pred-1.png", "nahled/po-0.png", "nahled/po-1.png"]
    assert api.get("/api/v2/models3d/tatra-87/v2/files/nahled/po-0.png").status_code == 200
    assert fake_tc == [{"src": "model.glb", "sila": "silne", "spina": True, "hrany": False}]


def test_opotrebeni_refuses_bad_input_and_missing_install(api, fake_tc, monkeypatch, tmp_path):
    wait(api, upload(api)["job_id"])
    assert api.post("/api/v2/models3d/tatra-87/v1/opotrebeni", json={"sila": "x"}).status_code == 400
    assert api.post("/api/v2/models3d/tatra-87/v1/opotrebeni", json={"spina": False, "hrany": False}).status_code == 400
    monkeypatch.setenv("CRAFT_HOME", str(tmp_path / "nikde"))
    assert api.post("/api/v2/models3d/tatra-87/v1/opotrebeni", json={}).status_code == 503
    assert len(api.get("/api/v2/models3d/tatra-87").json()["versions"]) == 1
