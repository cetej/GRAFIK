"""Plnění 3D skladu na D: z GRAFIKu (DECISIONS 2026-11-05).

    python scripts/sklad3d.py smithsonian "woolly mammoth" trilobite --na-tema 3   # Smithsonian CC0 podle témat
    python scripts/sklad3d.py nase                                                 # zkontrolované modely z library/3d

Smithsonian jde přes `engine/hotove3d.py` (licence z Open Access API, jen CC0). Model, který už ve skladu je,
se nestahuje znovu. `nase` dožene kopie modelů zaškrtnutých dřív, než kopie při kontrole existovala.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import hotove3d  # noqa: E402  (engine/__init__ dá na sys.path i shared/)
from engine.config import Settings  # noqa: E402
from engine.models3d import Model3dLibrary  # noqa: E402
from ngm_shared import sklad3d  # noqa: E402
from ngm_shared.sklad import SkladError  # noqa: E402


def smithsonian(temata: list[str], na_tema: int) -> None:
    for tema in temata:
        for k in hotove3d.search_si(tema, limit=na_tema):
            if (sklad3d.dir3d() / "smithsonian" / k["id"] / "puvod.json").exists():
                print(f"{tema}: {k['nazev']} už ve skladu je")
                continue
            try:
                glb, info = hotove3d.fetch_si(k["id"])
                z = sklad3d.uloz_model("smithsonian", k["id"], glb, {**info, "popis": f"Smithsonian, nalezeno pro: {tema}"})
            except (hotove3d.Hotove3dError, SkladError) as e:
                print(f"{tema}: {k['nazev']}: {e}")
                continue
            print(f"{tema}: {z['nazev']} · {z['bajtu'] / 1e6:.1f} MB · {z['licence']}")
    print(f"index: {len(sklad3d.sestav_index())} položek")


def nase() -> None:
    lib = Model3dLibrary(Settings().library_dir / "3d")
    n = 0
    for m in lib.list():
        for v in lib.get(m["id"])["versions"]:
            if v.get("review") and not v.get("sklad"):
                z = sklad3d.uloz_nas(lib.vdir(v["id"], v["version"]), v)
                lib.update(v["id"], v["version"], sklad=z["id"], sklad_chyba=None)
                n += 1
                print(f"{z['id']} · {z['bajtu'] / 1e6:.1f} MB")
    print(f"zkopírováno {n} zkontrolovaných verzí")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("smithsonian")
    s.add_argument("temata", nargs="+")
    s.add_argument("--na-tema", type=int, default=3)
    sub.add_parser("nase")
    a = p.parse_args()
    smithsonian(a.temata, a.na_tema) if a.cmd == "smithsonian" else nase()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
