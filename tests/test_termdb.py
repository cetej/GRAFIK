"""termdb (editorial term database, read-only): hints for the translator, checks for infographics.
The fixture rebuilds the traps found in the real BIOLIB/termdb.db on 2026-10-23."""
import sqlite3

import pytest

from engine.termdb import TermDB
from tests.test_engine_v2 import FakeSd, create_app, free_port, sdserver, wait_done  # noqa: F401

ROWS = [  # (term_id, canonical, domain, [(lang, name, is_primary), ...])
    (1, "Cantharellus cibarius", "biology", [("cs", "liška obecná", 1), ("en", "chanterelle", 1)]),
    (2, "liška obecná", "foreign_words", [("cs", "liška obecná", 1), ("en", "red fox, Vulpes vulpes", 1)]),
    (3, "Lynx lynx", "biology", [("cs", "rys ostrovid", 1), ("en", "Eurasian lynx", 1)]),
    (4, "Eurasian lynx", "biology", [("cs", "rys ostrovid", 1), ("en", "Eurasian lynx", 1)]),
    (5, "Praha", "geography", [("cs", "Praha", 1), ("en", "Prague", 1)]),
    (6, "Praha", "foreign_words", [("cs", "Praha", 1), ("en", "Prague (the capital city of the Czech Republic)", 1)]),
    (7, "most", "foreign_words", [("cs", "most", 1), ("en", "bridge", 1)]),
    (8, "Most", "geography", [("cs", "Most", 1)]),
    (9, "plachta", "foreign_words", [("cs", "plachta", 1), ("en", "sail", 1)]),
    (10, "Věž", "geography", [("cs", "Věž", 1)]),
    (11, "věž", "foreign_words", [("cs", "věž", 1), ("en", "tower", 1)]),
    (12, "bojový", "foreign_words", [("cs", "bojový", 1), ("en", "combat", 1)]),
    (13, "Vulpes vulpes", "biology", [("cs", "liška", 0), ("en", "Arctic Marble Fox", 0)]),
]


@pytest.fixture
def termdb_path(tmp_path):
    p = tmp_path / "termdb.db"
    con = sqlite3.connect(p)
    con.executescript("""
        CREATE TABLE terms (id INTEGER PRIMARY KEY, canonical_name TEXT NOT NULL, domain TEXT NOT NULL);
        CREATE TABLE translations (id INTEGER PRIMARY KEY, term_id INTEGER NOT NULL, name TEXT NOT NULL,
                                   language TEXT NOT NULL, is_primary BOOLEAN DEFAULT 0, source TEXT);
        CREATE INDEX idx_translations_name ON translations(name COLLATE NOCASE);
        CREATE INDEX idx_translations_term_lang ON translations(term_id, language);""")
    for tid, canonical, domain, names in ROWS:
        con.execute("INSERT INTO terms VALUES (?, ?, ?)", (tid, canonical, domain))
        con.executemany("INSERT INTO translations (term_id, language, name, is_primary) VALUES (?, ?, ?, ?)",
                        [(tid, lang, name, prim) for lang, name, prim in names])
    con.commit()
    con.close()
    return p


def test_classify_handles_the_real_traps(termdb_path):
    t = TermDB(termdb_path)
    assert t.classify("liška obecná")["status"] == "ambiguous"     # fungus in biology, red fox in the dictionary
    lynx = t.classify("rys ostrovid")
    assert lynx["status"] == "hint" and lynx["en"] == "Eurasian lynx" and lynx["latin"] == "Lynx lynx"
    assert t.classify("Praha")["en"] == "Prague"
    assert t.classify("most")["status"] == "known"                  # lower case: the bridge, not the town
    assert t.classify("Most")["status"] == "ambiguous"              # capital: town or bridge
    assert t.classify("věž")["status"] == "known"                   # not the village Věž
    assert t.classify("liška")["status"] == "missing"               # only non-primary backfill rows
    assert t.classify("kloun")["status"] == "missing"
    assert t.classify("Bojová")["status"] == "known"                # feminine adjective -> bojový


def test_glossary_and_check(termdb_path):
    t = TermDB(termdb_path)
    assert t.glossary("Rys ostrovid na střeše nad městem Praha") == ["Rys ostrovid = Eurasian lynx (Lynx lynx)", "Praha = Prague"]
    assert t.glossary("Liška obecná v lese") == []
    c = t.check("Bronzový kloun")
    assert c["missing"] == ["Bronzový", "kloun"] and c["ok"] == []
    assert t.check("Bojová věž") == {"text": "Bojová věž", "ok": ["Bojová", "věž"], "ambiguous": [], "missing": [], "hints": []}
    assert TermDB(None).glossary("rys ostrovid") == [] and not TermDB(termdb_path.with_name("nope.db")).available


def test_translator_gets_glossary_and_cache_key_changes(termdb_path, tmp_path, monkeypatch):
    from engine import translate
    sent = []
    monkeypatch.setattr(translate, "claude_text", lambda c, m, w: sent.append(c) or "A Eurasian lynx on a rock.")
    plain = translate.Translator(tmp_path / "a.jsonl")
    with_db = translate.Translator(tmp_path / "b.jsonl", TermDB(termdb_path))
    plain.translate("flux-local", "prompt", "Rys ostrovid na skále")
    with_db.translate("flux-local", "prompt", "Rys ostrovid na skále")
    assert "editorial term database" not in sent[0]
    assert "Rys ostrovid = Eurasian lynx (Lynx lynx)" in sent[1]
    assert plain.key("flux-local", "prompt", "x") != plain.key("flux-local", "prompt", "x", glossary=["a = b"])


def test_api_terms_check_and_settings(termdb_path, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from engine.backends import FluxLocal
    from engine.config import Settings
    monkeypatch.setattr(sdserver, "free_vram_mib", lambda: None)
    s = Settings(data_dir=tmp_path, flux_dir=tmp_path, sd_port=free_port(), gpu_lock_path=tmp_path / "gpu.lock",
                 termdb=str(termdb_path))
    sd = FakeSd(s)
    try:
        with TestClient(create_app(s, backends={"flux-local": FluxLocal(s, sd)}, server=sd)) as api:
            r = api.post("/api/v2/terms/check", json={"texts": ["Bronzový kloun", "", "Most"]}).json()
            assert r["available"] is True and [x["text"] for x in r["results"]] == ["Bronzový kloun", "Most"]
            assert r["results"][1]["ambiguous"][0]["phrase"] == "Most"
            svc = {x["id"]: x for x in api.get("/api/v2/settings").json()["services"]}
            assert svc["termdb"]["connected"] is True
    finally:
        sd.stop("test teardown")
