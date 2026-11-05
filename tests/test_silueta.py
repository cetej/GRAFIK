"""Profil tvora z předloh (engine/silueta.py): z boku hřbet a břicho, shora šířka, v podílech délky."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from engine.silueta import Predloha, SiluetaError, SiluetaIn, decode, measure
from tests.test_models3d import api, settings  # noqa: F401  (fixtures)

REPO = Path(__file__).resolve().parents[1]
WHALE_REFS = Path("C:/Users/stock/Documents/000_NGM/GRAFIK/library/plakaty/vorvan/predlohy")


def drawing(height_px: int, width_px: int = 400, blunt_left: bool = True) -> np.ndarray:
    """Tmavý tvar na bílém: tupá hlava vlevo (elipsa), tenký ocas vpravo (trojúhelník)."""
    img = np.full((300, 600, 3), 255, np.uint8)
    cv2.ellipse(img, (250, 150), (width_px // 2, height_px // 2), 0, 0, 360, (40, 40, 40), -1)
    cv2.fillPoly(img, [np.array([[400, 140], [560, 148], [560, 152], [400, 160]])], (40, 40, 40))
    return img if blunt_left else img[:, ::-1].copy()


def png(img: np.ndarray) -> str:
    return base64.b64encode(cv2.imencode(".png", img)[1].tobytes()).decode()


def test_side_gives_back_and_belly_over_the_lowest_point():
    out = measure(drawing(100), SiluetaIn(bok=Predloha(prah=49)))
    prof = out["profil"]
    assert len(prof["x"]) == 101 and prof["x"][0] == 0 and prof["x"][-1] == 1
    length = 560 - 50
    assert out["vyska_ku_delce"] == pytest.approx(100 / length, abs=0.01)
    assert min(prof["bricho"]) == 0.0 and "sirka" not in prof


def test_thin_tail_is_cut_off_and_head_can_be_on_the_right():
    left = measure(drawing(100), SiluetaIn(bok=Predloha(prah=49), konec_tloustka=0.05))
    right = measure(drawing(100, blunt_left=False), SiluetaIn(bok=Predloha(prah=49), konec_tloustka=0.05, hlava_bok="vpravo"))
    assert left["vyska_ku_delce"] == pytest.approx(100 / 400, abs=0.01)       # tělo končí u kořene ocasu, ne na jeho špičce
    assert np.allclose(left["profil"]["hrbet"], right["profil"]["hrbet"], atol=0.01)


def test_top_view_turns_the_shape_and_puts_the_blunt_end_first():
    img = drawing(80)
    tilted = cv2.warpAffine(img, cv2.getRotationMatrix2D((300, 150), 30, 0.8), (600, 300), borderValue=(255, 255, 255))
    out = measure(drawing(100), SiluetaIn(bok=Predloha(prah=49), shora=Predloha(prah=49)), tilted)
    width = out["profil"]["sirka"]
    assert out["sirka_ku_delce"] == pytest.approx(80 / 510, abs=0.015)
    assert np.argmax(width) < 60 and width[95] < 0.15 * max(width)      # hlava (tupý konec) vlevo, ocas tenký vpravo
    flipped = measure(drawing(100), SiluetaIn(bok=Predloha(prah=49), shora=Predloha(prah=49), obratit_shora=True), tilted)
    assert np.argmax(flipped["profil"]["sirka"]) > 40


def test_blank_picture_and_bad_crop_are_refused():
    with pytest.raises(SiluetaError, match="žádný tvar"):
        measure(np.full((100, 100, 3), 255, np.uint8), SiluetaIn(bok=Predloha()))
    with pytest.raises(SiluetaError, match="výřez"):
        measure(drawing(100), SiluetaIn(bok=Predloha(vyrez=(0.5, 0, 0.2, 1))))


def test_api_measures_uploaded_pictures_and_says_what_is_missing(api):
    r = api.post("/api/v2/models3d/silueta", json={"bok": {"b64": png(drawing(100)), "prah": 49}, "shora": {"b64": png(drawing(60)), "prah": 49}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["vyska_ku_delce"] == pytest.approx(0.196, abs=0.01) and "sirka" in body["profil"]
    assert cv2.imdecode(np.frombuffer(base64.b64decode(body["kontrola_bok"]), np.uint8), cv2.IMREAD_COLOR) is not None
    assert api.post("/api/v2/models3d/silueta", json={"bok": {"ref_id": "neni"}}).status_code == 404
    assert api.post("/api/v2/models3d/silueta", json={"bok": {}}).status_code == 400
    assert api.post("/api/v2/models3d/silueta", json={"bok": {"b64": base64.b64encode(b"neni obrazek").decode()}}).status_code == 400


@pytest.mark.skipif(not (WHALE_REFS / "01.jpg").is_file(), reason="předlohy vorvaně nejsou na disku")
def test_whale_references_give_the_hand_measured_profile():
    out = measure(decode((WHALE_REFS / "01.jpg").read_bytes()), SiluetaIn(bok=Predloha(vyrez=(0, 0, 1, 0.5), prah=49), shora=Predloha(prah=22), konec_tloustka=0.03),
                  decode((WHALE_REFS / "17.jpg").read_bytes()))
    ref = json.loads((REPO / "scripts" / "3d" / "vorvan_profily.json").read_text(encoding="utf-8"))
    assert out["profil"]["hrbet"] == ref["hrbet"] and out["profil"]["bricho"] == ref["bricho"]
    assert np.abs(np.array(out["profil"]["sirka"]) - np.array(ref["sirka"])).mean() < 0.005
