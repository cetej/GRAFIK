"""Převod do sdílené knihovny (fáze 4): KLAPKA `studio/library/` a GRAFIK `styles/` → KNIHOVNA.

Jen kopíruje, zdroje zůstanou beze změny (záloha, dokud se převod neověří). Z KLAPKY jde každý soubor
na stejné místo (postavy, místa, rekvizity, náhledy i `.bak`), jen karty stylů se převedou na společnou
kartu (`ngm_shared.knihovna`). Z GRAFIKU jde `style.json` jako společná karta a vzorky do
`styles/<slug>/samples/`; `STYLE.md` se napíše znovu, koš `.trash/` se nepřevádí.

Opakované spuštění nic nezmění: soubor nebo karta se stejným obsahem se přeskočí. Když by se cíl lišil
nebo dva zdroje mířily na stejné místo (kolize slugů), skončí bez jediného zápisu a kolize vypíše.

    python -m ngm_shared.knihovna_prevod --dry-run
    python -m ngm_shared.knihovna_prevod [--klapka DIR] [--grafik DIR] [--cil DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml

from ngm_shared import knihovna

KLAPKA_LIBRARY = Path("C:/Users/stock/Documents/000_NGM/KLAPKA/studio/library")
GRAFIK_STYLES = Path("C:/Users/stock/Documents/000_NGM/GRAFIK/styles")
KIND_OF_FOLDER = {"characters": "character", "environments": "environment", "props": "prop", "styles": "style"}
LABELS = {"character": "postavy", "environment": "místa", "prop": "rekvizity", "style": "styly", None: "ostatní"}


@dataclass
class Step:
    dst: Path                   # relativně ke knihovně
    src: Path                   # odkud
    card: dict | None = None    # převedená karta stylu; None = kopie souboru beze změny
    kind: str | None = None
    slug: str = ""
    origin: str = ""            # KLAPKA | GRAFIK


def _item(rel: Path) -> tuple[str | None, str]:
    """(druh, slug) souboru knihovny podle cesty: characters/<slug>/…, props/<slug>.yaml, styles/<slug>.png …"""
    kind = KIND_OF_FOLDER.get(rel.parts[0]) if len(rel.parts) > 1 else None
    if kind is None:
        return None, ""
    if len(rel.parts) > 2:
        return kind, rel.parts[1]
    return kind, rel.name.split(".")[0]


def plan_klapka(src: Path) -> list[Step]:
    steps = []
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = path.relative_to(src)
        kind, slug = _item(rel)
        card = None
        if kind == "style" and len(rel.parts) == 2 and rel.suffix == ".yaml":
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            card = knihovna.from_klapka(data, puvod=f"převedeno z KLAPKA studio/library/styles/{rel.name}")
        steps.append(Step(rel, path, card, kind, slug, "KLAPKA"))
    return steps


def plan_grafik(src: Path) -> tuple[list[Step], list[str]]:
    steps, skipped = [], []
    for folder in sorted(p for p in src.iterdir() if p.is_dir()):
        if not (folder / "style.json").exists():
            skipped.append(f"GRAFIK {folder.name}/: {'koš smazaných stylů' if folder.name == '.trash' else 'není karta stylu'}")
            continue
        slug = folder.name
        data = json.loads((folder / "style.json").read_text(encoding="utf-8"))
        steps.append(Step(Path("styles") / f"{slug}.yaml", folder / "style.json",
                          knihovna.from_grafik(data), "style", slug, "GRAFIK"))
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            rel = path.relative_to(folder)
            if rel.as_posix() in ("style.json", "STYLE.md"):
                continue                     # karta je převedená, STYLE.md napíše knihovna znovu
            steps.append(Step(Path("styles") / slug / rel, path, None, "style", slug, "GRAFIK"))
    return steps, skipped


def _same(step: Step, target: Path) -> bool:
    dst = target / step.dst
    if step.card is not None:
        return dst.read_text(encoding="utf-8") == knihovna.dump(step.card)
    return knihovna._same_bytes(step.src, dst)


def check(steps: list[Step], target: Path) -> tuple[list[str], list[Step], list[Step]]:
    """(kolize, co zapsat, co už v knihovně je stejně)."""
    collisions, todo, done = [], [], []
    seen: dict[str, Step] = {}
    for step in steps:
        key = os.path.normcase(step.dst.as_posix())
        if key in seen:
            first = seen[key]
            collisions.append(f"{step.dst.as_posix()}: {first.origin} {first.src} i {step.origin} {step.src}")
            continue
        seen[key] = step
        if not (target / step.dst).exists():
            todo.append(step)
        elif _same(step, target):
            done.append(step)
        else:
            collisions.append(f"{step.dst.as_posix()}: v knihovně už je jiný obsah (zdroj {step.origin} {step.src})")
    return collisions, todo, done


def _items(steps: list[Step]) -> dict[str | None, set]:
    """Slugy podle druhu: položka je to, co má kartu (props/<slug>.yaml, characters/<slug>/card.yaml)."""
    out: dict[str | None, set] = {}
    for s in steps:
        card = (len(s.dst.parts) == 2 and s.dst.suffix == ".yaml") or \
               (len(s.dst.parts) == 3 and s.dst.name == "card.yaml")
        if s.kind and card:
            out.setdefault(s.kind, set()).add(s.slug)
    return out


def run(klapka: Path | None = KLAPKA_LIBRARY, grafik: Path | None = GRAFIK_STYLES, target: Path | None = None,
        dry_run: bool = False) -> dict:
    """Naplánuje, zkontroluje a (bez `dry_run` a bez kolizí) zkopíruje. Vrací přehled pro výpis."""
    target = Path(target) if target is not None else knihovna.root()
    steps, skipped = [], []
    if klapka is not None:
        steps += plan_klapka(Path(klapka))
    if grafik is not None:
        g, skipped = plan_grafik(Path(grafik))
        steps += g
    collisions, todo, done = check(steps, target)
    report = {"target": str(target), "dry_run": dry_run, "collisions": collisions, "skipped": skipped,
              "files": len(steps), "to_write": len(todo), "already": len(done),
              "items": {LABELS[k]: sorted(v) for k, v in _items(steps).items()},
              "by_origin": dict(Counter(f"{LABELS[s.kind]} {s.origin}" for s in steps
                                        if s.kind == "style" and s.card is not None)),
              "written": 0}
    if collisions or dry_run:
        return report
    for step in todo:
        if step.card is not None:
            knihovna.write("style", step.slug, step.card, base=target)
        else:
            knihovna.copy_file(step.src, target / step.dst)
        report["written"] += 1
    report["in_library"] = {LABELS[k]: len(knihovna.slugs(k, base=target)) for k in knihovna.KINDS}
    return report


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Převod KLAPKA studio/library a GRAFIK styles do sdílené knihovny "
                                             "(jen kopíruje, opakovatelné).")
    ap.add_argument("--klapka", type=Path, default=KLAPKA_LIBRARY)
    ap.add_argument("--grafik", type=Path, default=GRAFIK_STYLES)
    ap.add_argument("--cil", type=Path, default=None, help="knihovna (výchozí NGM_KNIHOVNA nebo KNIHOVNA)")
    ap.add_argument("--dry-run", action="store_true", help="jen vypsat, nic nezapsat")
    a = ap.parse_args(argv)
    for src in (a.klapka, a.grafik):
        if not src.is_dir():
            print(f"zdroj {src} neexistuje")
            return 2
    r = run(a.klapka, a.grafik, a.cil, a.dry_run)
    print(f"knihovna: {r['target']}{'  (jen nanečisto, nic se nezapíše)' if r['dry_run'] else ''}")
    for label, slugs in r["items"].items():
        print(f"  {label}: {len(slugs)}  ({', '.join(slugs)})")
    print(f"  styly podle zdroje: {r['by_origin']}")
    print(f"  souborů ve zdrojích: {r['files']}, k zápisu {r['to_write']}, už v knihovně stejně {r['already']}")
    for line in r["skipped"]:
        print(f"  vynecháno: {line}")
    if r["collisions"]:
        print(f"KOLIZE ({len(r['collisions'])}), nic se nezapsalo:")
        for line in r["collisions"]:
            print(f"  {line}")
        return 1
    if not r["dry_run"]:
        print(f"zapsáno {r['written']}; v knihovně teď: {r['in_library']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
