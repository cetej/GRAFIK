# The Pantheon poster as a panel document (step 3c), from the same renders and texts as scripts/3d/pantheon_plakat.py, free:
#   python scripts/3d/pantheon_dokument.py pohledy     renders into library/plakaty/pantheon-dokument/pohledy/<shot>, under the heavy lock
#   python scripts/3d/pantheon_dokument.py dokument [--engine http://127.0.0.1:8300]    new document and its exports
# The finished poster library/plakaty/pantheon stays as it is; the difference from it is measured in docs/spikes/2026-11-01-dokument-panely.md.
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "scripts" / "3d"), str(REPO / "shared")]

import pantheon_plakat as plakat  # noqa: E402

SHOTS = {"rez": ([2400, 1350], True), "rozklad": ([1020, 1720], True), "interier": ([960, 800], False),
         "beton_dolni": ([640, 400], False), "beton_stred": ([640, 400], False), "beton_horni": ([640, 400], False)}
FOLDER = "plakaty/pantheon-dokument/pohledy"
SAMPLES = (("beton_dolni", "Dole travertin", "asi 2 200 kg/m³"), ("beton_stred", "Uprostřed kusy cihel", "hustota nedoložená"), ("beton_horni", "Nahoře tuf a pemza", "asi 1 350 kg/m³"))


def render_all(out: Path) -> None:
    from engine.config import find_blender
    from ngm_shared.heavy_lock import heavy

    blender = find_blender()
    for shot, (res, layers) in SHOTS.items():
        d = out / shot
        d.mkdir(parents=True, exist_ok=True)
        with heavy("blender", owner="grafik", caller="pantheon dokument", wait_s=600):
            run = subprocess.run([blender, "-b", "--factory-startup", "-P", str(REPO / "scripts" / "3d" / "lod_pantheon.py"), "--", str(d / "model.glb"), "--render", str(d), "--shot", shot,
                                  "--res", str(res[0]), str(res[1]), *(["--vrstvy"] if layers else [])], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200)
        print(shot, "exit", run.returncode, flush=True)
        if run.returncode or not (d / "body.json").is_file():
            raise SystemExit(run.stderr[-1500:] or run.stdout[-1500:])


def label_of(name, smalls, where, pos, align, **extra) -> dict:
    return {"text": name, "small": smalls, "kotva": where if isinstance(where, str) else list(where), "pos": list(pos), "align": align, **extra}


def fields(folder: str, exploded: dict) -> dict:
    """`exploded` je body.json pohledu rozklad: kotvy rozložených dílů z něj berou rozměry."""
    r_o = exploded["dim"]["inner_d"] / 2 + exploded["dim"]["wall"]
    up = exploded["explode"]
    drawing, plan_words = plakat.plan(exploded["dim"], 1270, 2010)
    box = [1260, 2000, 280, 200]
    panels = [
        {"id": "hlavni", "typ": "obraz", "poradi": 1, "nazev": "Hlavní řez", "rect": [0, 30, 1600, 900], "zdroj": {"slozka": f"{folder}/rez"}, "vrstvy": plakat.HERO_LAYERS,
         "prekryvy": [{"typ": "krivka", "body": "kruh"}, {"typ": "usecka", "od": "pata_l", "do": "pata_p"}, {"typ": "usecka", "od": "podlaha_stred", "do": "vrchol_koule"}],
         "labels": [label_of(name, [small], where, pos, align) for name, small, where, pos, align in plakat.HERO_LABELS]},
        {"id": "rozklad", "typ": "obraz", "poradi": 2, "nazev": "Rozložení", "titulek": {"text": "Z čeho se skládá", "x": 50, "y": 980}, "rect": [0, 992, 620, 1046], "zdroj": {"slozka": f"{folder}/rozklad"}, "vrstvy": plakat.EXPLODED_LAYERS,
         "labels": [label_of(name, small, where, pos, "left", size=22) for name, small, where, pos in (
             ("Bronzový prstenec", ["lemuje okulus"], (4.7, 0, 44.0 + up["lip"]), (560, 1030)),
             ("Kupole", ["jedna skořepina: 7 prstenců", "venku, kazety uvnitř"], (r_o * 0.45, r_o * 0.1, 40 + up["dome_low"]), (560, 1200)),
             ("Stěna", ["8 pilířů, 7 výklenků a vchod"], (r_o * 0.75, r_o * 0.55, 10), (560, 1480)),
             ("Podlaha", ["mírně vypouklá, s odtoky"], (10, 12, up["floor"]), (560, 1700)),
             ("Základ", ["prstenec 7,2 × 4,7 m na jílu"], (24.0, 3.0, -2.5 + up["found"]), (560, 1860)))]},
        {"id": "interier", "typ": "obraz", "poradi": 3, "nazev": "Pohled k okulu", "titulek": {"text": "Pohled k okulu", "x": 860, "y": 980}, "rect": [860, 992, 710, 592], "zdroj": {"slozka": f"{folder}/interier"}},
    ]
    for i, (shot, name, small) in enumerate(SAMPLES):
        panel = {"id": shot, "typ": "obraz", "poradi": 4 + i, "nazev": name, "rect": [860 + i * 240, 1652, 230, 144], "zdroj": {"slozka": f"{folder}/{shot}"}, "pod": {"text": name, "small": small}}
        if i == 0:
            panel["titulek"] = {"text": "Beton: čím výš, tím lehčí", "x": 860, "y": 1636}
        panels.append(panel)
    panels += [
        {"id": "proc", "typ": "text", "poradi": 7, "nazev": "Proč stojí", "titulek": {"text": "Proč stojí", "x": 860, "y": 1912}, "rect": [860, 1926, 700, 320], "size": 26, "small_size": 21, "krok": 104, "sirka": 44,
         "items": [{"value": value, "text": small} for value, small in plakat.WHY]},
        {"id": "cisla", "typ": "fakta", "poradi": 8, "nazev": "Čísla", "titulek": {"text": "Čísla", "x": 50, "y": 2076}, "rect": [50, 2097.6, 780, 130], "size": 36, "small_size": 21, "sirka": 15,
         "items": [{"value": value, "text": small, "x": x} for x, (value, small) in zip((50, 190, 372, 530, 668), plakat.FACTS)]},
        {"id": "pudorys", "typ": "kresba", "poradi": 9, "nazev": "Půdorys", "rect": box, "viewbox": box, "kresba": drawing, "texty": plan_words},
    ]
    return {"title": "Pantheon", "subtitle": "Největší kupole z nevyztuženého betonu\nŘím, asi 114–126 n. l.", "size": "1600x2400", "accent": plakat.ACCENT,
            "sources": plakat.SOURCES.removeprefix("Zdroj: "), "nadpis": {"x": 50, "y": 118, "size": 88}, "paticka_y": 2306, "panels": panels}


def call(base: str, method: str, path: str, body=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode("utf-8"), method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path}: {e.code} {e.read().decode('utf-8', 'replace')[:800]}") from e


def main() -> int:
    from engine.config import Settings

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = Settings().library_dir / FOLDER
    if sys.argv[1] == "pohledy":
        render_all(root)
        return 0
    base = sys.argv[sys.argv.index("--engine") + 1] if "--engine" in sys.argv else "http://127.0.0.1:8300"
    exploded = json.loads((root / "rozklad" / "body.json").read_text(encoding="utf-8"))
    doc = call(base, "POST", "/api/v2/infographics/panels", fields(FOLDER, exploded))
    print("dokument", doc["id"])
    for check in call(base, "GET", f"/api/v2/infographics/{doc['id']}/kontrola"):
        print("ok" if check["ok"] else " !", check["text"])
    for fmt in ("png", "pdf", "svg"):
        print(call(base, "POST", f"/api/v2/infographics/{doc['id']}/export", {"format": fmt}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
