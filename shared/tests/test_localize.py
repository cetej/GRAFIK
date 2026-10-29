"""Počeštění vrstvou textu (`ngm_shared.textlayer.localize`) a sdílené volání Claude (`ngm_shared.claude`).

Claude je všude zamockovaný (`ask=`); skutečné volání pod pytestem bez GRAFIK_LIVE_TESTS=1 skončí chybou.
Obrázky jsou syntetické: písmo se kreslí do známého podkladu a po mazání se měří, kolik ho zůstalo.
"""

import json
import math

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from ngm_shared import claude
from ngm_shared.textlayer import localize as L

FONT = "C:/Windows/Fonts/timesbd.ttf"


def _answer(payload: dict, usd: float = 0.05) -> claude.Answer:
    return claude.Answer(json.dumps(payload, ensure_ascii=False), "claude-opus-5-5", 2000, 2000, usd, "end_turn")


def _text(img: Image.Image, xy, text: str, size: int, fill, angle: float = 0.0) -> list:
    """Nakreslí text (otočený kolem středu) a vrátí jeho rámeček [x0, y0, x1, y1]."""
    f = ImageFont.truetype(FONT, size)
    w, h = int(f.getlength(text)) + 4, int(size * 1.3)
    layer = Image.new("L", (w, h), 0)
    ImageDraw.Draw(layer).text((2, 0), text, font=f, fill=255)
    if angle:
        layer = layer.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    x, y = int(xy[0] - layer.width / 2), int(xy[1] - layer.height / 2)
    ink = Image.new("RGB", layer.size, fill) if not callable(fill) else fill(img.crop((x, y, x + layer.width, y + layer.height)))
    img.paste(ink, (x, y), layer)
    ys, xs = np.nonzero(np.asarray(layer) > 60)
    return [x + int(xs.min()), y + int(ys.min()), x + int(xs.max()) + 1, y + int(ys.max()) + 1]


def _el(box, en="Text", cs="Text", color="#000000", angle=0.0, **kw) -> dict:
    return L.normalize_texts({"elements": [{"id": 1, "en": en, "cs": cs, "box": box, "angle": angle,
                                            "color": color, "font": "serif", "bold": True, **kw}]})["elements"][0]


def _left(clean: np.ndarray, ref: np.ndarray, box) -> float:
    """Podíl pixelů v rámečku, které se po mazání liší od podkladu bez písma o víc než 60."""
    x0, y0, x1, y1 = [int(v) for v in box]
    d = np.abs(clean[y0:y1, x0:x1].astype(int) - ref[y0:y1, x0:x1].astype(int)).max(2)
    return float((d > 60).mean())


# ------------------------------------------------------------------ přečtené texty

def test_normalize_texts_scales_boxes_back_and_skips_empty():
    out = L.normalize_texts({"kind": "map", "scale": 0.5, "elements": [
        {"id": 1, "en": "Greenland", "cs": "Grónsko", "box": [10, 20, 60, 30], "color": "nonsense"},
        {"id": 2, "en": "Logo", "cs": "", "box": [0, 0, 5, 5]}]})
    assert out["kind"] == "map" and out["scale"] == 1.0 and len(out["elements"]) == 1
    el = out["elements"][0]
    assert el["box"] == [20, 40, 120, 60] and el["color"] == "#000000" and el["align"] == "left"
    with pytest.raises(L.LocalizeError, match="neplatný rámeček"):
        L.normalize_texts({"elements": [{"en": "x", "cs": "x", "box": [50, 0, 10, 5]}]})


def test_read_texts_asks_once_and_returns_cost(tmp_path):
    img = Image.new("RGB", (3136, 1000), "white")       # zmenší se na 1568 px → měřítko 0.5
    img.save(tmp_path / "a.png")
    calls = []

    def ask(content, system, **kw):
        calls.append(kw)
        assert content[0]["type"] == "image" and "1568x500" in content[1]["text"]
        return _answer({"kind": "infographic", "elements": [
            {"id": 1, "en": "Water", "cs": "Voda", "box": [100, 100, 200, 120], "color": "#1f7cc0"}]}, usd=0.11)

    texts, cost = L.read_texts(tmp_path / "a.png", ask=ask)
    assert len(calls) == 1 and calls[0]["model"] == "claude-opus-5-5" and calls[0]["effort"] == "high"
    assert texts["elements"][0]["box"] == [200, 200, 400, 240]
    assert cost == {"model": "claude-opus-5-5", "in": 2000, "out": 2000, "usd": 0.11}


# ------------------------------------------------------------------ mazání

def test_erase_removes_text_and_keeps_the_town_dot_next_to_it():
    ref = Image.new("RGB", (400, 120), (230, 238, 245))
    img = ref.copy()
    box = _text(img, (220, 60), "Roskilde", 24, (0, 0, 0))
    ImageDraw.Draw(img).ellipse((box[0] - 16, 55, box[0] - 9, 62), fill=(0, 0, 0))    # tečka města
    clean, measured, _ = L.erase(np.array(img), [_el(box)])
    assert _left(clean, np.array(ref), box) < 0.01
    assert clean[58, box[0] - 12].max() < 80                 # tečka zůstala
    assert measured[0]["residue"] < 0.05


def test_erase_multiplied_label_over_two_colours():
    """Vada T2: šedý popisek sázený násobením podkladu je na zelené tmavě zelený, na žluté tmavě žlutý."""
    ref = Image.new("RGB", (500, 140), (3, 154, 41))
    ImageDraw.Draw(ref).rectangle((250, 0, 500, 140), fill=(255, 192, 0))
    img = ref.copy()
    multiply = lambda crop: Image.fromarray((np.asarray(crop).astype(int) * 128 // 255).astype(np.uint8))  # noqa: E731
    box = _text(img, (250, 70), "Saami and others", 30, multiply)
    clean, measured, _ = L.erase(np.array(img), [_el(box, en="Saami and others", color="#808080")])
    assert _left(clean, np.array(ref), box) < 0.03            # zbytek = rozmazaná hranice ploch, ne písmo
    assert not measured[0]["color_measured"]                 # barvu od Claude potvrdily pixely (násobení)


def test_erase_measures_the_colour_when_claude_got_it_wrong():
    """Claude barvu písma netrefil (řekl šedá, písmo je tmavě červené na zelené ploše)."""
    ref = Image.new("RGB", (400, 120), (3, 154, 41))
    img = ref.copy()
    box = _text(img, (200, 60), "Skralings", 30, (120, 20, 20))
    clean, measured, _ = L.erase(np.array(img), [_el(box, en="Skralings", color="#808080")])
    assert measured[0]["color_measured"] and np.linalg.norm(np.array(measured[0]["ink_color"]) - (120, 20, 20)) < 40
    assert _left(clean, np.array(ref), box) < 0.01


def test_rotated_label_size_in_one_pass_and_neighbour_line_ignored():
    ref = Image.new("RGB", (600, 400), (190, 190, 190))
    img = ref.copy()
    box = _text(img, (300, 200), "Gardarike", 28, (90, 90, 90), angle=-35)
    # hranice území stejné barvy kříží konec popisku
    ImageDraw.Draw(img).line((box[2] - 10, 40, box[2] + 60, 380), fill=(90, 90, 90), width=2)
    el = _el([box[0] - 4, box[1] + 6, box[2] + 4, box[3] - 6], en="Gardarike", cs="Gardarike", angle=-35,
             color="#5a5a5a")
    m = L._measure(np.array(img), el)
    px, _ = L.font_size(el, el["box"], m["frame"])
    assert 0.8 * 28 <= px <= 1.15 * 28
    assert math.dist(m["center"], ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)) < 8


# ------------------------------------------------------------------ celek

def test_localize_with_given_texts_is_free_and_writes_png_svg(tmp_path):
    img = Image.new("RGB", (500, 200), (240, 240, 240))
    box = _text(img, (250, 60), "Water cycle", 32, (20, 20, 20))
    box2 = _text(img, (250, 140), "Rain", 24, (31, 124, 192))
    img.save(tmp_path / "info.png")
    texts = {"kind": "map", "elements": [
        {"id": 1, "en": "Water cycle", "cs": "Koloběh vody", "box": box, "color": "#141414", "font": "serif",
         "bold": True, "align": "center"},
        {"id": 2, "en": "Rain", "cs": "Déšť s mnoha dalšími slovy navíc", "box": box2, "color": "#1f7cc0"}]}

    def no_ask(*a, **kw):
        raise AssertionError("s hotovými texty se Claude nevolá")

    r = L.localize(tmp_path / "info.png", tmp_path / "out", texts=texts, ask=no_ask)
    assert r["cost"] is None and r["elements"] == 2 and r["kind"] == "map"
    svg = (tmp_path / "out" / "image-0.svg").read_text(encoding="utf-8")
    assert "Koloběh vody" in svg and 'href="image-0-bez-textu.png"' in svg and svg.count("<text") == 2
    assert Image.open(r["png"]).size == (500, 200)
    saved = json.loads((tmp_path / "out" / "image-0.texty.json").read_text(encoding="utf-8"))
    assert saved["elements"][0]["cs"] == "Koloběh vody"
    whats = [w["what"] for w in r["warnings"]]
    assert whats[0] == "Obrázek je mapa." and any("delší než původní" in w for w in whats)


def test_localize_without_text_is_an_error(tmp_path):
    Image.new("RGB", (50, 50), "white").save(tmp_path / "x.png")
    with pytest.raises(L.LocalizeError, match="žádný text"):
        L.localize(tmp_path / "x.png", tmp_path / "o", texts={"elements": []})


# ------------------------------------------------------------------ Claude

def test_ask_refuses_to_pay_under_pytest(monkeypatch):
    monkeypatch.delenv(claude.LIVE_ENV, raising=False)
    monkeypatch.setattr(claude, "_client", lambda: pytest.fail("klient se nesmí ani vytvořit"))
    with pytest.raises(claude.ClaudeError, match="GRAFIK_LIVE_TESTS"):
        claude.ask([], "x", what="test")


def test_usd_from_usage_and_unknown_model_at_the_top_price():
    assert claude.usd_for("claude-opus-5-5", 2336, 5259) == 0.1145        # T2 čtení infografiky
    assert claude.usd_for("claude-haiku-5-5", 1_000_000, 0) == 0.10
    assert claude.usd_for("neznámý", 1_000_000, 0) == 10.0


def test_parse_json_takes_the_object_out_of_prose():
    assert claude.parse_json('Tady: {"a": 1} hotovo', "x") == {"a": 1}
    with pytest.raises(claude.ClaudeError, match="není JSON"):
        claude.parse_json("nic", "x")
