"""Vrstvy objektů v generované ilustraci (engine/objekty.py): offline, Claude a SAM-3 podstrčené, FLUX = fake sd-server."""
from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from engine import objekty
from engine.app import create_app
from engine.backends import FluxLocal, NanoBananaPro
from tests.test_engine_v2 import FakeSd, free_port, wait_done  # noqa: F401  (fixtures below reuse them)
from tests.test_engine_v2 import sd, settings  # noqa: F401


def _ellipse(size, box_px):
    m = Image.new("L", size, 0)
    x0, y0, x1, y1 = box_px
    ImageDraw.Draw(m).ellipse([x0 + 4, y0 + 4, x1 - 4, y1 - 4], fill=255)
    return m


@pytest.fixture
def calls():
    return {"find": 0, "segment": []}


@pytest.fixture
def api(settings, sd, monkeypatch, calls):  # noqa: F811
    def find(png, brief):
        calls["find"] += 1
        return [{"cs": "maják", "en": "lighthouse", "box": [100, 100, 600, 300]},
                {"cs": "loď", "en": "boat", "box": [500, 550, 900, 950]}]

    def segment(png, box, text=None):
        calls["segment"].append((box, text))
        size = Image.open(BytesIO(png)).size
        return _ellipse(size, box), 0.9

    monkeypatch.setattr(objekty, "claude_find", find)
    monkeypatch.setattr(objekty, "sam_segment", segment)
    app = create_app(settings, backends={"flux-local": FluxLocal(settings, sd), "nb-pro": NanoBananaPro()}, server=sd)
    with TestClient(app) as c:
        yield c


def _image(api):
    r = api.post("/api/v2/images", json={"prompt": "lighthouse and a boat", "size": "512x256", "seed": 3})
    job = wait_done(api, r.json()["job_id"])
    assert job["status"] == "done", job["error"]
    return f"{job['job_id']}/0"


def _url(ref, tail=""):
    job, n = ref.split("/")
    return f"/api/v2/jobs/{job}/images/{n}/objekty{tail}"


def _layers(api, ref, calls):
    r = api.post(_url(ref), json={})
    assert r.status_code == 402 and r.json()["estimate_usd"] == objekty.Objekty.find_usd()
    assert calls["find"] == 0 and calls["segment"] == []
    r = api.post(_url(ref), json={"confirm_cost": True})
    assert r.status_code == 201, r.text
    doc = r.json()
    plate_job = doc["ulohy"][0]["job"]
    assert wait_done(api, plate_job)["status"] == "done"
    return api.get(_url(ref)).json()


def test_plate_and_layers_in_place_give_the_original():
    """Podklad + vrstvy na místě se od originálu liší nejvýš v úzkém prstenci kolem objektu (plocha podkladu)."""
    rng = np.random.default_rng(1)
    orig = Image.fromarray(rng.integers(0, 255, (300, 400, 3), dtype=np.uint8))
    masks = [_ellipse(orig.size, (40, 40, 160, 200)), _ellipse(orig.size, (200, 120, 380, 290))]
    noise = Image.fromarray(rng.integers(0, 255, (300, 400, 3), dtype=np.uint8))
    plate = Image.composite(noise, orig, objekty.plate_mask(masks, orig.size))     # jako engine/paste.py
    out = objekty.compose(plate, [(objekty.cut_layer(orig, m), (0, 0)) for m in masks])
    diff = np.abs(np.asarray(orig, dtype=np.int16) - np.asarray(out, dtype=np.int16)).max(axis=2) > 8
    objects = np.asarray(objekty.plate_mask(masks, orig.size)) > 0
    inner = np.zeros_like(objects)
    for m in masks:
        inner |= np.asarray(m) > 127
    assert not diff[~objects].any(), "mimo plochu podkladu musí zůstat originál"
    assert not diff[inner].any(), "objekt sám je z originálu"
    assert objekty.check(orig, out)["changed_share"] < 0.05
    moved = objekty.compose(plate, [(objekty.cut_layer(orig, masks[0]), (60, 0))])
    assert objekty.check(orig, moved)["changed_share"] > 0.05


def test_pick_mask_takes_the_instance_near_the_box():
    size = (400, 300)
    left, right = _ellipse(size, (20, 20, 120, 120)), _ellipse(size, (250, 150, 380, 280))
    assert objekty.pick_mask([left, right], (240, 160, 390, 290)) == 1
    assert objekty.pick_mask([left, right], (20, 130, 120, 160)) == 0      # bez překryvu: nejbližší střed
    assert objekty.pick_mask([Image.new("L", size, 0)], (0, 0, 10, 10)) is None


def test_parse_found_keeps_valid_items_only():
    text = ('Here: [{"cs": "maják", "en": "lighthouse", "box": [10, 20, 500, 300]}, {"cs": "", "en": "x", "box": [1, 1, 2, 2]},'
            ' {"cs": "racek", "en": "gull", "box": [500, 0, 100, 10]}, {"cs": "loď", "en": "boat", "box": [1.4, 2, 3, 4]}]')
    assert objekty.parse_found(text) == [{"cs": "maják", "en": "lighthouse", "box": [10, 20, 500, 300]},
                                         {"cs": "loď", "en": "boat", "box": [1, 2, 3, 4]}]
    with pytest.raises(objekty.ObjektyError):
        objekty.parse_found("nic")


def test_find_layers_plate_hide_move_and_save(api, calls):
    ref = _image(api)
    doc = _layers(api, ref, calls)
    assert calls["find"] == 1 and len(calls["segment"]) == 2      # jedno volání SAM na objekt
    assert [text for _, text in calls["segment"]] == ["lighthouse", "boat"]     # podle slova, rámeček jen vybírá výskyt
    assert [o["nazev"] for o in doc["objects"]] == ["maják", "loď"]
    assert doc["podklad"] and doc["podklad"]["objekty"] == ["o1", "o2"]
    layer = Image.open(BytesIO(api.get(doc["objects"][0]["vrstva_url"]).content))
    assert layer.mode == "RGBA" and layer.size == (512, 256)
    assert api.get(_url(ref, "/soubor/..%2Fobjekty.json")).status_code == 404
    check = api.get(_url(ref, "/kontrola")).json()
    assert check["changed_share"] < 0.05, check        # jen úzký prstenec kolem objektů (fake FLUX kreslí jiný obraz)

    assert api.patch(_url(ref, "/o1"), json={"viditelny": False}).status_code == 200
    assert api.patch(_url(ref, "/o2"), json={"posun": [-40, 0]}).json()["objects"][1]["posun"] == [-40, 0]
    r = api.post(_url(ref, "/hotovo"))
    assert r.status_code == 201, r.text
    new = r.json()["ref"]
    prov = api.get(f"/api/v2/jobs/{new.replace('/', '/images/')}/provenance").json()
    assert prov["objekty_of"] == ref and prov["ai_generated"] is True and prov["vectorcraft_svg"]
    assert [o["viditelny"] for o in prov["objekty"]] == [False, True]
    svg = (api.get(f"/api/v2/jobs/{new.split('/')[0]}").json()["result"]["files"][0]).replace(".png", ".svg")
    text = open(svg, encoding="utf-8").read()
    assert '<g id="Podklad">' in text and '<g id="o2"' in text and '<g id="o1"' not in text

    # nové hledání by zahodilo podklad
    assert api.post(_url(ref), json={"confirm_cost": True}).status_code == 400


def test_change_object_is_paid_and_adds_a_version(api, calls):
    ref = _image(api)
    _layers(api, ref, calls)
    r = api.post(_url(ref, "/o2/zmenit"), json={"instruction": "plachetnice s bílou plachtou"})
    assert r.status_code == 402 and r.json()["estimate_usd"] == round(objekty.SAM_USD + 0.01, 4)
    r = api.post(_url(ref, "/o2/zmenit"), json={"instruction": "plachetnice s bílou plachtou", "confirm_cost": True})
    assert r.status_code == 202
    assert wait_done(api, r.json()["job_id"])["status"] == "done"
    o2 = api.get(_url(ref)).json()["objects"][1]
    assert len(o2["verze"]) == 2 and o2["verze"][1]["pokyn"] == "plachetnice s bílou plachtou"
    assert o2["vrstva_url"].endswith("vrstva-o2-v2.png")
    assert api.post(_url(ref, "/o9/zmenit"), json={"instruction": "x", "confirm_cost": True}).status_code == 404


def test_add_by_box_marks_plate_stale(api, calls):
    ref = _image(api)
    _layers(api, ref, calls)
    r = api.post(_url(ref, "/pridat"), json={"box": [0, 700, 200, 900], "nazev": "racek"})
    assert r.status_code == 402
    r = api.post(_url(ref, "/pridat"), json={"box": [0, 700, 200, 900], "nazev": "racek", "confirm_cost": True})
    doc = r.json()
    assert doc["objects"][-1]["nazev"] == "racek" and doc["podklad"]["zastaraly"] is True
    assert calls["segment"][-1][1] is None          # rámeček operátora je přesný: obtáhne se to, co je v něm


def test_done_without_plate_is_refused_and_api_rejects_edit_mask(api, calls, monkeypatch):
    ref = _image(api)
    assert api.get(_url(ref)).json()["objects"] == []
    assert api.post(_url(ref, "/hotovo")).status_code == 404
    r = api.post("/api/v2/images", json={"prompt": "-", "parent": ref, "edit": {
        "action": "remove", "bbox": [0, 0, 500, 500], "instruction": "x", "mask": "C:/Windows/win.ini"}})
    assert r.status_code == 400
