# The main picture of the Velsen article, 3:2, from local FLUX: hooded legionaries stab their comrade in the hips (the wounds as in the book, p. 159-163), the victim as the figure in the well infographic.
#   python scripts/plakaty/velsen_hero.py LIB --seeds 301,302 [--muz skupiny/sedici-s123.png] [--prekresli hero/hero-335.png]
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "shared")]
from ngm_shared import grafik_client as gc  # noqa: E402

PROMPT = ("A nineteenth-century history painting in the manner of Jean-Leon Gerome: precise natural drawing, sober natural colours, restrained light, nothing theatrical. "
          "Dusk in the rain inside a Roman auxiliary fort on the Dutch coast in the first century, a muddy lane between long barracks of smooth pale plastered wattle with a dark timber frame and thatched roofs, no windows, no glass, no panelled doors. One burning torch lies on the ground and throws low orange light. "
          "Three Roman soldiers off duty, not monks: each in a knee-length hooded wool travelling cloak of dull brown, the hood pulled over the face, bare muscular shins below the cloak, open-work hobnailed Roman caligae sandals, a leather soldier's belt where the cloak falls open. No armour, no helmets. They overpower the man of <ref_image_0>: the same face, heavy jaw, short black hair, stubble, deep-set eyes, thick dark brows, a man past thirty, very tall and square-built, lean, in an off-white wool tunic to the knee with a soldier's belt, a dark red wool cloak sliding off one shoulder, Roman caligae on his feet. "
          "He is on his feet, seen at an angle, dragged backwards, his knees giving way, head thrown back, mouth open in a scream, his whole body arched in agony. One hooded soldier behind him twists his arm up his back and with the other hand drives a short broad Roman pugio dagger into his left hip from behind. "
          "A second hooded soldier, crouching low in front of him, drives the same dagger into his right hip. A third holds him round the chest. The pugio is short and wide, a waisted leaf-shaped blade no longer than a hand. Dark blood on the tunic at the hips. "
          "Nobody looks at the camera. A real moment caught in motion, the figures overlapping, one cut by the edge of the frame. Correct human proportions and perspective. No swords, no long blades, no gold, no lantern, no text.")


REPAINT = ("The same picture as <ref_image_0>: the same painting, the same men in the same poses, the same faces, cloaks, belts, sandals and daggers, the same torch on the ground, the same light and the same place in the frame. "
           "Only the buildings change: long Roman fort barracks with smooth pale lime-plastered walls over wattle and a dark timber frame, low thatched roofs without any chimney, no logs, no planks, no window bars. A nineteenth-century history painting, precise natural drawing, sober natural colours. No text.")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    lib = Path(sys.argv[1])
    seeds = [int(s) for s in sys.argv[sys.argv.index("--seeds") + 1].split(",")]
    muz = sys.argv[sys.argv.index("--muz") + 1] if "--muz" in sys.argv else "skupiny/sedici-s123.png"
    out = lib / "hero"
    out.mkdir(parents=True, exist_ok=True)
    # the face only: a whole seated figure would make him sit, a wider crop loses the likeness (8 GB: the reference stays small)
    fig = Image.open(lib / muz).convert("RGB")
    frame = Image.open(lib / "render/muz/maska.png").convert("L").point(lambda v: 255 if v > 32 else 0).getbbox()
    fw, fh = frame[2] - frame[0], frame[3] - frame[1]
    head = fig.crop((frame[0] + fw * 34 // 100, frame[1], frame[0] + fw * 78 // 100, frame[1] + fh * 33 // 100))
    head.thumbnail((240, 240))
    small = out / "_muz-male.png"
    head.save(small)
    refs, prompt = [{"path": str(small), "role": "subject"}], PROMPT
    if "--prekresli" in sys.argv:    # the chosen picture again with only the buildings corrected; one reference, two do not fit next to 1200 x 800
        chosen = Image.open(lib / sys.argv[sys.argv.index("--prekresli") + 1]).convert("RGB")
        chosen.thumbnail((384, 256))
        small = out / "_vyber-male.png"
        chosen.save(small)
        refs = [{"path": str(small), "role": "geometry"}]
        prompt = REPAINT
    jobs = {seed: gc.submit(prompt, size="1200x800", seed=seed, refs=refs, caller="velsen-hero") for seed in seeds}
    for seed, j in jobs.items():
        target = out / f"hero-{seed}.png"
        gc.download(gc.wait(j, timeout=1500), out)[0].replace(target)
        print(target.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
