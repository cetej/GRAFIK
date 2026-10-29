"""ngm_shared.knihovna and knihovna_prevod: the shared library of characters, places, props and styles (phase 4)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import yaml

from ngm_shared import knihovna, knihovna_prevod

HERE = Path(__file__).resolve().parent
REPO_STYLES = HERE.parents[1] / "styles"


def test_root_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("NGM_KNIHOVNA", str(tmp_path))
    assert knihovna.root() == tmp_path
    monkeypatch.delenv("NGM_KNIHOVNA")
    assert knihovna.root() == knihovna.DEFAULT_ROOT


def test_layout_is_klapkas(tmp_path):
    assert knihovna.card_path("character", "caesar", tmp_path) == tmp_path / "characters" / "caesar" / "card.yaml"
    assert knihovna.card_path("environment", "a", tmp_path) == tmp_path / "environments" / "a" / "card.yaml"
    assert knihovna.card_path("prop", "amfora", tmp_path) == tmp_path / "props" / "amfora.yaml"
    assert knihovna.card_path("style", "default", tmp_path) == tmp_path / "styles" / "default.yaml"
    assert knihovna.item_dir("prop", "amfora", tmp_path) == tmp_path / "props" / "amfora"
    for bad in ("", "../x", "a/b", "a.b", "a\\b", ".", "č"):
        with pytest.raises(knihovna.KnihovnaError):
            knihovna.card_path("character", bad, tmp_path)
    with pytest.raises(knihovna.KnihovnaError):
        knihovna.card_path("animal", "x", tmp_path)


def test_write_read_list_update(tmp_path):
    assert knihovna.read("character", "caesar", tmp_path) is None
    assert knihovna.slugs("character", tmp_path) == []
    knihovna.write("character", "caesar", {"name": "Caesar", "anchors": "laurel wreath, toga"}, tmp_path)
    knihovna.write("character", "delnik", {"name": "Dělník"}, tmp_path)
    knihovna.write("prop", "amfora", {"name": "Amfora", "count": 1}, tmp_path)
    assert knihovna.read("character", "caesar", tmp_path) == {"name": "Caesar", "anchors": "laurel wreath, toga"}
    assert knihovna.slugs("character", tmp_path) == ["caesar", "delnik"]
    assert list(knihovna.cards("prop", tmp_path)) == ["amfora"]
    for slug in ("rekonstrukce", "rekonstrukce-era"):                  # KLAPKA's order: by card file
        knihovna.write("style", slug, {"name": slug, "look": "x"}, tmp_path)
    assert knihovna.slugs("style", tmp_path) == ["rekonstrukce-era", "rekonstrukce"]
    text = (tmp_path / "characters" / "delnik" / "card.yaml").read_text(encoding="utf-8")
    assert text == "name: Dělník\n"                                  # same writer as KLAPKA: diacritics kept
    new = knihovna.update("character", "caesar", {"voice": "deep"}, tmp_path)
    assert new == {"name": "Caesar", "anchors": "laurel wreath, toga", "voice": "deep"}
    assert knihovna.update("prop", "amfora", lambda c: {**c, "count": c["count"] + 1}, tmp_path)["count"] == 2
    assert not list(tmp_path.rglob("*.tmp"))                         # atomic write leaves nothing behind
    (tmp_path / "props" / "rozbita.yaml").write_text("name: [nedopsano\n", encoding="utf-8")
    with pytest.raises(knihovna.KnihovnaError, match="rozbita"):
        knihovna.read("prop", "rozbita", tmp_path)


def test_lock_is_reentrant_in_a_thread_and_excludes_other_threads(tmp_path):
    knihovna.write("prop", "kvadr", {"count": 0}, tmp_path)
    with knihovna.lock("prop", "kvadr", tmp_path):
        with knihovna.lock("prop", "kvadr", tmp_path):           # a save inside a save (KLAPKA card_lock)
            knihovna.update("prop", "kvadr", {"count": 1}, tmp_path)
        other = threading.Thread(target=lambda: knihovna.update("prop", "kvadr", {"count": 99}, tmp_path))
        other.start()
        other.join(0.3)
        assert other.is_alive() and knihovna.read("prop", "kvadr", tmp_path)["count"] == 1
    other.join(5)
    assert knihovna.read("prop", "kvadr", tmp_path)["count"] == 99


def test_concurrent_processes_never_lose_a_write(tmp_path):
    knihovna.write("prop", "pocitadlo", {"name": "Počítadlo", "count": 0}, tmp_path)
    workers = [subprocess.Popen([sys.executable, str(HERE / "knihovna_worker.py"), str(tmp_path), "25"])
               for _ in range(6)]
    assert [w.wait(120) for w in workers] == [0] * 6
    assert knihovna.read("prop", "pocitadlo", tmp_path) == {"name": "Počítadlo", "count": 150}


def test_add_ref_copies_with_provenance_and_never_overwrites(tmp_path):
    knihovna.write("character", "caesar", {"name": "Caesar"}, tmp_path)
    src = tmp_path / "in" / "caesar.png"
    src.parent.mkdir()
    src.write_bytes(b"\x89PNG first")
    puvod = {"origin": "commons", "title": "Busta", "author": "Autor", "license": "CC BY-SA 4.0",
             "license_url": "https://creativecommons.org/licenses/by-sa/4.0/", "sha256": "stale", "width": 10,
             "height": 20, "added": "2026-10-29T10:00:00", "seen": True}
    dst = knihovna.add_ref("character", "caesar", src, puvod=puvod, base=tmp_path)
    assert dst == tmp_path / "characters" / "caesar" / "refs" / "caesar.png" and dst.read_bytes() == b"\x89PNG first"
    meta = knihovna.read_puvod(dst)
    assert list(meta) == ["origin", "title", "author", "license", "license_url", "sha256", "width", "height", "added"]
    assert meta["sha256"] == hashlib.sha256(b"\x89PNG first").hexdigest() and meta["license"] == "CC BY-SA 4.0"
    assert knihovna.add_ref("character", "caesar", src, base=tmp_path) == dst      # the same file is not added twice
    src.write_bytes(b"\x89PNG second")
    second = knihovna.add_ref("character", "caesar", src, base=tmp_path)
    assert second.name == "caesar-2.png" and dst.read_bytes() == b"\x89PNG first"
    assert knihovna.read_puvod(second) is None
    assert knihovna.read("character", "caesar", tmp_path) == {"name": "Caesar"}   # the card is untouched
    with pytest.raises(knihovna.KnihovnaError):
        knihovna.add_ref("character", "nikdo", src, base=tmp_path)
    with pytest.raises(knihovna.KnihovnaError):
        knihovna.add_ref("style", "default", src, base=tmp_path)


def test_trash_moves_everything_and_deletes_nothing(tmp_path):
    knihovna.write("style", "olej", {"name": "Olej", "look": "oil"}, tmp_path)
    (tmp_path / "styles" / "olej.png").write_bytes(b"png")
    (tmp_path / "styles" / "olej" / "samples").mkdir(parents=True)
    (tmp_path / "styles" / "olej" / "samples" / "1.jpg").write_bytes(b"jpg")
    dest = knihovna.trash("style", "olej", tmp_path)
    assert sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()) == \
        ["olej.png", "olej.yaml", "olej/STYLE.md", "olej/samples/1.jpg"]
    assert ".trash" in dest.parts and knihovna.slugs("style", tmp_path) == []
    knihovna.write("character", "x", {"name": "X"}, tmp_path)
    assert (knihovna.trash("character", "x", tmp_path) / "x" / "card.yaml").exists()
    with pytest.raises(knihovna.KnihovnaError):
        knihovna.trash("prop", "nic", tmp_path)


# ── the shared style card ────────────────────────────────────────────────────

# What KLAPKA's own code made of these cards (klapka.model.Library + the style lines of engine.build_shot
# + imaging._look), computed 2026-10-29 before phase 4.
KLAPKA_SYNTHETIC = {
    "zkusebni-noir": ({"name": "Zkušební noir", "look": "hard key light, deep shadows", "lens": "50mm, deep focus",
                       "grade": "cold silver grade", "negative": "watermark, extra fingers"},
                      ["Style: hard key light, deep shadows, 50mm, deep focus, cold silver grade.",
                       "sharp clarity, stable picture, no flicker, consistent faces and wardrobe across the shot.",
                       "Avoid: watermark, extra fingers."]),
    "zkusebni-pastel": ({"name": "Pastel", "look": "soft pastel animation.", "lens": "", "grade": "muted colours",
                         "negative": "", "constraints": "gentle motion, stable picture"},
                        ["Style: soft pastel animation., muted colours.", "gentle motion, stable picture."]),
    "zkusebni-holy": ({"look": "bare look"},
                      ["Style: bare look.",
                       "sharp clarity, stable picture, no flicker, consistent faces and wardrobe across the shot."]),
}


@pytest.mark.parametrize("slug", sorted(KLAPKA_SYNTHETIC))
def test_klapka_card_gives_klapkas_video_lines(slug):
    data, lines = KLAPKA_SYNTHETIC[slug]
    card = knihovna.from_klapka(data)
    assert knihovna.video_lines(card) == lines
    assert knihovna.video_text(card) == "\n".join(lines)
    assert knihovna.film_fields(card) == data | ({"negative": data["negative"]} if "negative" in data else {})
    # a card still in KLAPKA's old shape (lens, grade, negative at the top) reads the same
    assert knihovna.film_fields(data) == knihovna.film_fields(card)
    assert knihovna.image_text(data) == knihovna.image_text(card)


def test_klapka_card_layout_and_extra_fields_survive():
    card = knihovna.from_klapka({"negative": "x", "grade": "g", "look": "l", "name": "N", "ref_style": "r",
                                 "custom": 1}, puvod="z KLAPKY")
    assert list(card) == ["name", "look", "film", "avoid", "puvod", "custom"]
    assert card["film"] == {"grade": "g", "ref_style": "r"}


def test_grafik_card_layout_and_image_text():
    data = json.loads((REPO_STYLES / "akvarel-prirodovedny" / "style.json").read_text(encoding="utf-8"))
    card = knihovna.from_grafik(data)
    assert list(card) == ["name", "note", "obraz", "avoid", "origin", "puvod", "created", "updated"]
    assert list(card["obraz"]) == ["medium", "light", "line", "composition", "palette", "signature"]
    assert knihovna.image_text(card) == _grafik_prompt_text_ee7fd78(data)


def test_a_style_crosses_over():
    grafik = knihovna.from_grafik({"label": "Akvarel", "medium": "watercolour washes.", "light": "soft daylight",
                                   "line": "sepia ink", "composition": "single specimen", "avoid": "photo"})
    assert knihovna.video_lines(grafik) == [
        "Style: watercolour washes, soft daylight, sepia ink.",
        "sharp clarity, stable picture, no flicker, consistent faces and wardrobe across the shot.",
        "Avoid: photo."]
    klapka = knihovna.from_klapka(KLAPKA_SYNTHETIC["zkusebni-noir"][0])
    assert knihovna.image_text(klapka) == \
        "Hard key light, deep shadows. 50mm, deep focus. Cold silver grade. Avoid watermark, extra fingers"
    both = {**grafik, "look": "museum plate"}
    assert knihovna.image_text(both).startswith("Museum plate. Watercolour washes. Soft daylight")
    assert knihovna.video_lines(both)[0] == "Style: museum plate."


def test_style_md_is_written_with_the_card(tmp_path):
    knihovna.write("style", "noir", knihovna.from_klapka(KLAPKA_SYNTHETIC["zkusebni-noir"][0]), tmp_path)
    md = (tmp_path / "styles" / "noir" / "STYLE.md").read_text(encoding="utf-8")
    assert md.startswith("# Zkušební noir") and "## Film: objektiv a kamera" in md
    assert "Style: hard key light, deep shadows, 50mm, deep focus, cold silver grade." in md


# ── same prompt words as before, on the real styles ──────────────────────────
# Sources outside this public repo (KLAPKA's library is private, karikatura-3d-real is the operator's own):
# the test reads them where they live and is skipped on a machine without them.

KLAPKA = Path(os.environ.get("NGM_TEST_KLAPKA", "C:/Users/stock/Documents/000_NGM/KLAPKA"))
GRAFIK_STYLES = Path(os.environ.get("NGM_TEST_GRAFIK_STYLES", "C:/Users/stock/Documents/000_NGM/GRAFIK/styles"))


def _grafik_prompt_text_ee7fd78(card: dict) -> str:
    """engine/styles.py prompt_text() as it was before phase 4 (GRAFIK ee7fd78), frozen as the reference;
    every real card names its colours, so color_name() is not needed."""
    parts = [card[f].strip().rstrip(".") for f in ("medium", "light", "line", "composition") if card.get(f, "").strip()]
    if card.get("palette"):
        parts.append("colour palette: " + ", ".join(f"{c['name']} {c['hex']}" for c in card["palette"]))
    if card.get("avoid", "").strip():
        parts.append("avoid " + card["avoid"].strip().rstrip("."))
    return ". ".join(p[0].upper() + p[1:] for p in parts)


def test_frozen_reference_matches_the_old_output():
    data = json.loads((REPO_STYLES / "karikatura-3d" / "style.json").read_text(encoding="utf-8"))
    assert _grafik_prompt_text_ee7fd78(data) == (
        "Stylised 3D cartoon render, exaggerated proportions with large heads and expressive faces, soft clay-like "
        "materials. Bright cheerful key light with a soft rim light. Rounded shapes, smooth surfaces, no outlines. "
        "Character-focused framing on a simple, softly blurred background. Colour palette: purple #5b3c8f, orange "
        "#f07c3b, turquoise #2fb3c2, cream #f4e1c1. Avoid realistic skin texture, gloomy lighting")


def test_real_grafik_styles_give_the_same_image_prompt():
    sources = sorted(GRAFIK_STYLES.glob("*/style.json"))
    if not sources:
        pytest.skip(f"GRAFIK styles not found in {GRAFIK_STYLES}")
    for path in sources:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert all(c.get("name") for c in data.get("palette") or []), path
        assert knihovna.image_text(knihovna.from_grafik(data)) == _grafik_prompt_text_ee7fd78(data), path


def test_real_klapka_styles_give_the_same_style_and_video_lines():
    folder = KLAPKA / "studio" / "library" / "styles"
    sources = sorted(folder.glob("*.yaml"))
    if not sources:
        pytest.skip(f"KLAPKA styles not found in {folder}")
    sys.path.insert(0, str(KLAPKA))
    try:
        from klapka import engine as E
        from klapka import imaging as I
    except ImportError as e:
        pytest.skip(f"KLAPKA does not import here: {e}")
    finally:
        sys.path.remove(str(KLAPKA))
    for path in sources:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        # klapka.model.Library._load before phase 4
        old = E.Style(**({"name": path.stem} | {k: v for k, v in data.items() if k in E.Style.__dataclass_fields__}))
        card = yaml.safe_load(knihovna.dump(knihovna.from_klapka(data, puvod="x")))   # as stored in the library
        new = E.Style(**({"name": path.stem} | knihovna.film_fields(card)))
        assert new == old, path
        look = ", ".join(p for p in (old.look, old.lens, old.grade) if p)               # engine.build_shot
        lines = [f"Style: {look}."] if look else []
        lines += [old.constraints + "."] if old.constraints else []
        lines += [f"Avoid: {old.negative}."] if old.negative else []
        assert knihovna.video_lines(card) == lines, path
        assert I._look(new) == I._look(old), path


# ── conversion into the library ──────────────────────────────────────────────

def _sources(tmp_path: Path) -> tuple[Path, Path]:
    klapka, grafik = tmp_path / "klapka-library", tmp_path / "grafik-styles"
    files = {
        "characters/caesar/card.yaml": "name: Caesar\nprimary: caesar.png\n",
        "characters/caesar/refs/caesar.png": "png",
        "characters/caesar/figura/figura.json": "{}",
        "environments/alexandrie/card.yaml": "name: Alexandrie\n",
        "props/amfora.yaml": "name: Amfora\ncount: 1\n",
        "props/amfora/model/model.json": "{}",
        "props/zkouska.yaml": "name: Zkouška\n",
        "styles/default.yaml": "# comment\nname: noir\nlook: noir look\nlens: 35mm\ngrade: grain\nnegative: watermark\n",
        "styles/default.png": "png",
        "styles/kresba.yaml": "name: Kresba\nlook: pencil\n",
        "styles/kresba.20260923-052100.png.bak": "old png",
    }
    for rel, text in files.items():
        (klapka / rel).parent.mkdir(parents=True, exist_ok=True)
        (klapka / rel).write_text(text, encoding="utf-8")
    for slug in ("akvarel-prirodovedny", "karikatura-3d"):
        (grafik / slug).mkdir(parents=True)
        for f in (REPO_STYLES / slug).rglob("*"):
            if f.is_file():
                (grafik / slug / f.relative_to(REPO_STYLES / slug)).parent.mkdir(parents=True, exist_ok=True)
                (grafik / slug / f.relative_to(REPO_STYLES / slug)).write_bytes(f.read_bytes())
    (grafik / ".trash" / "20261023-old").mkdir(parents=True)
    (grafik / ".trash" / "20261023-old" / "style.json").write_text("{}", encoding="utf-8")
    return klapka, grafik


def _snapshot(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def test_conversion_copies_everything_and_is_idempotent(tmp_path):
    klapka, grafik = _sources(tmp_path)
    before = (_snapshot(klapka), _snapshot(grafik))
    target = tmp_path / "KNIHOVNA"
    dry = knihovna_prevod.run(klapka, grafik, target, dry_run=True)
    assert not target.exists() and dry["to_write"] == dry["files"] and dry["collisions"] == []
    r = knihovna_prevod.run(klapka, grafik, target)
    assert r["items"] == {"postavy": ["caesar"], "místa": ["alexandrie"], "rekvizity": ["amfora", "zkouska"],
                          "styly": ["akvarel-prirodovedny", "default", "karikatura-3d", "kresba"]}
    assert r["by_origin"] == {"styly KLAPKA": 2, "styly GRAFIK": 2}
    assert r["in_library"] == {"postavy": 1, "místa": 1, "rekvizity": 2, "styly": 4}
    assert r["written"] == r["files"] and r["skipped"] == ["GRAFIK .trash/: koš smazaných stylů"]
    assert (_snapshot(klapka), _snapshot(grafik)) == before                     # the sources are untouched
    for rel in ("characters/caesar/card.yaml", "characters/caesar/refs/caesar.png", "props/amfora/model/model.json",
                "styles/default.png", "styles/kresba.20260923-052100.png.bak"):
        assert (target / rel).read_bytes() == (klapka / rel).read_bytes(), rel
    noir = knihovna.read("style", "default", target)
    assert noir == {"name": "noir", "look": "noir look", "film": {"lens": "35mm", "grade": "grain"},
                    "avoid": "watermark", "puvod": "převedeno z KLAPKA studio/library/styles/default.yaml"}
    assert (target / "styles" / "karikatura-3d" / "samples" / "1.jpg").exists()
    assert (target / "styles" / "karikatura-3d" / "STYLE.md").exists()
    assert knihovna.image_text(knihovna.read("style", "karikatura-3d", target)) == _grafik_prompt_text_ee7fd78(
        json.loads((grafik / "karikatura-3d" / "style.json").read_text(encoding="utf-8")))
    again = knihovna_prevod.run(klapka, grafik, target)
    assert (again["to_write"], again["written"], again["already"]) == (0, 0, r["files"])


def test_conversion_stops_on_collisions_without_writing(tmp_path):
    klapka, grafik = _sources(tmp_path)
    (klapka / "styles" / "karikatura-3d.yaml").write_text("name: Kolize\nlook: x\n", encoding="utf-8")
    target = tmp_path / "KNIHOVNA"
    r = knihovna_prevod.run(klapka, grafik, target)
    assert r["written"] == 0 and not target.exists()
    assert len(r["collisions"]) == 1 and r["collisions"][0].startswith("styles/karikatura-3d.yaml: KLAPKA")
    # a card changed in the library after the conversion is not overwritten by a second run
    (klapka / "styles" / "karikatura-3d.yaml").unlink()
    knihovna_prevod.run(klapka, grafik, target)
    knihovna.update("style", "kresba", {"look": "pencil, edited"}, target)
    r = knihovna_prevod.run(klapka, grafik, target)
    assert r["written"] == 0 and r["collisions"] == [
        f"styles/kresba.yaml: v knihovně už je jiný obsah (zdroj KLAPKA {klapka / 'styles' / 'kresba.yaml'})"]
    assert knihovna.read("style", "kresba", target)["look"] == "pencil, edited"


def test_cli_dry_run_and_exit_codes(tmp_path, capsys):
    klapka, grafik = _sources(tmp_path)
    target = tmp_path / "KNIHOVNA"
    assert knihovna_prevod.main(["--klapka", str(klapka), "--grafik", str(grafik), "--cil", str(target),
                                 "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "nanečisto" in out and "styly: 4" in out and not target.exists()
    assert knihovna_prevod.main(["--klapka", str(tmp_path / "nic"), "--grafik", str(grafik)]) == 2
