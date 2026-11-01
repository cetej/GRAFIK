"""Popis stavby z dílů: co model nesmí dostat do Blenderu, a skutečná stavba Pantheonu (přeskočí se bez Blenderu)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from ngm_shared.heavy_lock import HeavyBusy, heavy
from PIL import Image

from engine.config import Settings
from engine.parts_spec import DECOR, MAX_PARTS, SpecError, validate

REPO = Path(__file__).resolve().parents[1]
PANTHEON = REPO / "scripts" / "3d" / "dily" / "pantheon.json"
KOLOSEUM = REPO / "scripts" / "3d" / "dily" / "koloseum.json"
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
    ({"dim": {"length": 1, "width": 1, "height": 1}, "dily": [dict(RING, nazev=f"d{i}") for i in range(MAX_PARTS + 1)]}, "nejvýš"),
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


def test_cut_surface_is_a_known_material():
    arches = {"typ": "ochoz", "nazev": "o", "cile": ["zed"], "osy": [10, 8], "od": -1, "do": -0.5, "z0": 0, "vyska": 3}
    assert validate(spec(RING, {**arches, "povrch": "omitka"}))["dily"][1]["povrch"] == "omitka"
    with pytest.raises(SpecError, match="povrch"):
        validate(spec(RING, {**arches, "povrch": "zlato"}))


def test_vault_and_stairs_are_cuts_of_solids():
    vault = {"typ": "ochoz", "nazev": "o", "cile": ["zed"], "osy": [10, 8], "od": -1, "do": -0.5, "z0": 0, "vyska": 3, "skript": "x"}
    stairs = {"typ": "schodiste", "nazev": "s", "cile": ["zed"], "osy": [10, 8], "od": -1, "do": 0, "z0": 0, "z1": 3, "sirka": 1, "pocet": 4}
    out = validate(spec(RING, vault, stairs))
    assert out["dily"][1]["tvar"] == "oblouk" and "skript" not in out["dily"][1]
    assert out["dily"][2]["pruchod"] == 2.5 and out["dily"][2]["stupnu"] == 12


@pytest.mark.parametrize("part, message", [
    ({"typ": "ochoz", "nazev": "o", "osy": [10, 8], "od": -1, "do": 0, "z0": 0, "vyska": 3}, "cile"),
    ({"typ": "ochoz", "nazev": "o", "cile": ["zed"], "osy": [10, 8], "od": 0, "do": -1, "z0": 0, "vyska": 3}, "menší"),
    ({"typ": "ochoz", "nazev": "o", "cile": ["neni"], "osy": [10, 8], "od": -1, "do": 0, "z0": 0, "vyska": 3}, "plný díl"),
    ({"typ": "ochoz", "nazev": "o", "cile": ["zed"], "osy": [10, 8], "od": -1, "do": 0, "z0": 0, "vyska": 3, "tvar": "hvezda"}, "tvar"),
    ({"typ": "schodiste", "nazev": "s", "cile": ["zed"], "osy": [10, 8], "od": -1, "do": 0, "z0": 0, "z1": 3, "sirka": 1, "pocet": 100000}, "celé číslo"),
])
def test_bad_vault_or_stairs_say_what_is_wrong(part, message):
    with pytest.raises(SpecError, match=message):
        validate(spec(RING, part))


def test_cut_only_a_solid_declared_before():
    columns = {"typ": "sloupy", "nazev": "s", "d": 1, "drik": 4, "pocet": 4, "osy": [10, 8]}
    with pytest.raises(SpecError, match="plný díl"):
        validate(spec(columns, {"typ": "vyrez", "nazev": "v", "cile": ["s"], "azimut": [0, 90], "z": [0, 1]}))


def test_colosseum_example_is_valid_and_labels_invented_things():
    out = validate(json.loads(KOLOSEUM.read_text(encoding="utf-8")))
    assert out["dim"] == {"length": 188.0, "width": 155.5, "height": 48.5}
    assert {p["typ"] for p in out["dily"]} >= set(DECOR)
    assert "vymyšlené" in out["zdroje"]["plachty a lidé"]       # oživení obrazu se nesmí tvářit jako pramen
    assert any(p.get("okoli") for p in out["dily"])


ROW = {"typ": "rada", "nazev": "pricky", "od": [1, 1, -6], "do": [1.5, 5, 0], "krok": [2, 0, 0], "pocet": 5, "zrcadlo": ["x", "y"]}
WALLS = {"typ": "pricky", "nazev": "steny", "osy": [10, 8], "profil": [[-3, 0], [0, 0], [0, 4]], "pocet": 8, "tloustka": 0.5}
OPENINGS = {"typ": "otvory", "nazev": "dvere", "cile": ["zed"], "stred": [0, 8, 0], "smer": "y", "sirka": 1, "vyska": 2, "hloubka": 3}
CAVITY = {"typ": "dutina", "nazev": "dutina", "cile": ["zed"], "osy": [10, 8], "profil": [[-1, 1], [0, 1], [0, 2]]}
STATUES = {"typ": "sochy", "nazev": "sochy", "osy": [10, 8], "pocet": 8, "z0": 1, "vyska": 2}
PEOPLE = {"typ": "lide", "nazev": "lide", "osy": [10, 8], "od": -5, "do": -1, "z0": 0, "pocet": 20}
SAILS = {"typ": "plachty", "nazev": "plachty", "osy": [10, 8], "od": -5, "do": 0, "z_dov": 4, "z_ven": 6, "azimut": [0, 60], "pocet": 4}
LIFTS = {"typ": "zdvihadla", "nazev": "vytahy", "stred": [1, 1], "z0": -6, "z1": 0, "sirka": 1, "delka": 1}


def test_new_kinds_reach_blender_with_known_fields_only():
    out = validate(spec(RING, ROW, WALLS, OPENINGS, CAVITY, STATUES, PEOPLE, SAILS, {**LIFTS, "skript": "x"}))
    parts = {p["nazev"]: p for p in out["dily"]}
    assert "skript" not in parts["vytahy"] and parts["vytahy"]["pocet"] == 1
    assert parts["lide"]["azimut"] == [[0.0, 360.0]] and parts["lide"]["vyska"] == 1.7
    assert parts["dvere"]["tvar"] == "oblouk" and parts["pricky"]["zrcadlo"] == ["x", "y"]
    two = validate(spec({**PEOPLE, "azimut": [[0, 40], [90, 120]]}))["dily"][0]
    assert two["azimut"] == [[0.0, 40.0], [90.0, 120.0]]


def test_arcade_axis_and_thin_seating_and_own_cut_face():
    arches = {"typ": "arkady", "nazev": "a", "cil": "zed", "osy": [10, 8], "odsazeni": [-1, 0], "vyska": 3, "sirka": 1, "pocet": 8, "ref": 0}
    assert validate(spec(RING, arches))["dily"][1]["ref"] == 0.0
    seats = {"typ": "hlediste", "nazev": "h", "osy": [10, 8], "od": -5, "do": -1, "z0": 1, "z1": 3, "stupnu": 4}
    assert "tloustka" not in validate(spec(seats))["dily"][0]
    assert validate(spec({**seats, "tloustka": 0.5}))["dily"][0]["tloustka"] == 0.5
    assert validate(spec({**RING, "rez": "tmava", "okoli": True}))["dily"][0]["rez"] == "tmava"


@pytest.mark.parametrize("part, message", [
    ({**ROW, "od": [2, 1, -6]}, "od < do"),
    ({**ROW, "zrcadlo": ["z"]}, "zrcadlo"),
    ({**WALLS, "profil": [[0, 0], [1, 1]]}, "profil"),
    ({**WALLS, "tloustka": 0}, "tloustka"),
    ({**OPENINGS, "smer": "z"}, "smer"),
    ({**OPENINGS, "tvar": "hvezda"}, "tvar"),
    ({**OPENINGS, "cile": ["neni"]}, "plný díl"),
    ({**CAVITY, "profil": [[-20, 1], [0, 1], [0, 2]]}, "přes střed"),
    ({**STATUES, "vyska": 100}, "vyska"),
    ({**PEOPLE, "od": -20}, "přes střed"),
    ({**PEOPLE, "pocet": 100000}, "celé číslo"),
    ({**PEOPLE, "azimut": [40, 10]}, "azimut"),
    ({**SAILS, "azimut": [0, 400]}, "azimut"),
    ({**SAILS, "lana": [10, 20]}, "lana"),
    ({**LIFTS, "z1": -7}, "z0 < z1"),
    ({**RING, "nazev": "r2", "rez": "cervena"}, "rez"),
])
def test_bad_new_kind_says_what_is_wrong(part, message):
    with pytest.raises(SpecError, match=message):
        validate(spec(RING, part))


def test_decor_cannot_be_cut():
    with pytest.raises(SpecError, match="plný díl"):
        validate(spec(STATUES, {**OPENINGS, "cile": ["sochy"]}))


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


def test_real_blender_reports_a_cut_that_removes_nothing(tmp_path):
    arches = {"typ": "arkady", "cil": "zed", "odsazeni": [-1.5, 0.5], "z0": 0.5, "vyska": 3, "sirka": 1, "pocet": 8}
    clean = tmp_path / "spec.json"
    clean.write_text(json.dumps(validate(spec({**RING, "osy": [10, 8]}, {**arches, "nazev": "dobre", "osy": [10, 8]}, {**arches, "nazev": "vedle", "osy": [0, 0]}))), encoding="utf-8")
    glb = tmp_path / "model.glb"
    real_blender("lod_parts.py", str(glb), str(clean))
    assert json.loads(Path(f"{glb}.dily.json").read_text(encoding="utf-8"))["rezy_bez_ucinku"] == ["vedle"]


def test_real_blender_cuts_vault_and_stairs(tmp_path):
    wall = {"typ": "prstenec", "nazev": "zed", "osy": [20, 16], "profil": [[-8, 0], [0, 0], [0, 12], [-8, 12]]}
    vault = {"typ": "ochoz", "nazev": "chodba", "cile": ["zed"], "osy": [20, 16], "od": -6, "do": -3, "z0": 0.5, "vyska": 5}
    stairs = {"typ": "schodiste", "nazev": "schody", "cile": ["zed"], "osy": [20, 16], "od": -8, "do": -1, "z0": 6, "z1": 9, "sirka": 1.5, "pocet": 4, "stupnu": 8}
    vedle = {"typ": "ochoz", "nazev": "vedle", "cile": ["zed"], "osy": [20, 16], "od": -6, "do": -3, "z0": 20, "vyska": 3}
    shafts = {"typ": "sachty", "nazev": "sachty", "cile": ["zed"], "osy": [20, 16], "odsazeni": -7, "pocet": 8, "sirka": 1, "delka": 1, "z": [11, 13]}
    clean = tmp_path / "spec.json"
    clean.write_text(json.dumps(validate({"dim": {"length": 40, "width": 32, "height": 12}, "dily": [wall, vault, stairs, vedle, shafts]})), encoding="utf-8")
    glb = tmp_path / "model.glb"
    real_blender("lod_parts.py", str(glb), str(clean))
    report = json.loads(Path(f"{glb}.dily.json").read_text(encoding="utf-8"))
    assert report["rezy_bez_ucinku"] == ["vedle"] and set(report["dily"]) == {"zed"}


def small_hollow_building() -> dict:
    """Všechny nové druhy na malé stavbě: dutá zeď, cely pod zemí, ozdoby a terén kolem."""
    wall = {"typ": "prstenec", "nazev": "zed", "osy": [20, 16], "profil": [[-8, 0], [0, 0], [0, 12], [-8, 12]], "material": "travertin"}
    ground = {"typ": "prstenec", "nazev": "terasa", "osy": [20, 16], "profil": [[0, -0.5], [6, -0.5], [6, 0], [0, 0]], "material": "travertin", "okoli": True}
    base = {"typ": "prstenec", "nazev": "zaklad", "osy": [20, 16], "profil": [[-8, -5], [0, -5], [0, 0], [-8, 0]], "material": "tuf", "rez": "tmava"}
    floor = {"typ": "disk", "nazev": "podlaha", "osy": [12, 8], "z0": -0.3, "z1": 0, "material": "drevo"}
    pit = {"typ": "disk", "nazev": "dno", "osy": [12, 8], "z0": -5, "z1": -4, "material": "beton"}
    return {"nazev": "věž", "dim": {"length": 40, "width": 32, "height": 12}, "kotvy": [{"nazev": "cela", "xyz": [2, 3, -3]}], "dily": [
        base, wall, ground, floor, pit,
        {"typ": "rada", "nazev": "cely", "od": [0.5, 1, -4], "do": [0.9, 6, -0.3], "krok": [2, 0, 0], "pocet": 4, "zrcadlo": ["x", "y"], "material": "cihla"},
        {"typ": "pricky", "nazev": "steny", "osy": [20, 16], "profil": [[-9, -0.2], [-8, -0.2], [-8, 6], [-9, 5]], "pocet": 12, "tloustka": 0.6, "material": "travertin"},
        {"typ": "otvory", "nazev": "tunel", "cile": ["zaklad"], "stred": [-15, 0, -4], "smer": "x", "sirka": 2, "vyska": 2.5, "hloubka": 12, "zrcadlo": ["x"]},
        {"typ": "otvory", "nazev": "vedle", "cile": ["zaklad"], "stred": [0, 0, 50], "smer": "x", "sirka": 2, "vyska": 2.5, "hloubka": 12},
        {"typ": "dutina", "nazev": "chodba", "cile": ["zed"], "osy": [20, 16], "profil": [[-5, 0.5], [-3, 0.5], [-3, 4], [-5, 3]]},
        {"typ": "sochy", "nazev": "sochy", "osy": [20, 16], "odsazeni": -1, "pocet": 16, "z0": 12, "vyska": 2, "material": "mramor"},
        {"typ": "sochy", "nazev": "aedikuly", "osy": [20, 16], "odsazeni": -8, "pocet": 16, "preskoc": 2, "aedikula": True, "z0": 6, "vyska": 2, "material": "mramor"},
        {"typ": "lide", "nazev": "lide", "osy": [20, 16], "od": 1, "do": 5, "z0": 0, "pocet": 30, "azimut": [[0, 90], [180, 270]]},
        {"typ": "plachty", "nazev": "plachty", "osy": [20, 16], "od": -9, "do": 0, "z_dov": 12, "z_ven": 15, "azimut": [10, 70], "pocet": 4, "prohyb": 0.5, "lana": [-20, 100]},
        {"typ": "zdvihadla", "nazev": "vytahy", "stred": [1.9, 3], "krok": [2, 0], "pocet": 3, "zrcadlo": ["x", "y"], "z0": -4, "z1": -0.3, "sirka": 1, "delka": 1, "material": "drevo"},
    ]}


def test_real_blender_builds_decor_outside_the_contact_check(tmp_path):
    clean = tmp_path / "spec.json"
    clean.write_text(json.dumps(validate(small_hollow_building())), encoding="utf-8")
    glb = tmp_path / "model.glb"
    real_blender("lod_parts.py", str(glb), str(clean))
    report = json.loads(Path(f"{glb}.dily.json").read_text(encoding="utf-8"))
    assert report["rezy_bez_ucinku"] == ["vedle"]
    assert {"sochy", "lide", "plachty", "vytahy", "cely", "steny", "aedikuly"} <= set(report["dily"])
    loose = {p["nazev"] for p in report["bez_kontaktu"]}
    assert not loose & set(DECOR) and not loose & {"sochy", "lide", "plachty", "vytahy", "aedikuly"}     # lidé na terase, plachty ve vzduchu
    lo, hi = report["dily"]["cely"]["bbox"]
    assert lo[0] == pytest.approx(-6.9, abs=0.01) and hi[0] == pytest.approx(6.9, abs=0.01)     # zrcadlo přes obě osy


def test_real_blender_renders_a_quarter_with_plinth_and_opened_floor(tmp_path):
    clean = tmp_path / "spec.json"
    clean.write_text(json.dumps(validate(small_hollow_building())), encoding="utf-8")
    request = {"pohled": "ctvrt", "res": [320, 200], "samples": 8, "cpu": True, "rez": "cerna", "sokl": {"z": 1.0, "pas": 5}, "odkryv": [{"dily": ["podlaha"], "azimut": [-225, -25]}]}
    real_blender("render_parts.py", str(clean), str(tmp_path), json.dumps(request))
    body = json.loads((tmp_path / "body.json").read_text(encoding="utf-8"))
    assert "cela" in body["points"] and "podlaha" in body["points"]
    box = Image.open(tmp_path / "obraz.png").getchannel("A").getbbox()
    assert box[2] - box[0] > 0.8 * 320 or box[3] - box[1] > 0.8 * 200     # záběr sedí na vrcholy, ne na rohy kvádrů kolem elipsy


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
