"""Mazání na tištěné mapě: smaže se jen písmo, plocha, hranice a značky zůstanou (mapa irbisů 2026-11-01)."""
import cv2
import numpy as np

from ngm_shared.textlayer import localize as lz
from ngm_shared.textlayer import pcraft, tisk

GOLD = (200, 170, 40)


def _map():
    img = np.full((600, 1200, 3), 245, np.uint8)
    img[150:450, 300:900] = GOLD                                        # areál přes celou plochu
    cv2.putText(img, "TIBET", (420, 320), cv2.FONT_HERSHEY_SIMPLEX, 3, (15, 15, 15), 9, cv2.LINE_AA)
    cv2.circle(img, (1000, 300), 10, (10, 10, 10), -1)                  # tečka města
    return img


def _el(**kw):
    return {"id": 1, "en": "TIBET", "cs": "TIBET", "box": [410, 245, 700, 335], "angle": 0.0, "color": "#111111",
            "font": "serif", "bold": False, "italic": False, "caps": True, "align": "center", **kw}


def test_only_ink_map_yes_relief_no():
    assert tisk.only_ink(_map(), [_el()])
    relief = _map()
    relief[:, :120] = 30                                                # tmavý reliéf mimo popisky
    assert not tisk.only_ink(relief, [_el()])


def test_erase_keeps_area_and_marker():
    img = _map()
    clean, layout = tisk.erase(img, [_el()], [[985, 285, 1015, 315]])
    box = clean[245:335, 410:700]
    assert (cv2.cvtColor(box, cv2.COLOR_RGB2GRAY) < tisk.DARK).sum() == 0           # písmo je pryč
    assert np.abs(box.reshape(-1, 3).mean(axis=0) - np.array(GOLD)).max() < 6       # areál pod ním zůstal
    assert (clean[295:305, 995:1005] == img[295:305, 995:1005]).all()               # značka se nedotkla
    assert layout[0]["residue"] == 0.0


def test_curved_label_keeps_crossing_line():
    img = np.full((400, 800, 3), 245, np.uint8)
    rng = np.random.default_rng(1)
    dots = rng.random((400, 800)) < 0.3
    img[(np.abs(np.arange(400)[:, None] - 200) < 4) & dots] = (20, 20, 20)          # hranice z tiskových bodů
    cv2.putText(img, "H", (350, 240), cv2.FONT_HERSHEY_SIMPLEX, 3, (10, 10, 10), 12)
    el = _el(en="H", cs="H", box=[340, 150, 460, 250], path=[[300, 200], [500, 200]], path_width=110)
    clean, _ = tisk.erase(img, [el], [])
    gray = cv2.cvtColor(clean, cv2.COLOR_RGB2GRAY)
    assert (gray[196:204, 600:700] < tisk.DARK).any()                               # hranice mimo písmeno je celá
    assert (gray[160:190, 360:430] < tisk.DARK).sum() == 0                          # písmeno nad ní je pryč


def test_protected_keeps_big_letters_out_on_large_scan():
    img = np.full((1500, 3000, 3), 240, np.uint8)
    cv2.rectangle(img, (500, 500), (506, 560), (200, 40, 40), -1)                   # 60 px vysoký sytý tah písmene
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    assert pcraft._protected(img, hsv, [])[530, 503] == 0


def test_residue_is_measured_not_zero():
    img = _map()
    assert pcraft._dark_left(img, img, _el()) == 1.0
    assert pcraft._dark_left(img, np.full_like(img, 245), _el()) == 0.0


def test_normalize_keeps_path_and_markers():
    data = {"kind": "map", "scale": 0.5, "markers": [[10, 10, 20, 20]],
            "elements": [{"id": 1, "en": "A", "cs": "B", "box": [0, 0, 10, 10], "path": [[10, 20], [30, 40]], "size_px": 50}]}
    out = lz.normalize_texts(data)
    assert out["markers"] == [[20.0, 20.0, 40.0, 40.0]]
    assert out["elements"][0]["path"] == [[20.0, 40.0], [60.0, 80.0]]
    assert out["elements"][0]["size_px"] == 50


def test_svg_has_layers_baseline_and_room_on_the_curve(tmp_path):
    from PIL import Image
    el = _el(path=[[300, 300], [800, 300]], path_width=100, size_px=40, italic=True)
    h = {**_el(id=2, en="X", cs="Čína", box=[100, 50, 300, 90]), "upright": True, "spaced": False}
    layout = [{"L": 500.0, "pitch": 40.0, "center": (500, 300), "rot_px": 30.0, "curve": None, "plate": None,
               "protect": np.zeros((600, 1200), np.uint8), "residue": 0.0},
              {"L": 200.0, "pitch": 40.0, "center": (200, 70), "rot_px": 30.0, "curve": None, "plate": None,
               "protect": np.zeros((600, 1200), np.uint8), "residue": 0.0}]
    _, svg, _ = pcraft.typeset(Image.fromarray(_map()), [el, h], layout, "podklad.png")
    assert '<g id="Podklad">' in svg and '<g id="Texty">' in svg and "dominant-baseline" not in svg
    assert "'NatGeo Peele', serif" in svg
    last = svg.split('id="krivka-0" d="M')[1].split('"')[0].split(" L")[-1]
    assert float(last.split()[0]) > 800 - 300                                       # křivka má rezervu za textem
    base = tmp_path / "podklad.png"
    base.write_bytes(b"PNGDATA")
    window = lz.for_window(svg, base)
    assert 'href="podklad.png"' not in window and "data:image/png;base64,UE5HREFUQQ==" in window
