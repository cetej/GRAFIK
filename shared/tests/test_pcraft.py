"""Počeštění přes PhotoCraft: co se chrání, kdy se použije a že selhání spadne na náhradní cestu."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from ngm_shared.textlayer import localize as tl, pcraft


def el(i, en, cs, box, **kw):
    return {"id": i, "en": en, "cs": cs, "box": box, "angle": 0.0, "color": "#222222", "font": "sans", "bold": False,
            "italic": False, "caps": False, "align": "left", **kw}


def noisy(h=200, w=300):
    return np.repeat(np.random.default_rng(1).integers(90, 170, (h, w, 1), dtype=np.uint8), 3, axis=2)   # šedý reliéf


def test_thin_line_stays_thick_area_and_label_letter_do_not():
    img = np.full((200, 300, 3), 180, np.uint8)
    img[100:102, 20:280] = (70, 31, 120)           # trasa
    img[10:60, 10:120] = (20, 160, 40)             # plocha mapy
    img[150:160, 150:160] = (70, 31, 120)          # značka
    img[150:160, 30:40] = (70, 31, 120)            # kus písmene v rámečku popisku
    hsv = pcraft.cv2.cvtColor(img, pcraft.cv2.COLOR_RGB2HSV)
    keep = pcraft._protected(img, hsv, [el(1, "x", "x", [25, 145, 60, 165])])
    assert keep[100, 100] and keep[155, 155]
    assert not keep[30, 60] and not keep[155, 35]


def test_erase_restores_the_route_and_paints_the_bar(monkeypatch):
    img = noisy()
    img[100:102, :] = (70, 31, 120)
    img[20:40, 30:130] = (70, 31, 120)
    img[26:34, 40:120] = (255, 255, 255)           # bílý text na pruhu
    seen = {}

    def fake(image, strokes):
        seen["strokes"] = strokes
        out = image.copy()
        out[90:110, 100:200] = 128                 # výplň přejela trasu
        return out

    monkeypatch.setattr(pcraft, "remove", fake)
    elements = [el(1, "ROUTE", "TRASA", [100, 95, 200, 107]),
                el(2, "START", "START LYŽAŘSKÉ TRASY", [36, 22, 124, 38], color="#FFFFFF", caps=True, bold=True)]
    clean, layout = pcraft.erase(img, elements)
    assert (clean[100, 150] == (70, 31, 120)).all()
    assert len(seen["strokes"]) == 1                # pruh se nemaže
    x0, y0, x1, y1 = layout[1]["plate"]
    assert (y0, y1) == (20, 40) and x1 - x0 > 100   # celá výška pruhu, prodloužený podle překladu
    assert (clean[30, 80] == (70, 31, 120)).all()


def test_batches_keep_all_strokes_together_unless_the_command_line_is_too_short():
    small = [{"points": [[1, 2], [3, 4]], "size": 5}] * 50
    assert len(pcraft._batches(small)) == 1
    big = [{"points": [[1.5, 2.5]] * 2000, "size": 5}] * 3
    assert len(pcraft._batches(big)) == 3 and sum(map(len, pcraft._batches(big))) == 3


def test_flat_map_is_not_textured_and_relief_is():
    assert not pcraft.textured(np.full((100, 100, 3), 200, np.uint8))
    assert pcraft.textured(noisy())


TEXTS = {"kind": "map", "elements": [{"id": 1, "en": "Face", "cs": "Stěna", "box": [40, 40, 120, 60], "color": "#111111"}]}


def test_photocraft_failure_falls_back_with_a_warning(tmp_path, monkeypatch):
    src = tmp_path / "a.png"
    Image.fromarray(noisy()).save(src)
    monkeypatch.setattr(pcraft, "ready", lambda: True)

    def broken(*_a):
        raise pcraft.PhotoCraftError("PhotoCraft selhal")

    monkeypatch.setattr(pcraft, "remove", broken)
    r = tl.localize(src, tmp_path / "o", texts=TEXTS)
    assert r["warnings"][0]["what"].startswith("Mazání náhradní cestou") and (tmp_path / "o" / "image-0.png").exists()


def test_flat_image_uses_the_old_path_without_a_warning(tmp_path, monkeypatch):
    src = tmp_path / "a.png"
    Image.new("RGB", (300, 200), (200, 200, 200)).save(src)

    def forbidden(*_a):
        raise AssertionError("plochý obrázek nemá jít do PhotoCraftu")

    monkeypatch.setattr(pcraft, "remove", forbidden)
    r = tl.localize(src, tmp_path / "o", texts=TEXTS)
    assert [w["what"] for w in r["warnings"]] == ["Obrázek je mapa."]


@pytest.mark.skipif(not pcraft.ready(), reason="PhotoCraft nebo písma NG tu nejsou")
def test_real_photocraft_removes_a_label_from_texture(tmp_path):
    img = noisy()
    img[80:96, 60:200] = 20
    src = tmp_path / "a.png"
    Image.fromarray(img).save(src)
    r = tl.localize(src, tmp_path / "o", texts={"kind": "map", "elements": [
        {"id": 1, "en": "Face", "cs": "Stěna", "box": [60, 80, 200, 96], "color": "#141414"}]})
    clean = np.array(Image.open(r["base"]))
    assert clean[88, 130].mean() > 60
    assert not [w for w in r["warnings"] if "náhradní" in w["what"]]
