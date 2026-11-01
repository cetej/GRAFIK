"""Popis stavby z dílů: co model nesmí dostat do Blenderu, a skutečná stavba Pantheonu (přeskočí se bez Blenderu)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from ngm_shared.heavy_lock import HeavyBusy, heavy
from PIL import Image

from engine.config import Settings
from engine.parts_spec import SpecError, validate

REPO = Path(__file__).resolve().parents[1]
PANTHEON = REPO / "scripts" / "3d" / "dily" / "pantheon.json"
RING = {"typ": "prstenec", "nazev": "zed", "osy": [10, 8], "profil": [[-1, 0], [0, 0], [0, 5], [-1, 5]]}


def spec(*parts) -> dict:
    return {"dim": {"length": 20, "width": 16, "height": 5}, "dily": list(parts)}


def test_pantheon_example_is_valid():
    out = validate(json.loads(PANTHEON.read_text(encoding="utf-8")))
    assert {p["typ"] for p in out["dily"]} == {"prstenec", "disk", "kopule", "arkady", "kvadr", "vyrez", "portik"}
    assert out["dim"]["height"] == 48.7


def test_unknown_fields_do_not_reach_blender():
    out = validate(spec({**RING, "skript": "import os", "material": "travertin"}))
    assert "skript" not in out["dily"][0]


@pytest.mark.parametrize("bad, message", [
    (spec({**RING, "typ": "python"}), "neznámý typ"),
    (spec({**RING, "nazev": "../zed"}), "nazev"),
    (spec(RING, RING), "opakuje"),
    (spec({**RING, "profil": [[0, 0], [1, 1]]}), "profil"),
    (spec({**RING, "profil": [[-11, 0], [0, 0], [0, 5]]}), "přes střed"),
    (spec({**RING, "profil": [[0, 0], [1, "x"], [2, 2]]}), "není číslo"),
    (spec({**RING, "profil": [[0, 0], [float("nan"), 1], [2, 2]]}), "není číslo"),
    (spec({**RING, "material": "zlato"}), "material"),
    (spec({"typ": "arkady", "nazev": "a", "cil": "neni", "odsazeni": [0, 1], "vyska": 3, "sirka": 2, "pocet": 8}), "plný díl"),
    (spec(RING, {"typ": "arkady", "nazev": "a", "cil": "zed", "odsazeni": [0, 1], "vyska": 3, "sirka": 2, "pocet": 100000}), "celé číslo"),
    (spec(RING, {"typ": "arkady", "nazev": "a", "cil": "zed", "odsazeni": [0, 1], "vyska": 3, "sirka": 2, "pocet": 8, "tvar": "hvezda"}), "tvar"),
    (spec(RING, {"typ": "vyrez", "nazev": "v", "cile": ["zed"], "azimut": [0, 400], "z": [0, 1]}), "celý kruh"),
    (spec({"typ": "kvadr", "nazev": "k", "od": [0, 0, 0], "do": [0, 1, 1]}), "od < do"),
    (spec({"typ": "kopule", "nazev": "k", "polomer": 5, "tloustka": [1, 1], "z_patka": 1, "okulus": 9}), "okulus"),
    ({"dily": [RING]}, "length"),
    ({"dim": {"length": 1, "width": 1, "height": 1}, "dily": []}, "žádné díly"),
    ({"dim": {"length": 1, "width": 1, "height": 1}, "dily": [dict(RING, nazev=f"d{i}") for i in range(81)]}, "nejvýš"),
])
def test_bad_description_says_what_is_wrong(bad, message):
    with pytest.raises(SpecError, match=message):
        validate(bad)


def test_anchors_are_named_points_of_the_model():
    out = validate({**spec(RING), "kotvy": [{"nazev": "okulus", "xyz": [0, 0, 5], "dil": "zed", "skript": "x"}]})
    assert out["kotvy"] == [{"nazev": "okulus", "xyz": [0.0, 0.0, 5.0], "dil": "zed"}]
    assert validate(spec(RING))["kotvy"] == []


@pytest.mark.parametrize("anchors, message", [
    ("okulus", "seznam"),
    ([{"nazev": "../x", "xyz": [0, 0, 0]}], "nazev"),
    ([{"nazev": "zed", "xyz": [0, 0, 0]}], "opakuje"),
    ([{"nazev": "a", "xyz": [0, 0]}], "tři čísla"),
    ([{"nazev": "a", "xyz": [0, 0, "x"]}], "není číslo"),
    ([{"nazev": "a", "xyz": [0, 0, 0], "dil": "neni"}], "v popisu není"),
])
def test_bad_anchor_says_what_is_wrong(anchors, message):
    with pytest.raises(SpecError, match=message):
        validate({**spec(RING), "kotvy": anchors})


def test_cut_only_a_solid_declared_before():
    columns = {"typ": "sloupy", "nazev": "s", "d": 1, "drik": 4, "pocet": 4, "osy": [10, 8]}
    with pytest.raises(SpecError, match="plný díl"):
        validate(spec(columns, {"typ": "vyrez", "nazev": "v", "cile": ["s"], "azimut": [0, 90], "z": [0, 1]}))


def real_blender(script: str, *args: str) -> None:
    blender = Settings().blender_cmd[0]
    if not Path(blender).is_file():
        pytest.skip("Blender není nainstalovaný")
    try:
        with heavy("blender", owner="grafik-test", caller="test dílů", wait_s=30):
            run = subprocess.run([blender, "-b", "--factory-startup", "-P", str(REPO / "engine" / "blender" / script), "--", *args],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
    except HeavyBusy as e:
        pytest.skip(f"zámek těžké práce je obsazený: {e}")
    assert run.returncode == 0, run.stderr[-800:]


def test_real_blender_renders_parts_with_anchors_and_layers(tmp_path):
    clean = tmp_path / "spec.json"
    source = json.loads(PANTHEON.read_text(encoding="utf-8"))
    clean.write_text(json.dumps(validate({**source, "kotvy": [{"nazev": "okulus", "xyz": [0, 0, 44], "dil": "kupole"}, {"nazev": "uvnitr", "xyz": [0, 0, 8]}]})), encoding="utf-8")
    groups = {"stavba": ["zaklad", "podlaha", "zed", "stupne", "kupole", "blok"], "portik": ["portik"]}
    request = {"pohled": "celek", "res": [240, 135], "samples": 8, "cpu": True, "vrstvy": True, "skupiny": groups, "posuny": {"kupole": 10}}
    real_blender("render_parts.py", str(clean), str(tmp_path), json.dumps(request))
    body = json.loads((tmp_path / "body.json").read_text(encoding="utf-8"))
    assert body["res"] == [240, 135] and body["vrstvy"] == groups
    assert set(groups["stavba"]) | {"portik", "okulus", "uvnitr"} == set(body["points"])
    assert "okulus" in body["viditelne"] and "uvnitr" not in body["viditelne"]      # bod uvnitř stavby kamera nevidí
    assert all(0 <= x <= 240 and 0 <= y <= 135 for x, y in body["points"].values())
    full, portico = Image.open(tmp_path / "obraz.png"), Image.open(tmp_path / "vrstva-portik.png")
    assert full.size == (240, 135) and full.mode == "RGBA"
    assert 0 < sum(portico.getchannel("A").histogram()[128:]) < sum(full.getchannel("A").histogram()[128:])


def test_real_blender_builds_named_parts(tmp_path):
    clean = tmp_path / "spec.json"
    clean.write_text(json.dumps(validate(json.loads(PANTHEON.read_text(encoding="utf-8")))), encoding="utf-8")
    glb = tmp_path / "model.glb"
    real_blender("lod_parts.py", str(glb), str(clean))
    report = json.loads(Path(f"{glb}.dily.json").read_text(encoding="utf-8"))
    assert set(report["dily"]) == {"zaklad", "podlaha", "zed", "stupne", "kupole", "blok", "portik"}     # řezy nejsou díly
    assert report["bez_kontaktu"] == []
    lo, hi = report["dily"]["kupole"]["bbox"]
    assert hi[2] == pytest.approx(44.0, abs=0.3) and lo[0] == pytest.approx(-27.85, abs=0.1)
