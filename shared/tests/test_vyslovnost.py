"""Sdílený slovník výslovnosti: přesné tvary jako dřív v NG-ROBOT, kmeny, zápis z editoru, hlášení kandidátů."""
import json
import threading

import pytest

from ngm_shared import vyslovnost as V

KMEN = {"mitochondri": {"respell": "mito-chondri", "kmen": True}}
# Skutečný zpětný přepis deseti vět komentáře k buňce (OmniVoice, Whisper small na CPU, 2026-11-01).
PREPIS = [
    ("Lidské tělo tvoří desítky bilionů buněk. Taková buňka funguje jako malé město.",
     "Lidské tělotvorí desítky bilionů buněk. Taková bunka funguje jako malé město."),
    ("V jádře je uložený návod, podle kterého buňka žije a pracuje. Je to její DNA.",
     "Vjádře je uložený návod, podle kterého bunka žije a pracuje. Je to její DNA."),
    ("V jadérku uvnitř jádra se staví drobné továrničky na bílkoviny, ribozomy.",
     "V jadérku uvnitř jádra se staví drobné továrničky na Bílkoviny Rybozome."),
    ("Ribozomy vyjdou ven, dostanou kopii návodu a skládají bílkoviny, dělníky buňky.",
     "Rybozomy výdou ven dostanou kopii návodu a skládají bílkoviny dělníky buňky."),
    ("Hotové bílkoviny míří sem, jako na poštu. Tady se upraví, zabalí a dostanou adresu.",
     "Hotové bílkoviny míří jsem jako na poštu. Tady se upraví zabalí a dostanou adresu."),
    ("Z tohoto středu se rozbíhají koleje a po nich buňkou cestují hotové balíčky.",
     "Z toho to středu se rozbíhají koleje a po nich bunkou cestují hotové balíčky."),
    ("Všechno to stojí energii. Tu vyrábějí ze živin a kyslíku mitochondrie, elektrárny buňky.",
     "Všechno to stojí energi. Tu vyrábějí ze živin a kyslíku mitochondrie elektrárny bunky."),
    ("Co dosloužilo, rozloží lyzozomy. Jsou to recyklační dvory, suroviny jdou znovu do oběhu.",
     "Co dosloužilo, rozloží lyzozomy. Sou to recyklační dvory suroviny douznovu do oběhu."),
    ("Celé město obepíná membrána s hlídanými branami. Dovnitř živiny, ven odpad a výrobky.",
     "Celé město obepíná membrána s hlídanými branami, do věc živiny, ven odpad a výrobky."),
    ("Právě teď se tohle děje ve vašem těle, v bilionech buněk najednou.",
     "Právě teď se tohle děje ve vašem těle v bilionech buněk na jednou."),
]


def test_slovnik_projde_kontrolou_a_ma_vsechny_puvodni_zdroje():
    entries = V.load()
    assert V.validate(entries) == []
    keys = {e["grapheme"] for e in entries}
    assert {"Yellowstone", "Panthera", "NASA", "Artemis II", "nahromadily", "ATP", "mitochondri"} <= keys


def test_kazda_presna_polozka_da_svuj_prepis_a_prepis_se_znovu_neprepise():
    for e in V.load():
        if e.get("kmen"):
            continue
        out, _ = V.apply(f"Slovo {e['grapheme']} tady.")
        assert out == f"Slovo {e['alias']} tady.", e["grapheme"]
        assert V.apply(out)[0] == out, e["grapheme"]


def test_presny_tvar_rozlisuje_velikost_a_hranici_slova():
    assert V.apply("PRESALE a ESA.", {"ESA": "Esa"})[0] == "PRESALE a Esa."
    assert V.apply("panthera je malé, Panthera velké", {"Panthera": "Pantera"})[0] == "panthera je malé, Pantera velké"
    assert V.apply("Čeleď Pantheraceae, rod Panthera.", {"Panthera": "Pantera"})[0] == "Čeleď Pantheraceae, rod Pantera."
    assert V.apply("NASY", {"NASA": "Nasa"})[0] == "NASY"


def test_delsi_klic_vyhrava_a_pocty_sedi():
    entries = {"Artemis": {"respell": "Artemis"}, "Artemis II": {"respell": "Artemis dvě"}}
    assert V.apply("Artemis II a Artemis.", entries)[0] == "Artemis dvě a Artemis."
    out, applied = V.apply("Panthera leo a Panthera tigris", {"Panthera": "Pantera"})
    assert out == "Pantera leo a Pantera tigris"
    assert applied == [{"grapheme": "Panthera", "alias": "Pantera", "count": 2}]


def test_ipa_jen_na_vyzadani_a_polozka_bez_prepisu_text_nezmeni():
    entries = {"Kilopower": {"respell": "Kilopauer", "ipa": "x"}}
    assert V.apply("Reaktor Kilopower.", entries)[0] == "Reaktor Kilopauer."
    assert V.apply("Reaktor Kilopower.", entries, use_ipa=True)[0] == 'Reaktor <phoneme alphabet="ipa" ph="x">Kilopower</phoneme>.'
    out, applied = V.apply("Slovo X.", {"X": {"note": "bez přepisu"}})
    assert out == "Slovo X." and applied == [{"grapheme": "X", "alias": "", "count": 1}]


@pytest.mark.parametrize("word,say", [
    ("mitochondrie", "mito-chondrie"), ("mitochondrií", "mito-chondrií"), ("mitochondrii", "mito-chondrii"),
    ("mitochondriím", "mito-chondriím"), ("mitochondriích", "mito-chondriích"), ("mitochondriemi", "mito-chondriemi"),
    ("Mitochondrie", "Mito-chondrie"),
])
def test_kmen_pokryje_vsechny_pady_i_zacatek_vety(word, say):
    assert V.apply(f"V buňce {word}.", KMEN)[0] == f"V buňce {say}."
    assert V.apply(f"V buňce {word}.")[0] == f"V buňce {say}."


@pytest.mark.parametrize("word", ["mitochondriální", "mitochondrion", "promitochondrie", "MITOCHONDRIE", "chondrie"])
def test_kmen_nezasahne_cizi_slovo(word):
    assert V.apply(f"V buňce {word}.", KMEN)[0] == f"V buňce {word}."


def test_kmen_kratsi_nez_slovo_nebere_jina_slova():
    entries = {"rover": {"respell": "rovr", "kmen": True}}
    assert V.apply("rovery, roverem a roverů", entries)[0] == "rovry, rovrem a rovrů"
    assert V.apply("roverka a rovernost", entries)[0] == "roverka a rovernost"


def test_pridavne_jmeno_ma_vlastni_polozku():
    assert V.apply("mitochondriální membrána")[0] == "mito-chondriální membrána"


def test_kmen_zkratky_a_jmena_nebere_jinou_velikost():
    entries = {"CERN": {"respell": "Cern", "kmen": True}}
    assert V.apply("V CERNu a CERN.", entries)[0] == "V Cernu a Cern."
    assert V.apply("cern a Cernu", entries)[0] == "cern a Cernu"


def test_presny_tvar_ma_prednost_pred_kmenem_a_delsi_kmen_pred_kratsim():
    entries = {**KMEN, "mitochondrie": "jinak"}
    assert V.apply("mitochondrie a mitochondrií", entries)[0] == "jinak a mito-chondrií"
    entries = {"Artemi": {"respell": "A", "kmen": True}, "Artemis": {"respell": "B", "kmen": True}}
    assert V.apply("Artemisu", entries)[0] == "Bu"


def test_covers_pocita_tvary_z_kmene():
    assert V.covers("mitochondrií", KMEN) and V.covers("Mitochondrie", KMEN)
    assert not V.covers("mitochondriální", KMEN)


def test_validate_hlida_kmen():
    assert any("ipa" in p for p in V.validate([{"grapheme": "kmenik", "alias": "x", "kmen": True, "ipa": "y"}]))
    assert any("kratší" in p for p in V.validate([{"grapheme": "lak", "alias": "x", "kmen": True}]))
    assert V.validate([{"grapheme": "ATP", "alias": "x", "kmen": True}]) == []
    assert any("číslici" in p for p in V.validate([{"grapheme": "CO2", "alias": "cé o 2"}]))
    assert any("duplicitní" in p for p in V.validate([{"grapheme": "X", "alias": "a"}, {"grapheme": "X", "alias": "b"}]))


def test_load_chybejici_je_prazdny_rozbity_je_chyba(tmp_path):
    assert V.load(tmp_path / "neni.json") == []
    bad = tmp_path / "rozbity.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="rozbitý"):
        V.load(bad)


def test_cesta_jde_prepsat_z_prostredi(tmp_path, monkeypatch):
    path = tmp_path / "jiny.json"
    path.write_text(json.dumps({"entries": [{"grapheme": "Slovo", "alias": "Jinak"}]}), encoding="utf-8")
    monkeypatch.setenv("NGM_VYSLOVNOST", str(path))
    assert V.apply("Slovo")[0] == "Jinak"


def test_load_map_vraci_tvar_pro_cz_text():
    entries = V.load_map()
    assert entries["NASA"]["respell"] == "Nasa"
    assert entries["SLS"]["ipa"]
    assert entries["mitochondri"]["kmen"] is True


def test_save_entry_prida_nahradi_a_necha_hlavicku(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"_comment": "hlava", "entries": [{"grapheme": "A", "alias": "a"}]}), encoding="utf-8")
    assert V.save_entry("Egypt", "Egipt", note="oprava", path=path) == (True, [])
    assert V.save_entry("Egypt", "Ídžipt", path=path) == (True, [])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["_comment"] == "hlava"
    assert [e["alias"] for e in data["entries"]] == ["a", "Ídžipt"]
    assert sum('"grapheme"' in line for line in path.read_text(encoding="utf-8").splitlines()) == 2


def test_save_entry_kmen_se_hned_pouzije(tmp_path):
    path = tmp_path / "s.json"
    assert V.save_entry("orchestr", "or-chestr", path=path, kmen=True) == (True, [])
    assert V.apply("v orchestru", V.load(path))[0] == "v or-chestru"


def test_save_entry_pri_problemu_nezapise(tmp_path):
    path = tmp_path / "s.json"
    saved, problems = V.save_entry("Egypt", "E2", path=path)
    assert saved is False and any("číslici" in p for p in problems)
    assert not path.exists()
    saved, problems = V.save_entry("Egypt", "Egypt", path=path)
    assert saved is False and any("nic by se nezměnilo" in p for p in problems)


def test_save_entry_soubeh_neztrati_slovo(tmp_path):
    path = tmp_path / "s.json"
    threads = [threading.Thread(target=V.save_entry, args=(f"Slovo{i}", f"slovo {chr(97 + i)}"), kwargs={"path": path})
               for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(V.load(path)) == 12


@pytest.mark.parametrize("text,heard,word,said", [
    ("Tu vyrábějí mitochondrie.", "Tu vyrábějí mitokondrie.", "mitochondrie", "mitokondrie"),
    ("Hrála část orchestru dnes.", "Hrála část orkerst dnes.", "orchestru", "orkerst"),
    ("Tahle ilustrace je pěkná.", "Tahle inustracie je pěkná.", "ilustrace", "inustracie"),
])
def test_kandidati_hlasi_podobne_slovo_napsane_jinak(text, heard, word, said):
    assert V.kandidati(text, heard) == [{"slovo": word, "slysel": said}]


def test_kandidati_stejny_prepis_nehlasi():
    assert V.kandidati("Tu vyrábějí mitochondrie.", "Tu vyrábějí mitochondrie.") == []


def test_kandidati_uplne_jine_slovo_nehlasi_to_je_neslysene():
    assert V.kandidati("Tloušťka tří setin milimetru.", "Tloušťka 300 mm milimetru.") == []


def test_kandidati_na_skutecnem_prepisu_nedelaji_sum():
    """Deset vět se správně slyšenou mitochondrií: Whisper píše jinak (bunka, Rybozome, Sou, do věc), kandidát žádný."""
    assert [V.kandidati(text, heard) for text, heard in PREPIS] == [[]] * len(PREPIS)
