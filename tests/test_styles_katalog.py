"""The catalogue of styles (styles/katalog.yaml): valid cards, free prompts, nothing overwritten in the library."""
import importlib.util
from pathlib import Path

from ngm_shared import knihovna

from engine.translate import is_czech

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("styles_katalog", ROOT / "scripts" / "styles_katalog.py")
K = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(K)
DATA = K.nacti()


def test_catalogue_entries_are_valid_and_every_category_has_styles():
    nove, stare = DATA["nove"], DATA["existujici"]
    slugs = [p["slug"] for p in [*nove, *stare]]
    assert len(slugs) == len(set(slugs))
    assert {p["kategorie"] for p in [*nove, *stare]} == set(knihovna.STYLE_CATEGORIES)
    poradi = [p["poradi"] for p in [*nove, *stare]]
    assert len(poradi) == len(set(poradi))
    for p in nove:
        assert p["name"] and p["note"] and p["signature"] and p["avoid"], p["slug"]
        assert len(p["ukazky"]) == 3, p["slug"]
        assert bool(p.get("look")) == (p["kategorie"] == "film"), p["slug"]


def test_prompt_words_are_english_so_no_paid_translation_and_stay_non_empty():
    for p in DATA["nove"]:
        text = knihovna.image_text(K.karta(p))
        assert len(text) > 80 and not is_czech(text), p["slug"]
        assert knihovna.video_lines(K.karta(p)), p["slug"]
        assert all(not is_czech(K.SPOLECNE.get(u, u)) for u in p["ukazky"]), p["slug"]


def test_every_style_of_the_catalogue_has_a_sample_plan_except_the_operators_own():
    plan = K.ukazky_plan(DATA)
    assert set(plan) == {p["slug"] for p in [*DATA["nove"], *DATA["existujici"]]} - {"karikatura-3d-real"}


def test_cards_are_written_once_and_existing_cards_only_gain_fields(tmp_path):
    old = {"name": "Noir", "look": "hard light", "film": {"lens": "35mm"}, "note": "můj popis"}
    knihovna.write("style", "default", old, tmp_path)
    K.karty(DATA, tmp_path, dry_run=True)
    assert knihovna.slugs("style", tmp_path) == ["default"]
    K.karty(DATA, tmp_path, dry_run=False)
    card = knihovna.read("style", "default", tmp_path)
    assert card == {**old, "kategorie": "film", "poradi": 1020}  # the operator's note stays
    # a new card edited by the operator is not rewritten by another run
    novy = DATA["nove"][0]["slug"]
    knihovna.write("style", novy, {**knihovna.read("style", novy, tmp_path), "note": "upraveno"}, tmp_path)
    K.karty(DATA, tmp_path, dry_run=False)
    assert knihovna.read("style", novy, tmp_path)["note"] == "upraveno"
