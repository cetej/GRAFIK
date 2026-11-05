"""Obrazy k infografice „Spolkl by vorvaň člověka?“: vorvaň z boku a potápěč, každý na zeleném plátně jako vlastní vrstva.

Lokální FLUX, 0 USD. Tvar vorvaně drží předloha z Commons (Physeter macrocephalus1.jpg, public domain) jako `geometry`.
Výstup: library/plakaty/vorvan/obrazy/<název>-<seed>.png
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
from ngm_shared import grafik_client as gc  # noqa: E402

DATA = Path(os.environ.get("GRAFIK_DATA", ROOT))     # knihovna a předlohy hlavního checkoutu
OUT = DATA / "library" / "plakaty" / "vorvan" / "obrazy"
DRAWING = DATA / "refs" / "library" / "20261105-071652-fd47" / "image.png"
SKIN = DATA / "refs" / "library" / "20261105-071627-f9c4" / "image.png"     # ocas vorvaně, B. Spragg, CC0: kůže, ne tvar
SCREEN = "on a seamless solid bright chroma key green background, one even green colour, nothing else in the picture, soft even light. "

WHALE = (SCREEN + "Photorealistic adult male sperm whale, exact side view from the left, the whole animal from the blunt square head to the tail flukes "
         "with space around it, horizontal, mouth slightly open showing the narrow lower jaw with conical white teeth, dark grey wrinkled skin, "
         "small eye, small pectoral fin, low dorsal hump, natural proportions, the head one third of the body length. Wildlife documentary photograph.")
DIVER = (SCREEN + "Photorealistic scuba diver swimming horizontally to the left, seen exactly from the side, full body from head to fins with space around it, "
         "black wetsuit, single silver tank on the back, mask and regulator, arms forward, fins behind. Studio photograph.")

ORGANS = (SCREEN + "Highly detailed realistic 3D anatomical illustration of the digestive tract of a sperm whale, exact side view, horizontal, left to right: "
          "a narrow muscular esophagus tube, then a thick-walled muscular first stomach chamber with deep ridged folds, then a larger yellowish glandular "
          "second stomach chamber, then two small round connecting chambers, then the start of a long coiled intestine on the right. Wet glossy pink and "
          "cream tissue with visible muscle fibres and blood vessels, medical 3D render, soft studio light, no labels.")
SCENES = {
    "tlama": "Photorealistic underwater wide shot into the open mouth of a sperm whale: the long narrow lower jaw with two rows of conical white teeth, the toothless upper jaw with sockets, pale pink-white mouth lining, a small scuba diver hovering in front of the jaw, blue deep-sea light.",
    "jicen": "Photorealistic view inside the narrow esophagus of a whale: a tight round fleshy tube of pink muscle with lengthwise folds, a scuba diver squeezed inside with arms forward, small torch light, claustrophobic, dark red tones.",
    "predzaludek": "Photorealistic view inside the first stomach chamber of a sperm whale: very thick muscular folded walls of pale pink-grey tissue squeezing in, crushed squid with tentacles, a scuba diver bracing against the walls with a torch, dim light.",
    "zaludek": "Photorealistic view inside the large second stomach chamber of a sperm whale: glistening yellowish glandular walls, murky yellow digestive fluid, thousands of small dark brown squid beaks piled on the floor and floating, a scuba diver with a torch, dim eerie light.",
}


def inside() -> None:
    """3. kolo: 3D orgány na zeleném plátně a čtyři scény zevnitř (operátor: vytrácí se 3D a zajímavé detaily)."""
    jobs = [("organy", seed, gc.submit(ORGANS, size="1536x512", seed=seed, caller="vorvan-infografika")) for seed in (41, 42)]
    jobs += [(f"scena-{name}", 51, gc.submit(prompt, size="1024x640", seed=51, caller="vorvan-infografika")) for name, prompt in SCENES.items()]
    OUT.mkdir(parents=True, exist_ok=True)
    for name, seed, job in jobs:
        path = gc.download(gc.wait(job), OUT / "tmp")[0]
        target = OUT / f"{name}-{seed}.png"
        path.replace(target)
        print(target, job, flush=True)


def main() -> None:
    jobs = []
    if "--kuze" in sys.argv:     # 2. kolo: kresba dala tvar i zrnitost tužky, kůži povede fotka
        prompt = WHALE.replace("dark grey wrinkled skin", "smooth wet dark brownish grey skin with fine wrinkles and pale scars, like the skin in the photo, no drawing texture")
        for seed in (31, 32, 33):
            jobs.append(("vorvan", seed, gc.submit(prompt, size="1536x576", seed=seed, caller="vorvan-infografika", confirm_cost=True,     # 0,01 USD: Haiku popíše kůži slovy
                                                   refs=[{"path": DRAWING, "role": "geometry"}, {"path": SKIN, "role": "style"}])))
        sys.argv.append("--jen-tyto")
    for seed in () if "--jen-tyto" in sys.argv else (11, 12, 13):
        jobs.append(("vorvan", seed, gc.submit(WHALE, size="1536x576", seed=seed, refs=[{"path": DRAWING, "role": "geometry"}], caller="vorvan-infografika")))
    for seed in () if "--jen-tyto" in sys.argv else (21, 22):
        jobs.append(("potapec", seed, gc.submit(DIVER, size="1024x576", seed=seed, caller="vorvan-infografika")))
    OUT.mkdir(parents=True, exist_ok=True)
    for name, seed, job in jobs:
        path = gc.download(gc.wait(job), OUT / "tmp")[0]
        target = OUT / f"{name}-{seed}.png"
        path.replace(target)
        print(target, job, flush=True)


if __name__ == "__main__":
    inside() if "--uvnitr" in sys.argv else main()
