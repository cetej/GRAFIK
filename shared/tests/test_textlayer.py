"""Vrstva textu (`ngm_shared.textlayer`): pravidla, rozložení, pozadí, geometrie skládání a kontroly.

Testy jsou kopie z NG-ROBOT `tests/test_ng_vector_labels.py` (commit f27580e9) pro zkopírované moduly;
soubory článku, návrh modelem a zeměpisné polohy zůstaly v NG-ROBOT. Skutečný VectorCraft je těžká
práce (až ~1,2 GB paměti grafiky), holé `pytest` ho nespouští: `GRAFIK_VECTORCRAFT_TESTS=1`.
"""

import os
import sys

import pytest
from PIL import Image

from ngm_shared.heavy_lock import HeavyBusy, HeavyLock, read_lock
from ngm_shared.textlayer import checks
from ngm_shared.textlayer import compose as comp_mod
from ngm_shared.textlayer import layout as lay_mod
from ngm_shared.textlayer import style as st
from ngm_shared.textlayer.raster import COAST, LAND, WATER, Base
from ngm_shared.textlayer.vc_client import VectorCraft, VectorCraftError, find_cli

OCEAN = (20, 50, 110)
ROCK = (120, 100, 70)


def _half(path, size=(400, 300)):
    """Levá polovina oceán, pravá pevnina."""
    im = Image.new("RGB", size, ROCK)
    im.paste(OCEAN, (0, 0, size[0] // 2, size[1]))
    im.save(path)
    return path


@pytest.fixture
def base_png(tmp_path):
    return _half(tmp_path / "base.png")


# ------------------------------------------------------------------ style

def test_contrast_bounds():
    assert st.contrast("#FFFFFF", "#000000") == pytest.approx(21.0)
    assert st.contrast("#777777", "#777777") == pytest.approx(1.0)


def test_pick_text_color_prefers_water_tone_on_dark_sea_and_dark_tone_on_ice():
    assert st.pick_text_color("ocean", OCEAN) == st.WATER_TEXT
    assert st.pick_text_color("ocean", (232, 243, 247)) == st.WATER_TEXT_DARK


def test_halo_separates_text_from_background():
    light_text_halo = st.halo_color(st.WHITE, ROCK)
    assert st.luminance(st.hex_to_rgb(light_text_halo)) < st.luminance(ROCK)
    dark_text_halo = st.halo_color(st.INK, ROCK)
    assert st.luminance(st.hex_to_rgb(dark_text_halo)) > st.luminance(ROCK)


def test_neogothic_and_bumstead_digits_are_flagged_unsafe():
    assert {st.NEO, st.BUM} == st.DIGIT_UNSAFE_FONTS
    assert st.feature("marker_number").font[0] == st.GEO


# ------------------------------------------------------------------ layout

def test_normalize_collects_all_errors_at_once():
    with pytest.raises(lay_mod.LayoutError) as e:
        lay_mod.normalize({"labels": [{"text": "", "kind": "nope", "at": [120, 5]}],
                           "routes": [{"points": [[1, 1]], "heading": "X"}]})
    msg = str(e.value)
    for part in ("chybí text", "neznámý druh", "mimo obrázek", "aspoň 2 body", "není světová strana"):
        assert part in msg


def test_normalize_unknown_view_means_no_scale():
    lay = lay_mod.normalize({"view": "isometric", "labels": []})
    assert lay["view"] is None and lay["version"] == 2


def test_from_legacy_v34_shape():
    old = {"infographic_idx": "01", "subtype": "map", "text_overlays": [
        {"id": "t", "role": "title", "content": "VIKINGOVÉ", "position": {"x_pct": 50, "y_pct": 7}},
        {"id": "o", "role": "label", "content": "ATLANTSKÝ OCEÁN", "font_hint": "neo_gothic_heavy_caps",
         "position": {"x_pct": 8, "y_pct": 22, "anchor": "left"}},
        {"id": "r", "role": "label", "content": "VESTRIBYGGĐ", "font_hint": "neo_gothic_heavy_caps",
         "position": {"x_pct": 14, "y_pct": 35, "anchor": "right"}, "callout_to": {"x_pct": 29, "y_pct": 36}},
        {"id": "m", "role": "numbered_marker", "content": "1", "position": {"x_pct": 38, "y_pct": 73}},
        {"id": "s", "role": "scale_bar", "label": "0 100 km", "position": {"x_pct": 60, "y_pct": 94}},
        {"id": "n", "role": "legend", "content": "Sever ↑", "position": {"x_pct": 8, "y_pct": 95}},
        {"id": "l", "role": "caption", "content": "1  Brattahlíð\n2  Hvalsey", "position": {"x_pct": 5, "y_pct": 50}},
    ]}
    lay = lay_mod.from_legacy(old)
    assert lay["header"]["title"] == "VIKINGOVÉ"
    kinds = {lab["id"]: lab["kind"] for lab in lay["labels"]}
    assert kinds == {"o": "ocean", "r": "region"}
    assert lay["labels"][1]["leader_to"] == [29.0, 36.0] and lay["labels"][1]["anchor"] == "right"
    assert lay["markers"] == [{"id": "m", "at": [38.0, 73.0], "n": "1", "kind": "numbered"}]
    assert lay["legend"]["entries"] == [{"n": "1", "text": "Brattahlíð"}, {"n": "2", "text": "Hvalsey"}]
    assert lay["north"]["at"] == [8.0, 95.0] and lay["scale"]["km"] is None
    assert lay["view"] is None
    lay_mod.normalize(lay)          # převedený formát musí projít validací


# ------------------------------------------------------------------ raster

def test_classify_water_land_coast(base_png):
    b = Base(base_png)
    assert b.classify(50, 150, 10)[0] == WATER
    assert b.classify(350, 150, 10)[0] == LAND
    assert b.classify(200, 150, 30)[0] == COAST


def test_nearest_land_from_sea(base_png):
    b = Base(base_png)
    x, y = b.nearest(150, 150, LAND, max_r=150, r=5)
    assert x > 200 and b.classify(x, y, 5)[0] == LAND


# ------------------------------------------------------------------ geometrie skládání

def test_edge_point_leaves_box_towards_target_with_gap():
    x, y = comp_mod._edge_point((100, 100, 200, 50), (500, 125), gap=10)
    assert x == pytest.approx(310) and y == pytest.approx(125)


def test_utf8_spans_are_byte_offsets():
    # „Ð“ má v UTF-8 2 bajty — rozsah číslic musí začít za nimi
    assert comp_mod._utf8_spans("Ð 1450", comp_mod._DIGITS) == [(3, 7)]


def test_catmull_passes_through_points_and_nice_km():
    anchors = comp_mod._catmull([[0, 0], [10, 0], [20, 10]])
    assert [(a["x"], a["y"]) for a in anchors] == [(0, 0), (10, 0), (20, 10)]
    assert "in" not in anchors[0] and "out" not in anchors[-1]
    assert comp_mod._nice_km(180) == 100 and comp_mod._nice_km(260) == 200 and comp_mod._nice_km(0.7) == 0.5


# ------------------------------------------------------------------ kontroly

def _el(id_, type_="label", text="", bbox=(100, 100, 100, 20), **kw):
    return {"id": id_, "type": type_, "text": text, "bbox": bbox, "size": 20, "halo_pad": 0, **kw}


def test_typography_catches_review_errors():
    els = [_el("a", text="VESTRIBYGGĐ"), _el("b", text="985-1450 n. l. | Grónsko"),
           _el("c", text="Osada 1", font=[st.NEO, "Heavy"]),
           _el("d", text="Osada 1", font=[st.NEO, "Heavy"], digit_font="Geograph Edit Bold")]
    codes = [(f["code"], tuple(f["ids"])) for f in checks.check_typography(els)]
    assert ("typo_eth", ("a",)) in codes
    assert codes.count(("typo_dash", ("b",))) == 2         # spojovník i svislice
    assert ("typo_digit", ("c",)) in codes and ("typo_digit", ("d",)) not in codes


def test_fonts_substitute_and_missing_glyphs():
    out = checks.check_fonts([{"family": "NatGeo Caption", "style": "Bold", "status": "substitute",
                               "resolved": {"family": "NatGeo Caption", "style": "Heavy"}},
                              {"family": "Geograph Edit", "style": "Bold", "status": "exact", "missingGlyphs": 2}])
    assert len(out) == 2 and all(f["code"] == "font" for f in out)


def test_collisions_respect_halo_and_parent():
    a = _el("a", text="A", bbox=(100, 100, 100, 20), halo_pad=6)
    b = _el("b", text="B", bbox=(205, 100, 50, 20), halo_pad=6)     # mezera 5 < 12 (dvě halo)
    note = _el("a__note", "note", text="pozn", bbox=(100, 135, 100, 15), parent="a")
    assert [f["ids"] for f in checks.check_collisions([a, b, note])] == [["a", "b"]]


def test_margin_and_shift():
    els = [_el("a", text="x", bbox=(1, 100, 50, 20)), _el("b", text="y", bbox=(300, 300, 50, 20), shifted=[0, 40])]
    out = checks.check_margins(els, 1000, 1000)
    assert [(f["code"], f["level"], f["ids"]) for f in out] == [("margin", "error", ["a"]), ("margin", "warn", ["b"])]


def test_contrast_without_and_with_halo(base_png):
    b = Base(base_png)
    bad = _el("a", text="x", bbox=(10, 10, 100, 50), color="#1E3A70")       # tmavomodrá na oceánu
    ok_halo = _el("b", text="y", bbox=(10, 10, 100, 50), color="#1E3A70", halo="#FFFFFF")
    out = checks.check_contrast([bad, ok_halo], b)
    assert any(f["ids"] == ["a"] and f["level"] == "error" for f in out)
    assert not any(f["ids"] == ["b"] and f["level"] == "error" for f in out)


def test_placement_marker_in_sea_suggests_land(base_png):
    b = Base(base_png)
    els = [_el("m1", "marker", text="1", point=[185, 150], expect="land"),     # 15 px od břehu
           _el("m2", "marker", text="2", point=[330, 150], expect="land")]
    out = checks.check_placement(els, b, 400)
    assert len(out) == 1 and out[0]["ids"] == ["m1"] and "nejbližší vhodné místo" in out[0]["msg"]


def test_leader_starting_in_text_and_crossing_note():
    lab = _el("a", text="EYSTRIBYGGÐ", bbox=(100, 100, 100, 20), leader=[[100, 100], [100, 300]])
    note = _el("a__note", "note", text="zánik", bbox=(90, 130, 120, 15), parent="a")
    codes = [f["msg"] for f in checks.check_leaders([lab, note])]
    assert any("začíná uvnitř" in m for m in codes) and any("vlastní poznámku" in m for m in codes)


def test_note_detached_from_parent():
    lab = _el("a", text="X", bbox=(100, 100, 100, 20))
    far = _el("a__note", "note", text="pozn", bbox=(100, 400, 100, 15), parent="a")
    assert checks.check_notes([lab, far])[0]["code"] == "note"


def test_route_heading_west_vs_east():
    west = _el("r", "route", text="do Evropy", points=[[500, 500], [300, 520], [100, 540]], heading="V")
    east = _el("s", "route", text="do Evropy", points=[[100, 500], [300, 520], [500, 500]], heading="V")
    out = checks.check_routes([west, east])
    assert len(out) == 1 and out[0]["ids"] == ["r"] and "míří na Z" in out[0]["msg"]


def test_scale_only_on_plan_with_reference():
    assert checks.check_scale({"scale": {"at": [1, 1]}, "view": "perspective"}, [])[0]["code"] == "scale"
    assert checks.check_scale({"scale": {"at": [1, 1]}, "view": "plan"},
                              [{"id": "scale", "reason": "chybí reference"}])[0]["code"] == "scale"
    assert checks.check_scale({"scale": None, "view": "perspective"}, []) == []


def test_north_letter_below_tip_is_error():
    good = _el("north", "north", text="S", points=[[100, 90], [100, 100]])
    bad = _el("north", "north", text="S", points=[[100, 110], [100, 100]])
    assert checks.check_north([good]) == [] and checks.check_north([bad])[0]["code"] == "north"


def test_legend_vs_markers():
    lay = {"markers": [{"n": "1"}, {"n": "2"}], "legend": {"entries": [{"n": "1", "text": "A"}, {"n": "3", "text": "A"}]}}
    msgs = [f["msg"] for f in checks.check_legend(lay)]
    assert any("Značka 2" in m for m in msgs) and any("vysvětluje 3" in m for m in msgs)
    assert any("opakuje" in m for m in msgs)


def test_overflow_and_numbers():
    assert checks.check_overflow([_el("r", text="trasa", text_width=500, path_len=400)])[0]["code"] == "overflow"
    assert checks.check_overflow([_el("r", text="trasa", text_width=300, path_len=400)]) == []
    out = checks.check_numbers([_el("a", text="zánik kolem roku 1450, 3 000 lidí, 77 domů")],
                               "Kolem roku 1450 … žilo 3 000 lidí.")
    assert [f["msg"].split("číslo ")[1] for f in out] == ["77 v článku není"]


def test_run_all_without_article_does_not_claim_numbers_passed(base_png):
    res = checks.run_all({"elements": [], "width": 400, "height": 300, "skipped": [], "fonts": []},
                         {"markers": [], "labels": []}, Base(base_png), article="")
    assert "numbers" not in res["passed"] and res["errors"] == 0



def test_geo_point_is_refused_with_a_pointer_to_kartograf():
    with pytest.raises(lay_mod.LayoutError, match="KARTOGRAF"):
        lay_mod.normalize({"labels": [{"text": "Praha", "kind": "town", "at": {"lat": 50.08, "lon": 14.42}}]})


# ------------------------------------------------------------------ zámek VectorCraftu

def test_vectorcraft_session_frees_the_lock_when_the_server_dies(tmp_path):
    lock = tmp_path / "lock"
    # python místo vectorcraft-cli: `python mcp --headless` hned skončí, relace musí zámek vrátit
    with pytest.raises(VectorCraftError, match="ukončil"):
        VectorCraft(cli=sys.executable, timeout=20, lock_path=lock, caller="test")
    assert read_lock(lock) is None


def test_vectorcraft_waits_for_the_heavy_lock(tmp_path):
    lock = tmp_path / "lock"
    other = HeavyLock(lock, "grafik-engine")
    assert other.try_acquire("gpu", "flux")
    with pytest.raises(HeavyBusy):
        VectorCraft(cli=sys.executable, lock_path=lock, lock_wait_s=0.2)
    other.release()


@pytest.mark.skipif(os.environ.get("GRAFIK_VECTORCRAFT_TESTS") != "1" or find_cli() is None,
                    reason="skutečný VectorCraft jen s GRAFIK_VECTORCRAFT_TESTS=1 (těžká práce)")
def test_real_vectorcraft_compose(tmp_path):
    base = _half(tmp_path / "base.png", size=(1600, 1200))
    lay = lay_mod.normalize({
        "view": "plan", "header": {"title": "Zkouška 985–1450", "at": [50, 6]},
        "labels": [{"id": "sea", "text": "Labradorské moře", "kind": "sea", "at": [25, 50]},
                   {"id": "reg", "text": "Eystribyggð", "kind": "region", "at": [25, 75],
                    "note": "zánik kolem roku 1450", "leader_to": [75, 60]}],
        "markers": [{"id": "m1", "n": "1", "at": [80, 40]}],
        "routes": [{"id": "r", "points": [[60, 85], [75, 88], [90, 80]], "heading": "V", "label": "do Evropy"}],
        "legend": {"at": [55, 15], "entries": [{"n": "1", "text": "Brattahlíð"}]},
        "north": {"at": [92, 15]},
        "scale": {"at": [60, 93], "ref": {"a": [10, 10], "b": [90, 10], "km": 800}}})
    with VectorCraft(caller="grafik-tests", lock_wait_s=300) as vc:
        comp = comp_mod.compose(base, lay, tmp_path / "out", vc=vc)
    for ext in (".vectorcraft", ".pdf", ".svg", ".png"):
        assert (tmp_path / f"out{ext}").stat().st_size > 0
    d = comp.to_dict()
    assert all(f["status"] == "exact" for f in d["fonts"])
    res = checks.run_all(d, lay, Base(base))
    assert res["errors"] == 0, res["findings"]
    with Image.open(tmp_path / "out.png") as im:
        assert im.size == (1600, 1200)
