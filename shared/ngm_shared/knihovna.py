"""Sdílená knihovna postav, míst, rekvizit a stylů (dělba práce, fáze 4; GRAFIK/docs/DECISIONS.md 2026-10-29).

Jedna složka, kterou čte a zapisuje KLAPKA i GRAFIK. Neběží žádný proces, projekty volají tyto funkce.

    KNIHOVNA/                          NGM_KNIHOVNA, výchozí C:/Users/stock/Documents/000_NGM/KNIHOVNA
      characters/<slug>/card.yaml      postava + refs/ (předlohy), stylized/, figura/, sources/, voice/
      environments/<slug>/card.yaml    místo + refs/
      props/<slug>.yaml                rekvizita + props/<slug>/ (model/ …)
      styles/<slug>.yaml               společná karta stylu (níže)
      styles/<slug>.png                náhled stylu z KLAPKY
      styles/<slug>/samples/<n>.jpg    vzorky stylu z GRAFIKU; styles/<slug>/STYLE.md = karta pro lidi
      .locks/                          zámky karet (soubory zůstávají)
      .trash/                          smazané položky (nic se nemaže natrvalo)

Rozložení je převzaté z KLAPKY (`studio/library/`) a slug (název složky nebo souboru) je identita:
scény, projekty i objednávky NG-ROBOT se odkazují slugem. Předloha může mít vedle sebe
`<soubor>.puvod.json` s původem a licencí (pole ze schránky předloh GRAFIKU, `engine/reflib.py`).

Zapisuje se jen přes `write()` / `update()` / `add_ref()` / `trash()`: drží zámek na kartu pro vlákna
i procesy (KLAPKA a GRAFIK Studio mohou upravovat souběžně) a soubor mění atomicky (dočasný soubor
a `os.replace`). Zámek je re-entrantní ve vlákně, jako `card_lock` v KLAPCE (uložení může běžet uvnitř
jiného).

Společná karta stylu (`styles/<slug>.yaml`):

    name: Akvarel přírodovědný
    note: k čemu se hodí
    look: společný popis vzhledu pro obraz i film
    obraz: {medium, light, line, composition, palette: [{hex, name}], signature}    # z GRAFIKU
    film: {lens, grade}                                                              # z KLAPKY
    avoid: čemu se vyhnout (GRAFIK `avoid` = KLAPKA `negative`)
    constraints: věta o stabilitě záběru (jen video; chybí-li, platí výchozí věta KLAPKY)
    origin, puvod, created, updated

`image_text()` složí slova za „Style:“ v promptu obrázku (jako GRAFIK), `video_lines()` řádky stylu
v promptu videa (jako KLAPKA `engine.build_shot`), `film_fields()` pole třídy `Style` v KLAPCE.
Každý projekt bere svůj oddíl; styl, který ho nemá, se doplní z druhého, takže styl z GRAFIKU
jde i do klipu a naopak.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable

import yaml

DEFAULT_ROOT = Path("C:/Users/stock/Documents/000_NGM/KNIHOVNA")
KINDS = ("character", "environment", "prop", "style")
# KLAPKA povoluje písmena, číslice, - a _ (server._slug); tečka ani lomítko nikdy.
SLUG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,99}")
OBRAZ = ("medium", "light", "line", "composition", "palette", "signature")
FILM = ("lens", "grade", "ref_style")
STYLE_KEYS = ("name", "note", "look", "obraz", "film", "avoid", "constraints",
              "origin", "puvod", "created", "updated")
# Výchozí `constraints` třídy Style v KLAPCE (klapka/engine.py): platí pro kartu, která pole nemá.
FILM_CONSTRAINTS = ("sharp clarity, stable picture, no flicker, "
                    "consistent faces and wardrobe across the shot")
PUVOD_FIELDS = ("origin", "title", "source_url", "page_url", "author", "license", "license_url",
                "sha256", "width", "height", "added")
PUVOD_SUFFIX = ".puvod.json"
LOCK_WAIT_S = 30.0


class KnihovnaError(ValueError):
    pass


class KnihovnaBusy(TimeoutError):
    pass


def root() -> Path:
    raw = os.environ.get("NGM_KNIHOVNA")
    return Path(raw) if raw else DEFAULT_ROOT


def _base(base) -> Path:
    return Path(base) if base is not None else root()


def _check(kind: str, slug: str) -> None:
    if kind not in KINDS:
        raise KnihovnaError(f"neznámý druh {kind!r}; povolené: {', '.join(KINDS)}")
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise KnihovnaError(f"neplatný slug {slug!r} (povoleno a-z, A-Z, 0-9, - a _)")


def card_path(kind: str, slug: str, base=None) -> Path:
    _check(kind, slug)
    if kind in ("character", "environment"):
        return _base(base) / f"{kind}s" / slug / "card.yaml"
    return _base(base) / f"{kind}s" / f"{slug}.yaml"


def item_dir(kind: str, slug: str, base=None) -> Path:
    """Složka položky: předlohy, figura, 3D model, vzorky stylu."""
    _check(kind, slug)
    return _base(base) / f"{kind}s" / slug


def slugs(kind: str, base=None) -> list[str]:
    """Slugy v pořadí souborů karet, jak je čte KLAPKA (`styles/a-b.yaml` před `styles/a.yaml`):
    na pořadí v KLAPCE záleží, např. který ze stylů se stejným vzhledem pojmenuje stylizovaný board."""
    if kind not in KINDS:
        raise KnihovnaError(f"neznámý druh {kind!r}; povolené: {', '.join(KINDS)}")
    folder = _base(base) / f"{kind}s"
    if not folder.is_dir():
        return []
    if kind in ("character", "environment"):
        found = [p.parent.name for p in sorted(folder.glob("*/card.yaml"))]
    else:
        found = [p.stem for p in sorted(folder.glob("*.yaml"))]
    return [s for s in found if SLUG.fullmatch(s)]


def _retry(fn, *args):
    """Windows na okamžik odmítne nahradit nebo číst soubor, který má otevřený jiný proces (antivir)."""
    for _ in range(50):
        try:
            return fn(*args)
        except PermissionError:
            time.sleep(0.02)
    return fn(*args)


def read(kind: str, slug: str, base=None) -> dict | None:
    """Karta jako slovník, `None` když v knihovně není."""
    path = card_path(kind, slug, base)
    try:
        text = _retry(path.read_text, "utf-8")
    except FileNotFoundError:
        return None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise KnihovnaError(f"karta {path} není platný YAML: {e}") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise KnihovnaError(f"karta {path} neobsahuje slovník polí")
    return data


def cards(kind: str, base=None) -> dict[str, dict]:
    """Všechny karty druhu podle slugu (seřazené)."""
    out = {}
    for slug in slugs(kind, base):
        card = read(kind, slug, base)
        if card is not None:            # mezitím smazaná
            out[slug] = card
    return out


def dump(data: dict) -> str:
    """Text karty; stejný zápis jako KLAPKA (`yaml.safe_dump`, diakritika, pořadí polí)."""
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}-{threading.get_ident()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        _retry(os.replace, tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def copy_file(src: Path, dst: Path) -> None:
    """Kopie souboru i s časem změny; cíl se objeví celý, nebo vůbec."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.{os.getpid()}-{threading.get_ident()}.tmp")
    try:
        shutil.copy2(src, tmp)
        _retry(os.replace, tmp, dst)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write(kind: str, slug: str, data: dict, base=None) -> Path:
    """Zapíše celou kartu (atomicky, pod zámkem karty). Styl dostane pořadí polí společné karty
    a vedle sebe přepsaný `STYLE.md`."""
    if not isinstance(data, dict):
        raise KnihovnaError("karta musí být slovník polí")
    path = card_path(kind, slug, base)
    if kind == "style":
        data = _style_ordered(data)
    with lock(kind, slug, base):
        _write_atomic(path, dump(data))
        if kind == "style":
            _write_atomic(item_dir(kind, slug, base) / "STYLE.md", style_md(slug, data))
    return path


def update(kind: str, slug: str, changes: dict | Callable[[dict], dict], base=None) -> dict:
    """Čtení, úprava a zápis jedné karty pod jedním zámkem. `changes` je slovník polí (sloučí se
    do karty) nebo funkce, která dostane kopii karty (`{}`, když ještě není) a vrátí novou."""
    with lock(kind, slug, base):
        card = read(kind, slug, base) or {}
        new = changes(dict(card)) if callable(changes) else {**card, **changes}
        write(kind, slug, new, base)
        return new


# ── zámek karty: vlákna v procesu + ostatní procesy ────────────────────────────

_guard = threading.Lock()
_rlocks: dict[str, threading.RLock] = {}
_held: dict[str, list] = {}     # klíč -> [hloubka, otevřený soubor zámku]; mění ho jen vlákno s RLock


if os.name == "nt":
    import msvcrt

    def _lock_byte(f) -> None:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock_byte(f) -> None:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock_byte(f) -> None:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock_byte(f) -> None:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _os_lock(path: Path, wait_s: float, what: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+b")
    deadline = time.monotonic() + wait_s
    while True:
        try:
            _lock_byte(f)
            return f
        except OSError:
            if time.monotonic() > deadline:
                f.close()
                raise KnihovnaBusy(f"karta {what} je zamčená jiným procesem déle než {wait_s:g} s") from None
            time.sleep(0.01)


@contextmanager
def lock(kind: str, slug: str, base=None, wait_s: float = LOCK_WAIT_S):
    """Zámek jedné karty. Drží ho každé čtení-úprava-zápis; re-entrantní v rámci vlákna."""
    _check(kind, slug)
    path = _base(base) / ".locks" / f"{kind}-{slug}.lock"
    key = os.path.normcase(os.path.abspath(path))
    with _guard:
        rlock = _rlocks.setdefault(key, threading.RLock())
    if not rlock.acquire(timeout=wait_s):
        raise KnihovnaBusy(f"karta {kind} {slug} je zamčená jiným vláknem déle než {wait_s:g} s")
    try:
        held = _held.get(key)
        if held is None:
            held = _held[key] = [0, _os_lock(path, wait_s, f"{kind} {slug}")]
        held[0] += 1
        try:
            yield
        finally:
            held[0] -= 1
            if held[0] == 0:
                del _held[key]
                try:
                    _unlock_byte(held[1])
                finally:
                    held[1].close()
    finally:
        rlock.release()


# ── předlohy a jejich původ ───────────────────────────────────────────────────

def puvod_path(ref: Path) -> Path:
    return Path(ref).with_name(Path(ref).name + PUVOD_SUFFIX)


def read_puvod(ref: Path) -> dict | None:
    """Původ a licence předlohy, `None` když soubor vedle ní není."""
    try:
        return json.loads(puvod_path(ref).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def write_puvod(ref: Path, puvod: dict) -> Path:
    """Zapíše `<předloha>.puvod.json` s poli schránky předloh GRAFIKU; `sha256` je vždy ze souboru."""
    data = {k: puvod[k] for k in PUVOD_FIELDS if puvod.get(k) is not None}
    data["sha256"] = hashlib.sha256(Path(ref).read_bytes()).hexdigest()
    data.setdefault("added", datetime.now().isoformat(timespec="seconds"))
    path = puvod_path(ref)
    _write_atomic(path, json.dumps({k: data[k] for k in PUVOD_FIELDS if k in data},
                                   ensure_ascii=False, indent=2))
    return path


def _same_bytes(a: Path, b: Path) -> bool:
    return a.stat().st_size == b.stat().st_size and a.read_bytes() == b.read_bytes()


def add_ref(kind: str, slug: str, src, name: str | None = None, puvod: dict | None = None,
            base=None) -> Path:
    """Zkopíruje obrázek do `refs/` položky a volitelně k němu zapíše původ a licenci.

    Jiný soubor stejného jména se nepřepíše (nový dostane `-2`, `-3` …); stejný soubor podruhé
    nepřibude, vrátí se cesta k už uloženému. Karta se nemění: kterou předlohu bere jako hlavní,
    určuje projekt (KLAPKA `primary`)."""
    if kind == "style":
        raise KnihovnaError("styl nemá předlohy, jen vzorky (styles/<slug>/samples/)")
    src = Path(src)
    name = Path(name or src.name).name
    if not name or name.startswith(".") or name.endswith(PUVOD_SUFFIX):
        raise KnihovnaError(f"neplatný název předlohy {name!r}")
    with lock(kind, slug, base):
        if read(kind, slug, base) is None:
            raise KnihovnaError(f"{kind} {slug} v knihovně není")
        refs = item_dir(kind, slug, base) / "refs"
        stem, suffix = Path(name).stem, Path(name).suffix
        dst, n = refs / name, 1
        while dst.exists() and not _same_bytes(src, dst):
            n += 1
            dst = refs / f"{stem}-{n}{suffix}"
        if not dst.exists():
            copy_file(src, dst)
        if puvod:
            write_puvod(dst, puvod)
        return dst


def trash(kind: str, slug: str, base=None) -> Path:
    """Přesune kartu i složku položky (u stylu i náhled) do `.trash/<druh>s/<čas>-<slug>/`. Nic nemaže."""
    with lock(kind, slug, base):
        card, folder = card_path(kind, slug, base), item_dir(kind, slug, base)
        movers = [folder] if kind in ("character", "environment") else [card, folder]
        if kind == "style":
            movers.append(card.with_suffix(".png"))
        movers = [p for p in movers if p.exists()]
        if not movers:
            raise KnihovnaError(f"{kind} {slug} v knihovně není")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest, n = _base(base) / ".trash" / f"{kind}s" / f"{stamp}-{slug}", 1
        while dest.exists():
            n += 1
            dest = _base(base) / ".trash" / f"{kind}s" / f"{stamp}-{slug}-{n}"
        dest.mkdir(parents=True)
        for p in movers:
            _retry(shutil.move, str(p), str(dest / p.name))
        return dest


# ── společná karta stylu ──────────────────────────────────────────────────────

def _section(card: dict, name: str) -> dict:
    part = card.get(name)
    return part if isinstance(part, dict) else {}


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _avoid(card: dict):
    return card.get("avoid", card.get("negative"))


def _film(card: dict) -> dict:
    """Oddíl film; karta ve starém tvaru KLAPKY (lens, grade nahoře) se čte stejně."""
    return {**{k: card[k] for k in FILM if k in card}, **_section(card, "film")}


def _style_ordered(card: dict) -> dict:
    out = {k: card[k] for k in STYLE_KEYS if k in card}
    for name, keys in (("obraz", OBRAZ), ("film", FILM)):
        if isinstance(out.get(name), dict):
            part = out[name]
            out[name] = {**{k: part[k] for k in keys if k in part},
                         **{k: v for k, v in part.items() if k not in keys}}
    return {**out, **{k: v for k, v in card.items() if k not in out}}


def from_grafik(data: dict) -> dict:
    """Karta stylu GRAFIK (`styles/<slug>/style.json`) jako společná karta."""
    card = {"name": data.get("label") or data.get("slug")}
    if data.get("note"):
        card["note"] = data["note"]
    obraz = {k: data[k] for k in OBRAZ if data.get(k)}
    if obraz:
        card["obraz"] = obraz
    for key in ("avoid", "origin", "puvod", "created", "updated"):
        if data.get(key):
            card[key] = data[key]
    return _style_ordered(card)


def from_klapka(data: dict, puvod: str = "") -> dict:
    """Karta stylu KLAPKA (`studio/library/styles/<slug>.yaml`) jako společná karta.

    Hodnoty se přenášejí, jak jsou (i prázdné), aby `film_fields()` vrátilo přesně pole,
    ze kterých KLAPKA dnes staví `Style`. Pole, která KLAPKA nezná, zůstanou na kartě."""
    film_keys = ("lens", "grade", "ref_style")
    card = {k: data[k] for k in ("name", "look", "constraints") if k in data}
    film = {k: data[k] for k in film_keys if k in data}
    if film:
        card["film"] = film
    if "negative" in data:
        card["avoid"] = data["negative"]
    card.update({k: v for k, v in data.items()
                 if k not in ("name", "look", "constraints", "negative", *film_keys)})
    if puvod:
        card.setdefault("puvod", puvod)
    return _style_ordered(card)


def image_text(card: dict) -> str:
    """Slova za „Style:“ v promptu obrázku (GRAFIK `engine/styles.py`): společný popis, oddíl obraz
    (bez něj objektiv a barevné podání z oddílu film), paleta, čemu se vyhnout."""
    obraz = _section(card, "obraz")
    picture = [obraz.get(k) for k in ("medium", "light", "line", "composition")]
    if not any(_text(p).strip() for p in picture):
        film = _film(card)
        picture = [film.get("lens"), film.get("grade")]
    parts = [_text(p).strip().rstrip(".") for p in (card.get("look"), *picture)]
    parts = [p for p in parts if p]
    palette = [c for c in obraz.get("palette") or [] if isinstance(c, dict) and c.get("hex")]
    if palette:
        parts.append("colour palette: " + ", ".join(
            " ".join(x for x in (c.get("name"), c["hex"]) if x) for c in palette))
    avoid = _text(_avoid(card)).strip()
    if avoid:
        parts.append("avoid " + avoid.rstrip("."))
    return ". ".join(p[0].upper() + p[1:] for p in parts)


def film_fields(card: dict) -> dict:
    """Pole stylu ve tvaru třídy `Style` v KLAPCE (name, look, lens, grade, negative, constraints,
    ref_style), jen ta, která karta má: chybějící dostanou výchozí hodnotu KLAPKY. Styl bez popisu
    filmu (z GRAFIKU) dostane `look` z média, světla a linky. Kartu ve starém tvaru KLAPKY čte stejně."""
    film = _film(card)
    out = {k: card[k] for k in ("name", "look", "constraints") if k in card}
    out.update({k: film[k] for k in FILM if k in film})
    if "avoid" in card or "negative" in card:
        out["negative"] = _avoid(card)
    if not any(out.get(k) for k in ("look", "lens", "grade")):
        obraz = _section(card, "obraz")
        drawn = [_text(obraz.get(k)).strip().rstrip(".") for k in ("medium", "light", "line")]
        if any(drawn):
            out["look"] = ", ".join(p for p in drawn if p)
    return out


def video_lines(card: dict) -> list[str]:
    """Řádky stylu v promptu videa, jak je skládá KLAPKA `engine.build_shot` u záběru projektu:
    „Style: look, lens, grade.“, věta constraints, „Avoid: ….“ (KLAPKA mezi poslední dva vkládá
    případně větu o hudbě)."""
    f = film_fields(card)
    look = ", ".join(p for p in (f.get("look"), f.get("lens"), f.get("grade")) if p)
    constraints = f.get("constraints", FILM_CONSTRAINTS)
    lines = []
    if look:
        lines.append(f"Style: {look}.")
    if constraints:
        lines.append(constraints + ".")
    if f.get("negative"):
        lines.append(f"Avoid: {f['negative']}.")
    return lines


def video_text(card: dict) -> str:
    return "\n".join(video_lines(card))


_MD_OBRAZ = (("medium", "Médium a technika"), ("light", "Světlo"), ("line", "Linka a povrch"),
             ("composition", "Kompozice"), ("signature", "Podpisové znaky"))


def style_md(slug: str, card: dict) -> str:
    """Karta stylu pro lidi; přepisuje se při každém uložení karty."""
    obraz, film = _section(card, "obraz"), _film(card)
    lines = [f"# {card.get('name') or slug}", "",
             f"Společná karta stylu ve sdílené knihovně, strojová část je `styles/{slug}.yaml`. Tento soubor "
             "se přepisuje při každém uložení; upravujte kartu v GRAFIK Studiu, v KLAPCE nebo v YAML.", ""]
    if card.get("note"):
        lines += ["## Podstata", "", str(card["note"]), ""]
    if card.get("look"):
        lines += ["## Společný popis", "", str(card["look"]), ""]
    for key, label in _MD_OBRAZ:
        if obraz.get(key):
            lines += [f"## {label}", "", str(obraz[key]), ""]
    if obraz.get("palette"):
        lines += ["## Barvy", ""] + [f"- `{c.get('hex')}` {c.get('name', '')}"
                                    for c in obraz["palette"] if isinstance(c, dict)] + [""]
    for key, label in (("lens", "Film: objektiv a kamera"), ("grade", "Film: barevné podání")):
        if film.get(key):
            lines += [f"## {label}", "", str(film[key]), ""]
    if _avoid(card):
        lines += ["## Vyhnout se", "", str(_avoid(card)), ""]
    lines += ["## Do promptu obrázku (slovy, nikdy jako obrázek)", "", f"Style: {image_text(card)}.", "",
              "## Do promptu videa", "", *video_lines(card), ""]
    if card.get("puvod"):
        lines += ["## Původ", "", str(card["puvod"]), ""]
    return "\n".join(lines)
