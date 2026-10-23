"""Editorial term database (termdb, shared with NG-ROBOT) — read-only, local, free.

termdb.db lives in BIOLIB (NG-ROBOT config.py MULTI_DOMAIN_DB_PATH): SQLite with `terms`
(canonical_name, domain) and `translations` (name, language, is_primary). GRAFIK uses it two ways
(operator 2026-10-23):
- translation hint: Czech terms that termdb knows unambiguously go to the Claude translator as a
  glossary ("rys ostrovid = Eurasian lynx (Lynx lynx)");
- check: labels of an infographic show which terms termdb confirms, which are ambiguous and which
  are not in termdb at all. NG-ROBOT's paid web-search fallback is deliberately not used.

Ambiguity is the real risk (measured 2026-10-23): "liška obecná" is a fungus in the biology domain
while the dictionary says red fox; "most" is a town and a bridge. A term is passed on only when every
specialist sense agrees and the dictionary gloss (if any) names the same thing.
"""
from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

SPECIALIST = ("biology", "geography", "medicine", "chemistry", "astronomy", "geology", "specialized", "general")
DICTIONARY = "foreign_words"
WORD = re.compile(r"[^\W\d_][^\W_]*(?:-[^\W\d_]+)*", re.UNICODE)
MAX_NGRAM = 3


class TermDB:
    def __init__(self, path: Path | None):
        self.path = path
        self._local = threading.local()

    @property
    def available(self) -> bool:
        return bool(self.path and self.path.is_file())

    def _db(self) -> sqlite3.Connection:
        con = getattr(self._local, "con", None)
        if con is None:
            con = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
            self._local.con = con
        return con

    def senses(self, phrase: str) -> list[dict]:
        """Primary Czech entries for the exact phrase (case-insensitive), with their English name."""
        if not self.available:
            return []
        rows = self._db().execute(
            """SELECT t.id, t.canonical_name, t.domain, tr.name,
                      (SELECT e.name FROM translations e INDEXED BY idx_translations_term_lang WHERE e.term_id = t.id AND e.language = 'en'
                       ORDER BY e.is_primary DESC LIMIT 1)
               FROM translations tr INDEXED BY idx_translations_name JOIN terms t ON t.id = tr.term_id
               WHERE tr.name = ? COLLATE NOCASE AND tr.language = 'cs' AND tr.is_primary = 1""", (phrase,)).fetchall()
        seen, out = set(), []
        for tid, canonical, domain, name, en in rows:
            # a place name only matches with its capital letter ("věž" is not the village Věž)
            if domain == "geography" and name != phrase and name[:1].isupper() and not phrase[:1].isupper():
                continue
            if tid not in seen and domain != "encyclopedia":  # cswiktionary rows carry no English
                seen.add(tid)
                out.append({"id": tid, "canonical": canonical, "domain": domain, "en": en})
        return out

    def classify(self, phrase: str) -> dict:
        """status: hint (one specialist sense, dictionary agrees) | known (dictionary word only) |
        ambiguous | missing."""
        senses = self.senses(phrase)
        if not senses and " " not in phrase and phrase[-1:].lower() in ("á", "é"):
            senses = self.senses(phrase[:-1] + "ý")  # feminine/neuter adjective -> dictionary form
        spec = [s for s in senses if s["domain"] in SPECIALIST]
        dic = [s for s in senses if s["domain"] == DICTIONARY]
        out = {"phrase": phrase, "senses": [_label(s) for s in senses]}
        if not senses:
            return {**out, "status": "missing"}
        if not spec:
            return {**out, "status": "known"}
        # biology: a taxon with a Latin canonical name wins over an English-only duplicate
        # ("rys ostrovid": Lynx lynx vs. a web-enriched "Eurasian lynx")
        latin = [s for s in spec if s["domain"] == "biology" and s["en"] and s["canonical"].lower() != s["en"].lower()]
        if latin:
            spec = latin + [s for s in spec if s["domain"] != "biology"]
        names = {(s["en"] or "").lower() for s in spec} | {s["canonical"].lower() for s in spec}
        one_thing = len({s["canonical"].lower() for s in spec}) == 1 or len({(s["en"] or "").lower() for s in spec} - {""}) == 1
        dict_agrees = all(any(n and n in (d["en"] or "").lower() for n in names) for d in dic)
        if one_thing and dict_agrees:
            s = spec[0]
            en = next((x["en"] for x in spec if x["en"]), None) or s["canonical"]
            latin = s["canonical"] if s["domain"] == "biology" and s["canonical"] != en else None
            if en.lower() == phrase.lower() and not latin:  # nothing to tell the translator (village "Štíty")
                return {**out, "status": "known"}
            return {**out, "status": "hint", "en": en, "latin": latin}
        return {**out, "status": "ambiguous"}

    def scan(self, text: str) -> list[dict]:
        """Longest known phrases (up to three words) in a free Czech text, left to right."""
        words = WORD.findall(text)
        found, i = [], 0
        while i < len(words):
            for n in range(min(MAX_NGRAM, len(words) - i), 0, -1):
                c = self.classify(" ".join(words[i:i + n]))
                if c["status"] != "missing" and (n > 1 or len(words[i]) > 2):
                    found.append(c)
                    i += n
                    break
            else:
                found.append({"phrase": words[i], "status": "missing", "senses": []})
                i += 1
        return found

    def glossary(self, text: str) -> list[str]:
        """Translator hints for the unambiguous specialist terms of a Czech text."""
        out = []
        for c in self.scan(text):
            if c["status"] == "hint":
                line = f"{c['phrase']} = {c['en']}" + (f" ({c['latin']})" if c.get("latin") else "")
                if line not in out:
                    out.append(line)
        return out

    def check(self, text: str) -> dict:
        """For the infographic check: what termdb confirms, what is ambiguous, what it does not know."""
        found = self.scan(text)
        return {
            "text": text,
            "ok": [c["phrase"] for c in found if c["status"] in ("hint", "known")],
            "ambiguous": [{"phrase": c["phrase"], "senses": c["senses"]} for c in found if c["status"] == "ambiguous"],
            "missing": [c["phrase"] for c in found if c["status"] == "missing" and len(c["phrase"]) > 3],
            "hints": [f"{c['phrase']} = {c['en']}" + (f" ({c['latin']})" if c.get("latin") else "")
                      for c in found if c["status"] == "hint"],
        }


def _label(s: dict) -> str:
    return f"{s['canonical']} ({s['domain']}{', ' + s['en'] if s['en'] and s['en'] != s['canonical'] else ''})"
