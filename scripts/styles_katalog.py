#!/usr/bin/env python3
"""Catalogue of styles by category (styles/katalog.yaml) -> the shared library KNIHOVNA.

  python scripts/styles_katalog.py karty [--dry-run]        new cards; existing ones get only kategorie, poradi, note
  python scripts/styles_katalog.py ukazky [--kolo 1 ...]    samples through the running Engine (local FLUX, 0 USD)
  python scripts/styles_katalog.py nahled <kategorie> <png> contact sheet of the category's samples

Samples go one at a time, so jobs of other projects get their turn in the Engine queue between them.
Done samples are remembered in `--stav`, a repeated run continues where it stopped.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import yaml
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "shared"))

from ngm_shared import knihovna  # noqa: E402

KATALOG = ROOT / "styles" / "katalog.yaml"
ENGINE = "http://127.0.0.1:8300"
SIZE = "1024x768"
SEED = 42
# The same subjects across styles, so the styles can be compared; horse and farmer fit every era.
SPOLECNE = {
    "SPOLECNY": "An old farmer leading a horse along a dirt path past a large oak tree",
    "PORTRET": "Head and shoulders portrait of an elderly fisherman with a grey beard and a weathered face",
}
# Samples of the cards that were already in the library (typical subject of the style in `ukazky` of the new ones).
EXISTUJICI_UKAZKY = {
    "kresba-tuzkou": ["SPOLECNY", "PORTRET"], "akvarel-prirodovedny": ["SPOLECNY", "A kingfisher perched on a reed"],
    "ng-infografika-3d": ["SPOLECNY", "A cutaway of a steam engine showing its inner parts"],
    "karikatura-3d": ["SPOLECNY", "PORTRET"], "animovany-film-3d": ["SPOLECNY", "PORTRET"],
    "graficky-roman": ["SPOLECNY", "PORTRET"], "default": ["SPOLECNY", "PORTRET"],
    "dokumentarni-rekonstrukce": ["SPOLECNY", "PORTRET"], "dokumentarni-rekonstrukce-era": ["SPOLECNY", "PORTRET"],
    "anticke-drama": ["SPOLECNY", "PORTRET"], "malovany-epos": ["SPOLECNY", "PORTRET"],
    "olejomalba": ["SPOLECNY", "PORTRET"], "loutkovy-film": ["SPOLECNY", "PORTRET"],
    "kreslena-animace-2d": ["SPOLECNY", "PORTRET"],
}
OBRAZ_POLE = ("medium", "light", "line", "composition", "signature")


def nacti(path: Path = KATALOG) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def karta(polozka: dict) -> dict:
    """A catalogue entry as the shared card. Film styles keep KLAPKA's shape (look + film)."""
    card = {k: polozka[k] for k in ("name", "kategorie", "poradi", "note", "look", "avoid") if polozka.get(k)}
    film = {k: polozka[k] for k in ("lens", "grade") if polozka.get(k)}
    if film:
        card["film"] = film
    obraz = {k: polozka[k] for k in OBRAZ_POLE if polozka.get(k)}
    if polozka.get("palette"):
        obraz["palette"] = [dict(zip(("hex", "name"), c.split(" ", 1))) for c in polozka["palette"]]
    if obraz:
        card["obraz"] = obraz
    now = datetime.now().isoformat(timespec="seconds")
    return {**card, "origin": "manual", "puvod": "katalog stylů GRAFIK (styles/katalog.yaml), napsáno ručně 2026-10-31",
            "created": now, "updated": now}


def karty(data: dict, base: Path, dry_run: bool, prepis: tuple[str, ...] = ()) -> None:
    """`prepis`: new cards whose text was tuned after looking at samples; only these are rewritten."""
    for p in data["nove"]:
        if knihovna.read("style", p["slug"], base) is not None and p["slug"] not in prepis:
            print(f"beze změny   {p['slug']}")
        else:
            print(f"nová karta   {p['slug']}")
            if not dry_run:
                knihovna.write("style", p["slug"], karta(p), base)
    for p in data["existujici"]:
        with knihovna.lock("style", p["slug"], base):
            card = knihovna.read("style", p["slug"], base)
            if card is None:
                print(f"NENÍ V KNIHOVNĚ {p['slug']}")
                continue
            add = {k: p[k] for k in ("kategorie", "poradi") if card.get(k) != p[k]}
            if p.get("note") and not card.get("note"):
                add["note"] = p["note"]
            print(f"doplnit {sorted(add) or '-'}   {p['slug']}")
            if add and not dry_run:
                knihovna.write("style", p["slug"], {**card, **add}, base)


def api(path: str, body: dict | None = None, timeout: int = 60) -> dict:
    req = urllib.request.Request(ENGINE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def ukazky_plan(data: dict) -> dict[str, list[str]]:
    """slug -> sample subjects, in the order of categories and of the time line inside them."""
    plan = {p["slug"]: p["ukazky"] for p in data["nove"]}
    plan |= {s: u for s, u in EXISTUJICI_UKAZKY.items()}
    poradi = {p["slug"]: (list(knihovna.STYLE_CATEGORIES).index(p["kategorie"]), p["poradi"])
              for p in [*data["nove"], *data["existujici"]]}
    return dict(sorted(plan.items(), key=lambda kv: poradi[kv[0]]))


def vyrob(slug: str, zadani: str, seed: int, cekat_s: int = 3600) -> str:
    """One image with the style, saved as the card's sample; returns the sample's name."""
    job = api("/api/v2/images", {"prompt": SPOLECNE.get(zadani, zadani), "style_id": slug, "style": slug,
                                 "size": SIZE, "n": 1, "seed": seed, "caller": f"styl:{slug}"})["job_id"]
    konec = time.time() + cekat_s
    while time.time() < konec:
        time.sleep(4)
        try:
            j = api(f"/api/v2/jobs/{job}")
        except (urllib.error.URLError, TimeoutError):
            continue  # Engine busy or restarting; the job waits in its store
        if j["status"] == "done":
            pred = set(api(f"/api/v2/styles/{slug}")["samples"])
            po = api(f"/api/v2/styles/{slug}/samples", {"job": f"{job}/0"})["samples"]
            return next(iter(set(po) - pred))
        if j["status"] in ("failed", "cancelled"):
            raise RuntimeError(f"{slug}: {j['status']} {j.get('error')}")
    raise TimeoutError(f"{slug}: job {job} se za {cekat_s} s nedokončil")


def ukazky(data: dict, base: Path, stav_path: Path, kola: list[int], only: list[str], seed: int, znovu: bool) -> None:
    """`znovu` (with `only`): the new image takes the file of the old sample, so the first sample stays first."""
    stav = json.loads(stav_path.read_text(encoding="utf-8")) if stav_path.exists() else {}
    plan = ukazky_plan(data)
    prace = [(s, z, k) for k in kola for s, u in plan.items() if (not only or s in only) and k <= len(u)
             for z in [u[k - 1]] if znovu or not any(x["kolo"] == k for x in stav.get(s, []))]
    print(f"zbývá {len(prace)} ukázek", flush=True)
    for i, (slug, zadani, kolo) in enumerate(prace, 1):
        t = time.time()
        try:
            name = vyrob(slug, zadani, seed)
        except Exception as e:  # one bad style must not stop hours of work; the repeated run picks it up
            print(f"[{i}/{len(prace)}] CHYBA {slug}: {e}", flush=True)
            continue
        old = next((x for x in stav.get(slug, []) if x["kolo"] == kolo), None)
        if old:
            d = knihovna.item_dir("style", slug, base) / "samples"
            (d / name).replace(d / old["vzorek"])
            name = old["vzorek"]
            stav[slug].remove(old)
        stav.setdefault(slug, []).append({"kolo": kolo, "zadani": zadani, "seed": seed, "vzorek": name})
        stav_path.parent.mkdir(parents=True, exist_ok=True)
        stav_path.write_text(json.dumps(stav, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[{i}/{len(prace)}] {slug} kolo {kolo} -> {name} ({time.time() - t:.0f} s)", flush=True)


def nahled(data: dict, base: Path, kategorie: str, out: Path, sloupce: int = 6, sirka: int = 300) -> None:
    """Contact sheet: one row per style, the samples next to its name."""
    polozky = sorted((p for p in [*data["nove"], *data["existujici"]] if p["kategorie"] == kategorie),
                     key=lambda p: p["poradi"])
    vyska = sirka * 3 // 4
    radky = []
    for p in polozky:
        d = knihovna.item_dir("style", p["slug"], base) / "samples"
        files = sorted(d.glob("*.jpg"), key=lambda f: int(f.stem)) if d.exists() else []
        radky.extend([(p["slug"], f) for f in files] or [(p["slug"], None)])
    rows = (len(radky) + sloupce - 1) // sloupce
    sheet = Image.new("RGB", (sloupce * sirka, rows * (vyska + 18)), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (slug, f) in enumerate(radky):
        x, y = (i % sloupce) * sirka, (i // sloupce) * (vyska + 18)
        if f:
            img = Image.open(f).convert("RGB")
            img.thumbnail((sirka - 4, vyska))
            sheet.paste(img, (x + 2, y + 16))
        draw.text((x + 3, y + 2), f"{slug} {f.stem if f else '-'}", fill="black")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=88)
    print(f"{out} {sheet.size} {out.stat().st_size // 1024} kB, {len(radky)} obrázků")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--knihovna", type=Path, default=None, help="jiná složka knihovny než NGM_KNIHOVNA / výchozí")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("karty")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--prepis", nargs="*", default=[], help="přepsat tyto nové karty textem z katalogu")
    u = sub.add_parser("ukazky")
    u.add_argument("--kolo", type=int, nargs="+", default=[1, 2, 3])
    u.add_argument("--only", nargs="*", default=[])
    u.add_argument("--seed", type=int, default=SEED)
    u.add_argument("--znovu", action="store_true", help="s --only: nahradit hotové ukázky novými")
    u.add_argument("--stav", type=Path, default=ROOT / "run" / "katalog-ukazky.json")
    n = sub.add_parser("nahled")
    n.add_argument("kategorie", choices=list(knihovna.STYLE_CATEGORIES))
    n.add_argument("out", type=Path)
    a = ap.parse_args()
    data = nacti()
    base = a.knihovna or knihovna.root()
    if a.cmd == "karty":
        karty(data, base, a.dry_run, tuple(a.prepis))
    elif a.cmd == "ukazky":
        if a.znovu and not a.only:
            ap.error("--znovu jen s --only")
        ukazky(data, base, a.stav, a.kolo, a.only, a.seed, a.znovu)
    else:
        nahled(data, base, a.kategorie, a.out)


if __name__ == "__main__":
    main()
