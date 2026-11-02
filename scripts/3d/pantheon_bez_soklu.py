# The Pantheon panel document again, the main section without the big grey plinth (operator 2026-11-02), free:
#   python scripts/3d/pantheon_bez_soklu.py pohled     render into library/plakaty/pantheon-dokument/pohledy/rez_zem, under the heavy lock
#   python scripts/3d/pantheon_bez_soklu.py dokument   new document through the running Engine, then its 16:9 version
# Same camera as shot rez, so every label stays where it was. Other panels and all texts are those of pantheon_dokument.py; 20261101-202603-9914 stays as it is.
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "scripts" / "3d"), str(REPO / "shared")]

import pantheon_dokument as dokument  # noqa: E402

LIBRARY = Path("C:/Users/stock/Documents/000_NGM/GRAFIK/library")
ENGINE = "http://127.0.0.1:8300"
SHOT = "rez_zem"
HEIGHT = 1182           # z 1350, stavba končí na pixelu kolem 1150
OMIT = ["rozklad", "interier", "beton_dolni", "beton_stred", "beton_horni", "proc", "pudorys"]


def render() -> None:
    from engine.config import find_blender
    from ngm_shared.heavy_lock import heavy

    out = (LIBRARY / dokument.FOLDER / SHOT).resolve()
    out.mkdir(parents=True, exist_ok=True)
    res = dokument.SHOTS["rez"][0]
    with heavy("blender", owner="grafik", caller="pantheon bez soklu", wait_s=1500):
        run = subprocess.run([find_blender(), "-b", "--factory-startup", "-P", str(REPO / "scripts" / "3d" / "lod_pantheon.py"), "--", str(out / "model.glb"), "--render", str(out), "--shot", SHOT,
                              "--res", str(res[0]), str(res[1]), "--vrstvy"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200)
    print("exit", run.returncode, flush=True)
    if run.returncode or not (out / "body.json").is_file():
        raise SystemExit(run.stderr[-1500:] or run.stdout[-1500:])


def trim(folder: Path) -> None:
    """Prázdný pruh pod stavbou pryč, jen zespodu: body i popisky zůstávají na svých pixelech."""
    info = json.loads((folder / "body.json").read_text(encoding="utf-8"))
    if info["res"][1] == HEIGHT:
        return
    for file in [folder / "rez.png", *folder.glob("vrstva-*.png")]:
        with Image.open(file) as im:
            im.load()
            im.crop((0, 0, im.width, HEIGHT)).save(file)
    info["res"][1] = HEIGHT
    (folder / "body.json").write_text(json.dumps(info), encoding="utf-8")


def document() -> None:
    root = LIBRARY / dokument.FOLDER
    trim(root / SHOT)
    exploded = json.loads((root / "rozklad" / "body.json").read_text(encoding="utf-8"))
    fields = dokument.fields(dokument.FOLDER, exploded)
    hero = fields["panels"][0]
    hero["zdroj"] = {"slozka": f"{dokument.FOLDER}/{SHOT}"}
    hero["rect"][3] = hero["rect"][2] * HEIGHT / dokument.SHOTS["rez"][0][0]
    doc = dokument.call(ENGINE, "POST", "/api/v2/infographics/panels", fields)
    print("dokument", doc["id"])
    wide = dokument.call(ENGINE, "POST", f"/api/v2/infographics/{doc['id']}/reformat", {"size": "16:9", "vynechat_panely": OMIT, "vynechat_popisky": {"hlavni": [4, 8]}})
    print("16:9", wide["id"], wide["size"])
    for check in dokument.call(ENGINE, "GET", f"/api/v2/infographics/{wide['id']}/kontrola"):
        print("ok" if check["ok"] else " !", check["text"])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    render() if sys.argv[1] == "pohled" else document()
