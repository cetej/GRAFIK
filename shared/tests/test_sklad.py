import json

import pytest

from ngm_shared import sklad

OPUS = [
    {"slug": "emollick-019567", "author": "emollick", "post_url": "https://x.com/emollick/status/2103688362960019567",
     "category": "explainer", "tech_tags": ["canvas"], "prompt": "A video explaining recursion in a radically different style",
     "prompt_partial": False, "poster_url": "https://media.skillry.dev/opus-5-5/emollick-019567/original.1.webp",
     "skillry_url": "https://skillry.dev/x", "added": "2026-09-26"},
    {"slug": "linearuncle-971663", "author": "LinearUncle", "post_url": "https://x.com/LinearUncle/status/2103128559174971663",
     "category": "explainer", "tech_tags": ["svg", "audio"], "prompt": "请用Manim给我制作一个导数概念学习的视频，配音使用edge-tts",
     "prompt_partial": False, "poster_url": "https://media.skillry.dev/opus-5-5/linearuncle-971663/original.2.webp",
     "skillry_url": "", "added": "2026-09-27"},
    {"slug": "bez-url", "author": "x", "post_url": "", "category": "motion", "tech_tags": [], "prompt": "p"},
]
CLAUDE = [
    {"post_id": "2103688362960019567", "creator": "emollick", "source_url": "https://x.com/emollick/status/2103688362960019567",
     "first_listed_date": "2026-09-26", "model_tags": "Opus;Sonnet", "title_en": "Recursion explainer",
     "category": "educational_explainer", "thumbnail": ""},
    {"post_id": "2108018789468250448", "creator": "nicceasy", "source_url": "https://x.com/nicceasy/status/2108018789468250448",
     "first_listed_date": "2026-10-11", "model_tags": "Opus", "title_en": "Braun turntable film",
     "category": "product", "thumbnail": "assets/a/2108018789468250448.jpg"},
    {"post_id": "1", "creator": "y", "source_url": "https://x.com/y/status/1", "first_listed_date": "2026-10-01",
     "model_tags": "", "title_en": "Something new", "category": "creator demo or comparison reply", "thumbnail": ""},
]


def test_index_spoji_stejny_prispevek_z_obou_sbirek():
    index = sklad.sestav_index(OPUS, CLAUDE, {"2108018789468250448": "namety/claude55-videos/nahledy/x.jpg"})
    ids = [z["id"] for z in index]
    assert len(ids) == len(set(ids)) == 4  # záznam bez post_url vypadne, emollick je jeden
    em = next(z for z in index if z["id"] == "2103688362960019567")
    assert em["zdroje"] == ["opus55-videos", "claude55-videos"]
    assert em["prompt"].startswith("A video explaining recursion")
    assert em["nazev"] == "Recursion explainer"
    assert em["modely"] == ["Opus", "Sonnet"]
    assert em["kategorie"] == "vysvetleni"


def test_kategorie_se_prevadeji_a_nezname_jsou_jine():
    index = sklad.sestav_index(OPUS, CLAUDE, {})
    kat = {z["id"]: z["kategorie"] for z in index}
    assert kat["2108018789468250448"] == "produkt"
    assert kat["1"] == "jine"
    assert set(kat.values()) <= set(sklad.KATEGORIE)


def test_index_razeny_od_nejnovejsiho():
    index = sklad.sestav_index(OPUS, CLAUDE, {})
    assert [z["pridano"] for z in index] == sorted((z["pridano"] for z in index), reverse=True)


def test_hledej_bez_diakritiky_podle_shody_a_filtru():
    index = sklad.sestav_index(OPUS, CLAUDE, {})
    assert [z["id"] for z in sklad.hledej("RECURSION", index=index)] == ["2103688362960019567"]
    assert [z["autor"] for z in sklad.hledej("manim edge-tts", index=index)] == ["LinearUncle"]
    assert {z["id"] for z in sklad.hledej("", kategorie="vysvetleni", index=index)} == {
        "2103688362960019567", "2103128559174971663"}
    assert [z["autor"] for z in sklad.hledej("", technika="audio", index=index)] == ["LinearUncle"]
    assert all(z["prompt"] for z in sklad.hledej("", jen_s_promptem=True, index=index))
    assert sklad.hledej("xyzzy", index=index) == []
    assert [z["id"] for z in sklad.hledej("recurs", index=index)] == ["2103688362960019567"]
    assert sklad.hledej("ursion", index=index) == []  # uvnitř slova se nehledá
    assert [z["autor"] for z in sklad.hledej("导数", index=index)] == ["LinearUncle"]
    with pytest.raises(sklad.SkladError):
        sklad.hledej("x", kategorie="neexistuje", index=index)


def test_stahni_namety_zapise_sklad_bez_site(monkeypatch, tmp_path):
    def fake_get(url):
        if url == sklad.ZDROJE["opus55-videos"]["data"]:
            return json.dumps(OPUS).encode()
        if url == sklad.ZDROJE["claude55-videos"]["data"]:
            head = ",".join(CLAUDE[0])
            rows = [",".join(f'"{r[k]}"' for k in CLAUDE[0]) for r in CLAUDE]
            return ("\n".join([head, *rows]) + "\n").encode()
        if "linearuncle" in url:
            raise sklad.SkladError(f"{url}: HTTP 404")
        return b"IMG"

    monkeypatch.setattr(sklad, "_get", fake_get)
    stav = sklad.stahni_namety(log=lambda s: None)
    assert stav == {"zaznamu": 4, "s_promptem": 2, "s_nahledem": 2, "novych_nahledu": 2, "chyb_nahledu": 1}
    root = tmp_path / "sklad"
    assert sklad.root() == root
    index = sklad.nacti_index()
    em = next(z for z in index if z["id"] == "2103688362960019567")
    assert sklad.cesta(em).read_bytes() == b"IMG"
    assert (root / "README.md").exists() and (root / "namety" / "puvod.json").exists()
    assert not list(root.rglob("*.tmp"))

    # druhý běh nestahuje náhledy znovu
    assert sklad.stahni_namety(log=lambda s: None)["novych_nahledu"] == 0


def test_nacti_index_bez_stazeni_hlasi_co_spustit():
    with pytest.raises(sklad.SkladError, match="stahni namety"):
        sklad.nacti_index()
