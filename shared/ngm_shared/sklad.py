"""Sklad na D: — náměty videí (fáze F1) pro POHYB, KLAPKA a GRAFIK; návrh STOPA `outputs/2026-11-04-sklad-namety-a-3d-modely.md`.

    NGM_SKLAD (výchozí D:/NGM-SKLAD)/
      README.md                          co ve skladu je a pod jakou licencí
      namety/
        index.json                       jeden index obou sbírek (hledá `hledej`)
        opus55-videos/videos.json        surová data yihui-dev/awesome-opus5-5-videos (MIT)
        opus55-videos/nahledy/<id>.webp  náhled videa (dílo autora, jen lokální reference)
        claude55-videos/collection-index.csv   athemeroy/awesome-claude-5-5-videos (CC BY 4.0)
        claude55-videos/nahledy/<id>.jpg
        puvod.json                       odkud, kdy a pod jakou licencí

Stahují se texty promptů, metadata a náhledy, nikdy videa (patří autorům a hromadné stahování z X je
mimo pravidla služby). Náměty jsou inspirace pro režii, ne obsah: prompt ani náhled nejde do výstupu.
`id` záznamu je číslo příspěvku na X, takže stejný příspěvek z obou sbírek je jeden záznam.

    python -m ngm_shared.sklad stahni namety [--bez-nahledu]
    python -m ngm_shared.sklad hledej recursion explainer [--kategorie vysvetleni] [--limit 5]
    python -m ngm_shared.sklad stav
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
from collections import Counter
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

DEFAULT_ROOT = Path("D:/NGM-SKLAD")
UA = {"User-Agent": "NGM-sklad/1 (https://github.com/cetej/GRAFIK)"}
TIMEOUT_S = 30

ZDROJE = {
    "opus55-videos": {
        "repo": "https://github.com/yihui-dev/awesome-opus5-5-videos",
        "data": "https://raw.githubusercontent.com/yihui-dev/awesome-opus5-5-videos/main/data/videos.json",
        "soubor": "videos.json",
        "licence": "MIT (texty a data); náhledy patří autorům videí",
    },
    "claude55-videos": {
        "repo": "https://github.com/athemeroy/awesome-claude-5-5-videos",
        "data": "https://raw.githubusercontent.com/athemeroy/awesome-claude-5-5-videos/main/data/collection-index.csv",
        "soubor": "collection-index.csv",
        "raw": "https://raw.githubusercontent.com/athemeroy/awesome-claude-5-5-videos/main/",
        "licence": "CC BY 4.0 (texty a data, uveď athemeroy/awesome-claude-5-5-videos); náhledy patří autorům",
    },
}

# Společné kategorie (klíč → popisek); kategorie sbírek se na ně převádějí v _KAT_OPUS a _KAT_CLAUDE.
KATEGORIE = {
    "motion": "Motion grafika",
    "vysvetleni": "Vysvětlení",
    "3d": "3D scéna",
    "interaktivni": "Hra a interaktivní",
    "postavy": "Postavy",
    "hudba": "Hudba",
    "strih": "Střih záznamu",
    "ai-video": "AI video model",
    "produkt": "Produkt",
    "jine": "Jiné",
}
_KAT_OPUS = {"motion": "motion", "3d": "3d", "explainer": "vysvetleni", "interactive": "interaktivni"}
_KAT_CLAUDE = {
    "procedural_2d": "motion", "motion": "motion",
    "educational_explainer": "vysvetleni", "science": "vysvetleni", "history": "vysvetleni",
    "3d_or_realtime_graphics": "3d",
    "interactive": "interaktivni", "app_or_game_capture": "interaktivni",
    "character": "postavy", "music": "hudba",
    "existing_source_transformation": "strih", "editing": "strih",
    "external_video_model": "ai-video", "product": "produkt",
}
_STATUS = re.compile(r"/status/(\d+)")
# Latinka a číslice zvlášť od ostatních písem: „请用manim给我“ dá slovo „manim“. Latinské slovo dotazu
# se shoduje se začátkem slova textu (recurs → recursion), jiné písmo (čínština bez mezer) kdekoli v textu.
_SLOVO = re.compile(r"[a-z0-9]+|[^\W\da-z_]+")


class SkladError(RuntimeError):
    pass


def root() -> Path:
    return Path(os.environ.get("NGM_SKLAD") or DEFAULT_ROOT)


def namety_dir() -> Path:
    return root() / "namety"


def _bez_diakritiky(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def _post_id(url: str) -> str | None:
    m = _STATUS.search(url or "")
    return m.group(1) if m else None


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _get(url: str) -> bytes:
    """Jeden opakovaný pokus na přechodnou chybu (timeout, 5xx), 404 a jiné 4xx hned dál."""
    for pokus in (1, 2):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=TIMEOUT_S) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500 or pokus == 2:
                raise SkladError(f"{url}: HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if pokus == 2:
                raise SkladError(f"{url}: {e}") from e
        time.sleep(5)
    raise AssertionError("unreachable")


def sestav_index(opus: list[dict], claude: list[dict], nahledy: dict[str, str]) -> list[dict]:
    """Jeden seznam záznamů z obou sbírek; `nahledy` mapuje id → cesta náhledu relativně ke kořeni skladu."""
    zaznamy: dict[str, dict] = {}
    for row in opus:
        pid = _post_id(row.get("post_url", ""))
        if not pid:
            continue
        zaznamy[pid] = {
            "id": pid,
            "zdroje": ["opus55-videos"],
            "autor": row.get("author") or "",
            "post_url": row["post_url"],
            "kategorie": _KAT_OPUS.get(row.get("category", ""), "jine"),
            "techniky": list(row.get("tech_tags") or []),
            "prompt": row.get("prompt") or "",
            "prompt_cast": bool(row.get("prompt_partial")),
            "nazev": "",
            "modely": ["Opus"],
            "skillry_url": row.get("skillry_url") or "",
            "pridano": row.get("added") or "",
        }
    for row in claude:
        pid = _post_id(row.get("source_url", "")) or row.get("post_id") or ""
        if not pid:
            continue
        modely = [m for m in (row.get("model_tags") or "").split(";") if m]
        z = zaznamy.get(pid)
        if z:
            z["zdroje"].append("claude55-videos")
            z["nazev"] = row.get("title_en") or z["nazev"]
            z["modely"] = sorted(set(z["modely"]) | set(modely))
            continue
        zaznamy[pid] = {
            "id": pid,
            "zdroje": ["claude55-videos"],
            "autor": row.get("creator") or "",
            "post_url": row.get("source_url") or "",
            "kategorie": _KAT_CLAUDE.get(row.get("category", ""), "jine"),
            "techniky": [],
            "prompt": "",
            "prompt_cast": False,
            "nazev": row.get("title_en") or "",
            "modely": modely,
            "skillry_url": "",
            "pridano": row.get("first_listed_date") or "",
        }
    for pid, z in zaznamy.items():
        z["nahled"] = nahledy.get(pid, "")
    return sorted(zaznamy.values(), key=lambda z: (z["pridano"], z["id"]), reverse=True)


def _stahni_nahled(url: str, cil: Path) -> bool:
    if cil.exists() and cil.stat().st_size > 0:
        return False
    _write_atomic(cil, _get(url))
    return True


def stahni_namety(nahledy: bool = True, log: Callable[[str], None] = print) -> dict:
    """Stáhne obě sbírky, náhledy (jen chybějící) a přepíše index. Opakovatelné, nic nemaže."""
    base = namety_dir()
    opus_raw = _get(ZDROJE["opus55-videos"]["data"])
    claude_raw = _get(ZDROJE["claude55-videos"]["data"])
    _write_atomic(base / "opus55-videos" / ZDROJE["opus55-videos"]["soubor"], opus_raw)
    _write_atomic(base / "claude55-videos" / ZDROJE["claude55-videos"]["soubor"], claude_raw)
    opus = json.loads(opus_raw.decode("utf-8"))
    claude = list(csv.DictReader(io.StringIO(claude_raw.decode("utf-8-sig"))))
    log(f"opus55-videos: {len(opus)} záznamů, claude55-videos: {len(claude)} záznamů")

    mapa: dict[str, str] = {}
    nove = chyby = 0
    kandidati: list[tuple[str, str, Path]] = []
    for row in opus:
        pid, url = _post_id(row.get("post_url", "")), row.get("poster_url") or ""
        if pid and url:
            kandidati.append((pid, url, base / "opus55-videos" / "nahledy" / f"{pid}{Path(url).suffix or '.webp'}"))
    for row in claude:
        pid, thumb = _post_id(row.get("source_url", "")) or row.get("post_id"), row.get("thumbnail") or ""
        if pid and thumb:
            kandidati.append((pid, ZDROJE["claude55-videos"]["raw"] + thumb,
                              base / "claude55-videos" / "nahledy" / f"{pid}{Path(thumb).suffix or '.jpg'}"))
    for pid, url, cil in kandidati:
        if pid in mapa:
            continue
        if nahledy:
            try:
                nove += _stahni_nahled(url, cil)
            except SkladError as e:
                chyby += 1
                log(f"náhled {pid}: {e}")
        if cil.exists():
            mapa[pid] = cil.relative_to(root()).as_posix()

    index = sestav_index(opus, claude, mapa)
    _write_atomic(base / "index.json", json.dumps(index, ensure_ascii=False, indent=1).encode("utf-8"))
    ted = datetime.now().isoformat(timespec="seconds")
    puvod = {k: {"repo": v["repo"], "data": v["data"], "licence": v["licence"], "stazeno": ted} for k, v in ZDROJE.items()}
    _write_atomic(base / "puvod.json", json.dumps(puvod, ensure_ascii=False, indent=1).encode("utf-8"))
    _zapis_readme()
    stav = {"zaznamu": len(index), "s_promptem": sum(1 for z in index if z["prompt"]),
            "s_nahledem": sum(1 for z in index if z["nahled"]), "novych_nahledu": nove, "chyb_nahledu": chyby}
    log(f"index: {stav}")
    return stav


def _zapis_readme() -> None:
    text = f"""# NGM-SKLAD

Surový sklad pro POHYB, KLAPKA a GRAFIK. Spravuje ho `ngm_shared.sklad` (repo GRAFIK, `shared/`).
Ručně tu nic neupravuj, další stažení soubory přepíše. Kořen mění proměnná `NGM_SKLAD`.

## namety/

Náměty videí, která lidé nechali napsat Claude jako kód. Slouží jako inspirace pro režii, ne jako obsah.

| Složka | Zdroj | Licence |
|---|---|---|
| `opus55-videos/` | {ZDROJE['opus55-videos']['repo']} | {ZDROJE['opus55-videos']['licence']} |
| `claude55-videos/` | {ZDROJE['claude55-videos']['repo']} | {ZDROJE['claude55-videos']['licence']} |

`index.json` spojuje obě sbírky, jeden záznam na příspěvek na X (`id`). Náhledy jsou jen lokální reference
a do výstupu projektů nesmí. Videa se nestahují, `post_url` vede na originál.

Hledání: `python -m ngm_shared.sklad hledej <slova> [--kategorie vysvetleni]`.
Aktualizace: `python -m ngm_shared.sklad stahni namety`.
"""
    _write_atomic(root() / "README.md", text.encode("utf-8"))


def nacti_index() -> list[dict]:
    path = namety_dir() / "index.json"
    if not path.exists():
        raise SkladError(f"{path} neexistuje, nejdřív `python -m ngm_shared.sklad stahni namety`")
    return json.loads(path.read_text(encoding="utf-8"))


def hledej(dotaz: str = "", kategorie: str | None = None, technika: str | None = None,
           limit: int = 20, jen_s_promptem: bool = False, index: list[dict] | None = None) -> list[dict]:
    """Slova dotazu bez ohledu na diakritiku a velikost písmen; řadí podle počtu shodných slov, pak podle data.

    Prompty jsou většinou anglicky, české slovo najde jen český nebo čínský prompt; volající (režisér) má
    téma předat i anglicky."""
    if kategorie and kategorie not in KATEGORIE:
        raise SkladError(f"neznámá kategorie {kategorie!r}, povolené: {', '.join(KATEGORIE)}")
    slova = [s for s in re.split(r"\W+", _bez_diakritiky(dotaz)) if s]
    vysledek = []
    for z in index if index is not None else nacti_index():
        if kategorie and z["kategorie"] != kategorie:
            continue
        if technika and technika not in z["techniky"]:
            continue
        if jen_s_promptem and not z["prompt"]:
            continue
        text = _bez_diakritiky(" ".join([z["prompt"], z["nazev"], z["autor"], " ".join(z["techniky"])]))
        slova_textu = _SLOVO.findall(text)
        skore = sum(1 for s in slova
                    if (any(w.startswith(s) for w in slova_textu) if s.isascii() else s in text))
        if slova and not skore:
            continue
        vysledek.append((skore, z))
    vysledek.sort(key=lambda p: (p[0], p[1]["pridano"]), reverse=True)
    return [z for _, z in vysledek[:limit]]


def cesta(zaznam: dict) -> Path | None:
    """Absolutní cesta k náhledu záznamu, nebo None, když náhled není."""
    return root() / zaznam["nahled"] if zaznam.get("nahled") else None


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="python -m ngm_shared.sklad")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stahni")
    s.add_argument("co", choices=["namety"])
    s.add_argument("--bez-nahledu", action="store_true")
    h = sub.add_parser("hledej")
    h.add_argument("slova", nargs="*")
    h.add_argument("--kategorie", choices=list(KATEGORIE))
    h.add_argument("--technika")
    h.add_argument("--limit", type=int, default=10)
    sub.add_parser("stav")
    a = p.parse_args(argv)
    try:
        if a.cmd == "stahni":
            stahni_namety(nahledy=not a.bez_nahledu)
        elif a.cmd == "hledej":
            for z in hledej(" ".join(a.slova), kategorie=a.kategorie, technika=a.technika, limit=a.limit):
                print(f"{z['id']}  {KATEGORIE[z['kategorie']]:<20} @{z['autor']}  {z['post_url']}")
                print(f"    {' '.join((z['prompt'] or z['nazev']).split())[:160]}")
        else:
            index = nacti_index()
            print(f"kořen {root()}: {len(index)} námětů, {sum(1 for z in index if z['prompt'])} s promptem, "
                  f"{sum(1 for z in index if z['nahled'])} s náhledem")
            for k, n in Counter(z["kategorie"] for z in index).most_common():
                print(f"  {KATEGORIE[k]}: {n}")
    except SkladError as e:
        print(f"chyba: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
