"""Počeštění na skutečných mapách z článků, zdarma z uložených textů. Každý nový druh mapy sem přibude
(`.claude/rules/pocesteni.md`). Soubory jsou v NG-ROBOT, bez nich se test přeskočí."""
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ngm_shared.textlayer import localize as lz
from ngm_shared.textlayer import tisk

PROCESSED = Path("C:/Users/stock/Documents/000_NGM/NG-ROBOT/processed")
IRBIS = PROCESSED / "2026-10-29_see-the-first-photographs-of-snow-leopards-in-the-wild/images/_mapa_cs/02"
EVEREST = PROCESSED / "2026-10-29_what-compelled-jim-morrison-to-ski-down-the-tallest-mountain-on-earth/images/_mapa_cs"


def _load(work: Path) -> tuple[np.ndarray, dict]:
    if not (work / "texty.json").is_file():
        pytest.skip(f"{work} není na tomhle počítači")
    original = next(work.glob("original.*"))
    with Image.open(original) as im:
        return np.array(im.convert("RGB")), lz.normalize_texts(json.loads((work / "texty.json").read_text(encoding="utf-8")))


def test_printed_scan_keeps_area_borders_and_markers():
    img, texts = _load(IRBIS)
    assert tisk.only_ink(img, texts["elements"])
    clean, layout = tisk.erase(img, texts["elements"], texts["markers"])
    # mimo písmo se obraz nezměnil: areál ani hranice nezmizely
    changed = (clean != img).any(axis=2).mean()
    assert changed < 0.08
    for x0, y0, x1, y1 in texts["markers"]:
        box = (slice(int(y0), int(y1)), slice(int(x0), int(x1)))
        assert (clean[box] == img[box]).all()
    # zbytek hlásí kontrola jen tam, kde popisek křižuje tmavou hranici
    assert sorted(el["en"] for el, m in zip(texts["elements"], layout) if m["residue"] > lz.RESIDUE_WARN) == ["Hindu Kush", "Tien Shan"]


def test_white_text_on_flat_plan_is_erased_and_stays_white():
    # půdorys gymnasionu v Mieze (2026-11-03): bílé písmo na zelené ploše vyšlo zelené a nesmazané
    job = Path("C:/Users/stock/Documents/000_NGM/GRAFIK/library/2026-11/20261103-223712-0fd24a")
    original = Path("C:/Users/stock/Documents/000_NGM/GRAFIK/run/uploads/e8767fdf4096a293.png")
    if not (job / "image-0.texty.json").is_file() or not original.is_file():
        pytest.skip("půdorys gymnasionu není na tomhle počítači")
    with Image.open(original) as im:
        img = np.array(im.convert("RGB"))
    texts = lz.normalize_texts(json.loads((job / "image-0.texty.json").read_text(encoding="utf-8")))
    clean, measured, _ = lz.erase(img, texts["elements"])
    assert {m["color"] for m in measured} == {"#FFFFFF"}
    for el in texts["elements"]:
        x0, y0, x1, y1 = (int(v) for v in el["box"])
        white = lambda a: int((a[y0:y1, x0:x1].astype(int).sum(axis=2) > 600).sum())  # noqa: E731
        assert white(img) > 100 and white(clean) == 0, el["en"]


def test_relief_map_stays_on_the_photocraft_path():
    work = next((p for p in sorted(EVEREST.glob("*")) if (p / "texty.json").is_file()), None) if EVEREST.is_dir() else None
    if work is None:
        pytest.skip("mapa Everestu není na tomhle počítači")
    img, texts = _load(work)
    assert not tisk.only_ink(img, texts["elements"])
