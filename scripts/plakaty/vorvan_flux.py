"""Realistická kůže a vnitřnosti vorvaně z lokálního FLUXu, tvar drží render 3D modelu (role geometry). 0 USD.

Operátor 5. 11.: model z průřezů „vypadá jako z gumy, nebo kovové torpédo“, vnitřnosti jako „špatně nalepená fotografie“;
zvolil „Render jako předloha FLUXu“. Postup:
  1. python scripts/3d/velsen_studna_run.py vorvan_scena.py RENDER --fmt 16x9 --vorvan vorvan-lod/v1 --predloha   (a 9x16)
  2. python scripts/plakaty/vorvan_flux.py RENDER [--fmt 16x9] [--seeds 61 62 63] [--jen vnitrek]
  3. python scripts/plakaty/vorvan_flux.py RENDER --fmt 16x9 --vyber SEED [--vnitrek SEED]
Ke každému seedu: <fmt>/flux-kuze-<seed>.png a flux-vnitrek-<seed>.png (RGBA ve velikosti renderu) a shoda obrysu
s modelem (IoU), aby FLUX nezměnil tvar ani měřítko k potápěči. Vybraný seed: --vyber SEED složí RENDER-flux/<fmt>/
(kůže s oknem do těla podle alfy kuze.png z Blenderu, vnitřnosti, potápěč a body.json beze změny).
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "shared"))
from engine.panels import cut_green  # noqa: E402
from ngm_shared import grafik_client as gc  # noqa: E402

GREEN = (0, 177, 64)
SIZE = {"16x9": (1536, 640), "9x16": (576, 1408)}     # stejný poměr jako render 2400×1000 a 900×2200
SCREEN = "on a seamless solid bright chroma key green background, one even green colour, nothing else in the picture. "
WHALE = (SCREEN + "Photorealistic adult male sperm whale with exactly the shape, pose, angle, size and outline of <ref_image_0>, "
         "the open narrow lower jaw with two rows of conical ivory teeth exactly where it is in the reference. Matte dark brownish grey skin, "
         "deeply wrinkled corrugated skin like a dried prune on the flanks behind the head, pale whitish scars and circular sucker scratches on "
         "the huge blunt head, white lips, small eye just above the mouth corner, small paddle pectoral fin, low dorsal hump with knuckles. Smooth throat and belly without any long grooves or pleats (not a rorqual), skin wrinkles short and irregular, not in regular bands; flukes visible as broad flat blades. "
         "Natural underwater daylight from above, wildlife photograph, sharp detail.")
ORGANS = (SCREEN + "Realistic anatomical 3D illustration of the digestive organs of a sperm whale with exactly the shapes, positions and sizes "
          "of <ref_image_0>: a fleshy muscular esophagus tube, a thick-walled muscular first stomach with deep ridges, a larger second stomach "
          "with folded glandular lining, two small round connecting chambers, a densely coiled long intestine. Wet tissue, fine blood vessels, "
          "pink, red and cream colours, soft studio light, medical illustration, no labels.")


def on_green(rgba: Image.Image, size) -> Image.Image:
    bg = Image.new("RGBA", rgba.size, (*GREEN, 255))
    bg.alpha_composite(rgba)
    return bg.convert("RGB").resize(size, Image.LANCZOS)


def iou(a: Image.Image, b: Image.Image) -> float:
    x, y = np.asarray(a.getchannel("A")) > 40, np.asarray(b.getchannel("A")) > 40
    return float((x & y).sum() / max((x | y).sum(), 1))


def run(render: Path, fmt: str, seeds: list[int], only: list[str] | None = None) -> None:
    d = render / fmt
    full = Image.open(d / "predloha-kuze.png").size
    jobs = []
    for name, prompt in (("kuze", WHALE), ("vnitrek", ORGANS)):
        if only and name not in only:
            continue
        # na výšku FLUX vnitřnosti kreslí jako lidské z atlasu (IoU 0,14–0,17) a kůži hůř (šedý ocas): 9:16 ležato a zpět
        turn = fmt == "9x16"
        size = SIZE[fmt][::-1] if turn else SIZE[fmt]
        ref = d / f"predloha-{name}-zelena.png"
        src = Image.open(d / f"predloha-{name}.png").convert("RGBA")
        on_green(src.rotate(90, expand=True) if turn else src, size).save(ref)
        for seed in seeds:
            jobs.append((name, seed, turn, gc.submit(prompt, size=f"{size[0]}x{size[1]}", seed=seed,
                                               refs=[{"path": str(ref), "role": "geometry"}], caller="vorvan-infografika")))
    for name, seed, turn, job in jobs:
        raw = gc.download(gc.wait(job), d / "tmp")[0]
        cut = cut_green(Image.open(raw).convert("RGBA"))
        cut = (cut.rotate(-90, expand=True) if turn else cut).resize(full, Image.LANCZOS)
        out = d / f"flux-{name}-{seed}.png"
        cut.save(out)
        print(f"{fmt} {name} seed {seed}: shoda obrysu s modelem IoU {iou(cut, Image.open(d / f'predloha-{name}.png')):.3f}  {out.name}", flush=True)


def pick(render: Path, fmt: str, seed: int, inner_seed: int | None = None) -> None:
    src, dst = render / fmt, render.with_name(render.name + "-flux") / fmt
    dst.mkdir(parents=True, exist_ok=True)
    for f in ("potapec.png", "body.json"):
        shutil.copy2(src / f, dst / f)
    flux = Image.open(src / f"flux-kuze-{seed}.png").convert("RGBA")
    window = np.asarray(Image.open(src / "kuze.png").getchannel("A"), np.float32) / 255     # obrys a okno do těla z Blenderu
    a = np.minimum(np.asarray(flux.getchannel("A"), np.float32) / 255, np.where(window > 0.03, window, 0))
    flux.putalpha(Image.fromarray((a * 255).astype("uint8")))
    flux.save(dst / "kuze.png")
    inner = Image.open(src / f"flux-vnitrek-{inner_seed or seed}.png").convert("RGBA")
    cavity = Image.open(src / "vnitrek.png").convert("RGBA")          # tmavá stěna dutiny z Blenderu pod vnitřnostmi
    cavity.alpha_composite(inner)
    cavity.save(dst / "vnitrek.png")
    print("složeno", dst)


def transpose(render: Path) -> None:
    """9:16 ze složené 16:9 překlopením podle úhlopříčky: hlava nahoru, břicho s tlamou doprava k popiskům. Je to týž vorvaň
    z druhé strany. Kamera 9:16 ukazovala víc břicha a FLUX na něm kreslil dlouhé rýhy jako u plejtváka (5. 11.)."""
    src, dst = render.with_name(render.name + "-flux") / "16x9", render.with_name(render.name + "-flux") / "9x16"
    dst.mkdir(parents=True, exist_ok=True)
    for f in ("kuze.png", "vnitrek.png", "potapec.png"):
        Image.open(src / f).transpose(Image.Transpose.TRANSPOSE).save(dst / f)
    body = json.loads((src / "body.json").read_text(encoding="utf-8"))
    body["points"] = {k: [y, x] for k, (x, y) in body["points"].items()}
    body["size"] = body["size"][::-1]
    (dst / "body.json").write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
    print("9x16 z 16x9", dst)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("render", type=Path)
    p.add_argument("--fmt", choices=("16x9", "9x16"), action="append")
    p.add_argument("--seeds", type=int, nargs="+", default=[61, 62, 63])
    p.add_argument("--vyber", type=int)
    p.add_argument("--jen", choices=("kuze", "vnitrek"), action="append")
    p.add_argument("--vnitrek", type=int, help="jiný seed pro vnitřnosti než pro kůži")
    p.add_argument("--z-16x9", dest="z169", action="store_true", help="9:16 překlopením složené 16:9")
    a = p.parse_args()
    if a.z169:
        transpose(a.render)
        return
    for fmt in a.fmt or ["16x9", "9x16"]:
        pick(a.render, fmt, a.vyber, a.vnitrek) if a.vyber else run(a.render, fmt, a.seeds, a.jen)


if __name__ == "__main__":
    main()
