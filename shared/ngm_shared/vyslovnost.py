"""Český slovník výslovnosti pro TTS, jeden pro všechny projekty (DECISIONS 2026-11-01).

Slovo se přepíše až těsně před TTS, text v editoru zůstává původní. Přepis českými písmeny funguje na každém
modelu, IPA jen tam, kde to volající zapne (`use_ipa`, SSML `<phoneme>` umí jen ElevenLabs řady v2).

    from ngm_shared.vyslovnost import apply
    apply("Mitochondrie vyrábějí energii.")
    # ("Mito-chondrie vyrábějí energii.", [{"grapheme": "mitochondri", "alias": "mito-chondri", "count": 1}])

Položka souboru `vyslovnost_cz.json` (cesta `NGM_VYSLOVNOST`, jinak vedle tohoto modulu):

    {"grapheme": "Yellowstone", "alias": "Jeloustoun", "type": "toponym", "ipa": "…", "note": "proč"}
    {"grapheme": "mitochondri", "alias": "mito-chondri", "kmen": true}

Bez `kmen` platí přesně zapsaný tvar: celé slovo, velikost písmen se rozlišuje, delší klíč vyhrává („Artemis II“
nad „Artemis“). S `kmen` platí i tvary s koncovkou z `KONCOVKY`, jiné pokračování slova ne, takže kmen nezasáhne
slovo, které jím jen začíná. Kmen s malým písmenem platí i na začátku věty a přepis pak dostane velké písmeno. Kmen
s velkým písmenem (jméno, zkratka) platí jen tak, jak je zapsaný. Přesně zapsaný tvar má před kmenem přednost.
Položka bez `kmen` s malým písmenem na začátku věty neplatí („rover“ nezachytí „Rover“), stejně jako před sloučením.

Oprava z editoru (`save_entry`) platí hned ve všech projektech, protože editovatelná instalace čte tento soubor
z hlavního checkoutu GRAFIK. V gitu ale není, dokud ji někdo necommitne (GRAFIK CLAUDE.md).

`kandidati` porovná zpětný přepis s textem a hlásí slova, která Whisper napsal jinak. Odlišný přepis je nález, stejný
důkaz není: Whisper píše i podle pravopisu. Slovník sám nemění, správnost potvrzuje poslech.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from collections.abc import Mapping
from difflib import SequenceMatcher
from pathlib import Path

from ngm_shared.knihovna import KnihovnaBusy, _os_lock, _retry, _unlock_byte

ENTRY_TYPES = ("name", "latin", "toponym", "term", "other")
# Pádové koncovky podstatných a přídavných jmen a tvary jmen osob (Hubblovi, Webbův). Slovesa sem nepatří.
KONCOVKY = ("", "a", "á", "e", "é", "ě", "i", "í", "o", "u", "ů", "y", "ý", "ou", "em", "ám", "ím", "ým", "ům", "ech",
            "ěch", "ách", "ích", "ých", "ami", "emi", "ěmi", "ími", "ými", "ému", "ímu", "ého", "ího", "ovi", "ové",
            "ův", "ova", "ovo", "ovu", "ovy", "ově", "ových")
# Kratší kmen s malým písmenem by zasáhl cizí slova (lak + y). Zkratku chrání velikost písmen.
MIN_KMEN = 4
PODOBNOST = 0.6         # od této podobnosti je to totéž slovo slyšené jinak; pod ní hlásí `unheard_words` v NG-ROBOT
MIN_SLOVO = 4           # krátká slova (předložky, spojky) Whisper mění běžně a o výslovnosti nic neříkají
_DIGIT = re.compile(r"\d")
_LOCK_WAIT_S = 5.0


def dict_path() -> Path:
    return Path(os.environ.get("NGM_VYSLOVNOST") or Path(__file__).with_name("vyslovnost_cz.json"))


def load(path=None) -> list[dict]:
    """Položky slovníku. Chybějící soubor je prázdný slovník, rozbitý je chyba: tichý návrat prázdného seznamu
    by nešel odlišit od prázdného slovníku a výslovnost by se tiše přestala používat."""
    p = Path(path) if path else dict_path()
    if not p.exists():
        return []
    try:
        # Windows na okamžik odmítne čtení, když `save_entry` právě soubor nahrazuje.
        return json.loads(_retry(p.read_text, "utf-8")).get("entries", [])
    except ValueError as e:
        raise ValueError(f"Slovník výslovnosti {p} je rozbitý: {e}") from e


def load_map(path=None) -> dict[str, dict]:
    """Stejný slovník jako {klíč: {respell, ipa, note, kmen}}, tvar pro NG-ROBOT `cz_text`."""
    out = {}
    for row in load(path):
        entry = {"respell": row.get("alias", "")}
        entry.update({k: row[k] for k in ("ipa", "note", "kmen") if row.get(k)})
        out[row["grapheme"]] = entry
    return out


def _rows(entries) -> list[dict]:
    """Seznam položek ze souboru, nebo {klíč: přepis | {respell, ipa, kmen}}. None je výchozí slovník."""
    if entries is None:
        return load()
    if not isinstance(entries, Mapping):
        return list(entries)
    rows = []
    for key, value in entries.items():
        if isinstance(value, str):
            rows.append({"grapheme": key, "alias": value})
        else:
            rows.append({"grapheme": key, "alias": value.get("respell") or value.get("alias") or "",
                         "ipa": value.get("ipa"), "kmen": value.get("kmen")})
    return rows


def _forms(rows: list[dict]) -> dict[str, tuple[dict, str]]:
    """{tvar v textu: (položka, přepis)}. Kmen se rozepíše do tvarů, delší kmen a přesný tvar přepíšou kratší kmen."""
    out = {}
    for row in sorted(rows, key=lambda r: (not r.get("kmen"), len(r.get("grapheme") or ""))):
        word, say = row.get("grapheme") or "", row.get("alias") or ""
        if not word:
            continue
        if not row.get("kmen"):
            out[word] = (row, say)
            continue
        for end in KONCOVKY:
            out[word + end] = (row, say and say + end)
            if word[0].islower():
                out[word[0].upper() + word[1:] + end] = (row, say and say[0].upper() + say[1:] + end)
    return out


def apply(text: str, entries=None, use_ipa: bool = False) -> tuple[str, list[dict]]:
    """(text pro TTS, [{grapheme, alias, count}]). Jeden průchod textem, přepis se znovu nepřepisuje.

    Položka bez přepisu text nezmění a vrátí prázdný `alias`, ať to volající může nahlásit."""
    forms = _forms(_rows(entries))
    if not text or not forms:
        return text, []
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(f) for f in sorted(forms, key=len, reverse=True)) + r")(?!\w)")
    applied: dict[str, dict] = {}

    def repl(m: re.Match) -> str:
        word = m.group(0)
        row, say = forms[word]
        # IPA popisuje celé slovo, u kmene by neseděla ke koncovce.
        if use_ipa and row.get("ipa") and not row.get("kmen"):
            say = f'<phoneme alphabet="ipa" ph="{row["ipa"]}">{word}</phoneme>'
            alias = say
        else:
            alias = row.get("alias") or ""
        hit = applied.setdefault(row["grapheme"], {"grapheme": row["grapheme"], "alias": alias, "count": 0})
        hit["count"] += 1
        return say or word

    return pattern.sub(repl, text), list(applied.values())


def covers(word: str, entries=None) -> bool:
    """Má slovník tenhle celý tvar? Počítá i tvary z kmene, proto ne `word in slovník`."""
    return word in _forms(_rows(entries))


def validate(entries: list[dict]) -> list[str]:
    """Problémy slovníku (prázdný seznam = v pořádku). Hlídá, na čem by výslovnost tiše selhala."""
    problems, seen = [], set()
    for i, row in enumerate(entries, start=1):
        word, alias = (row.get("grapheme") or "").strip(), (row.get("alias") or "").strip()
        if not word:
            problems.append(f"záznam #{i}: prázdný 'grapheme'")
            continue
        if not alias:
            problems.append(f"záznam #{i} ('{word}'): prázdný 'alias'")
        if _DIGIT.search(alias):
            problems.append(f"záznam #{i} ('{word}'): alias obsahuje číslici — TTS ji přečte doslova")
        if word in seen:
            problems.append(f"záznam #{i}: duplicitní 'grapheme' '{word}'")
        seen.add(word)
        etype = row.get("type", "other")
        if etype not in ENTRY_TYPES:
            problems.append(f"záznam #{i} ('{word}'): neznámý 'type' '{etype}' (povolené: {ENTRY_TYPES})")
        if row.get("kmen"):
            if row.get("ipa"):
                problems.append(f"záznam #{i} ('{word}'): kmen nemůže mít 'ipa', ta popisuje celé slovo")
            if word[0].islower() and len(word) < MIN_KMEN:
                problems.append(f"záznam #{i} ('{word}'): kmen kratší než {MIN_KMEN} písmena zasáhne cizí slova")
    return problems


def _dump(data: dict) -> str:
    """Jedna položka na řádek, ať je v gitu vidět jedno změněné slovo."""
    head = {k: v for k, v in data.items() if k != "entries"}
    rows = ",\n".join("    " + json.dumps(e, ensure_ascii=False) for e in data["entries"])
    top = "".join(f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)},\n" for k, v in head.items())
    return "{\n" + top + '  "entries": [\n' + rows + "\n  ]\n}\n"


def save_entry(grapheme: str, alias: str, etype: str = "other", note: str = "", path=None,
               kmen: bool = False) -> tuple[bool, list[str]]:
    """Přidá nebo přepíše položku (editor „Opravit výslovnost“). Stejný klíč se nahradí, zbytek souboru zůstane.

    Před zápisem projde celý slovník `validate`; při problému se nic nezapíše. Vrací (uloženo, problémy)."""
    target = Path(path) if path else dict_path()
    grapheme, alias = (grapheme or "").strip(), (alias or "").strip()
    new: dict = {"grapheme": grapheme, "alias": alias, "type": etype if etype in ENTRY_TYPES else "other"}
    if kmen:
        new["kmen"] = True
    if note:
        new["note"] = note
    try:
        lock = _os_lock(Path.home() / ".ngm-vyslovnost.lock", _LOCK_WAIT_S, "slovník výslovnosti")
    except KnihovnaBusy as e:
        return False, [str(e)]
    try:
        data = json.loads(_retry(target.read_text, "utf-8")) if target.exists() else {"entries": []}
        entries = [e for e in data.get("entries", []) if (e.get("grapheme") or "").strip() != grapheme] + [new]
        problems = validate(entries)
        if alias == grapheme:
            problems.append(f"'{grapheme}': alias je stejný jako slovo — nic by se nezměnilo")
        if problems:
            return False, problems
        data["entries"] = entries
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f"{target.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
        tmp.write_text(_dump(data), encoding="utf-8", newline="\n")
        _retry(os.replace, tmp, target)
        return True, []
    finally:
        _unlock_byte(lock)
        lock.close()


def _words(text: str) -> list[tuple[str, str]]:
    """[(slovo, tvar k porovnání)]. Tvar stírá, co Whisper mění, i když to zní stejně: diakritiku (d/ď neslyší),
    i/y (ribozomy, rybozomy) a j před s, d (jsou, sou; vyjdou, vydou)."""
    out = []
    for w in re.findall(r"[^\W_]+", text):
        plain = "".join(c for c in unicodedata.normalize("NFD", w.lower()) if not unicodedata.combining(c))
        out.append((w, re.sub(r"j(?=[sd])", "", plain.replace("y", "i"))))
    return out


def _different(a: str, b: str) -> bool:
    """Totéž slovo slyšené jinak? Rozdíl jen v koncovce je Whisper, ne výslovnost (buňka, buňky)."""
    if a == b or len(a) < MIN_SLOVO or _DIGIT.search(a) or _DIGIT.search(b):
        return False
    prefix = len(os.path.commonprefix([a, b]))
    if prefix >= min(len(a), len(b)) - 2:
        return False
    return SequenceMatcher(None, a, b, autojunk=False).ratio() >= PODOBNOST


def kandidati(text: str, heard: str) -> list[dict]:
    """Slova, která Whisper napsal jinak než text: [{"slovo": "mitochondrie", "slysel": "mitokondrie"}].

    Hlásí se jen podobné tvary. Úplně jiné slovo je jiný nález (zaznělo něco jiného), to hlásí `unheard_words`
    v NG-ROBOT. Slovo rozdělené nebo slepené přepisem („Lúk Raňan“, „Lukraňan“) se porovná bez mezer."""
    exp, got = _words(text), _words(heard)
    out = []
    sm = SequenceMatcher(None, [n for _, n in exp], [n for _, n in got], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "replace":
            continue
        if i2 - i1 == j2 - j1:
            pairs = [(exp[i1 + k], got[j1 + k][0], got[j1 + k][1]) for k in range(i2 - i1)]
        else:
            if i2 - i1 != 1 and j2 - j1 != 1:
                continue
            joined = " ".join(w for w, _ in got[j1:j2])
            pairs = [(("".join(w for w, _ in exp[i1:i2]), "".join(n for _, n in exp[i1:i2])), joined,
                      "".join(n for _, n in got[j1:j2]))]
        for (word, norm), said, said_norm in pairs:
            if _different(norm, said_norm):
                out.append({"slovo": word, "slysel": said})
    return out
