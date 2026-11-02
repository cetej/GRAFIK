# Pictures for the two Velsen infographics, local FLUX only, 0 USD. Text never comes from the generator.
#   python scripts/plakaty/velsen_obraz.py studna RENDER_DIR PODKLADY OUT [--seeds 11,12]   the Blender section with the man as `geometry`
#   python scripts/plakaty/velsen_obraz.py sceny RENDER_DIR PODKLADY OUT [--jen 2,5] [--seed 501] [--styl hist-akademismus]   six stagings repainted, the victim with the face from the book
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "shared")]
from ngm_shared import grafik_client as gc  # noqa: E402

MAN_HEAD, MAN_FOOT = 185, 800     # in velsen_rekonstrukce_muze.png, the man seated is about 0.95 m (p. 42: 1.84-1.91 m tall, flexed)

STUDNA = ("Photorealistic museum-quality cutaway of a Roman well, a real archaeological section photographed in raking light. Keep the composition, the proportions and every object exactly where they are in the reference. "
          "Dark wet layered soil and sand around it, real grain, roots, stones and strata. A flooded barrel-lined shaft: a wide wine barrel of dark wet silver fir staves bound with hazel withies, murky green water, and below it a narrower barrel filled with clean grey sand, small white sea shells and a rusty iron chain. "
          "At the bottom of the wide barrel a dead Roman soldier, a very tall young man, sits slumped with bent knees and bowed head: short black hair, off-white wool tunic, dark red wool cloak, military belt, one leather sandal, real skin, real anatomy, hands on his shins. "
          "A long wooden stake leans across his chest. Broken dark basalt millstone fragments, field stones and burnt orange clay lie heaped beside and behind him. "
          "Natural materials, deep shadows, no glow. No text, no labels, no people other than him.")

FACE = ("The victim, the tall man described below, is a huge heavily built soldier worn out by service, looking well over thirty: broad heavy jaw, thick dark brows, dark tired eyes with heavy bags, weathered tanned skin, short black hair with a ragged fringe, stubble. ")
COMMON = ("Repaint <ref_image_0> as a finished painting: exactly the same camera, the same number of figures, the same poses and places, the same buildings and the same light. "
          "The mannequins become real people with realistic faces, hands and clothes, the shapes around them real timber, thatch, plaster and mud. No mannequins, no 3D look. "
          "Roman fort on the North Sea coast of the Netherlands, about AD 28. Plastered timber-framed buildings under thatch, earth and timber rampart. No text, no letters, no modern objects. ")

# Only the place, without people: painted calmly, the people are cut-outs on top (velsen_skladba.py). The operator: FLUX renders "přetažené".
BACK = ("Paint <ref_image_0> as the empty background of a nineteenth-century academic history painting: exactly the same camera, the same buildings and the same horizon. "
        "Restrained natural colours, soft air and depth, quiet even brushwork, nothing theatrical, no dramatic clouds. Nobody in the picture, no people, no figures, no animals. No text. ")
BACKS = {
    1: "Grey dawn behind the rampart of a small Roman timber fort on the Dutch coast: an earth and timber rampart with a wattle breastwork, plastered wattle-and-daub barracks with thatched roofs beyond, one roof far off burning with thin smoke, trampled mud in the foreground.",
    2: "Night by a harbour: a square timber well kerb with two corner posts, plastered thatched buildings dark on both sides, a ship's mast against the sky, cold moonlight, one small oil lamp on the kerb, dry trampled earth, no water, no puddles, no reflections on the ground.",
    3: "Cold grey morning with pale fog: a muddy parade ground inside a Roman fort, plastered wattle-and-daub barracks with timber frames and thatched roofs, an earth rampart with a timber palisade behind, flat white-grey sky, no sun.",
    4: "Night, a narrow gap between two plastered barracks with timber frames, one torch burning on the left wall with warm light, dark mud, a broken vine stick and an iron helmet lying in the mud.",
    5: "Blue dusk, sea mist over a tidal marsh: reeds, black mud, still water, a thin line of warm light on the horizon, the low dark line of a small timber fort very far off, hardly visible in the mist.",
    6: "Violet twilight in a burned-out timber fort: charred posts, a few dim embers among the ash, thin smoke, a square timber well kerb with two corner posts in the middle, rough broken fragments of dark porous basalt millstones and field stones heaped on the ground before it.",
}
SCENES = {
    1: "Dawn, orange light through smoke. On the rampart the tall Roman soldier in a mail shirt over a tunic, bareheaded, his iron helmet fallen in the mud, staggers back wounded. A bearded Frisian warrior in a shaggy wool cloak and trousers drives a spear at him, others come over the breastwork with spears and round wooden shields. Burning thatch behind.",
    2: "Night by the harbour. Two men in hooded wool cloaks, faces hidden, lower the limp body of the tall man in a dark red cloak and off-white tunic feet first into a well with a square timber kerb, gripping him under the arms. His head falls to one side, eyes closed. One small oil lamp on the kerb, cold moonlight, a mast against the sky.",
    3: "Cold grey morning, pale fog. A kneeling prisoner, the tall man in a torn undyed tunic with no belt, hands tied behind his back, faces us. Two Roman legionaries in banded iron plate armour, early lorica segmentata with bronze fittings over red tunics, and iron helmets stand over him. In the left foreground a centurion in a mail shirt and dark red cloak, a transverse crest across his helmet from ear to ear, holds a straight vine stick. Behind them silent ranks of legionaries, some in banded plate armour, some in mail.",
    4: "Night, a narrow gap between plastered barracks, one torch on the wall, hard orange light and black shadows. Three furious men in plain tunics, no armour, force the big tall man in an off-white tunic and silver-plated belt to bend forward over a wooden crate, one grips his neck, one wrenches his arm, the third behind him raises a short leaf-shaped dagger. A snapped vine stick and an iron helmet lie in the mud.",
    5: "Blue dusk, sea mist over a tidal marsh, reeds and black mud, a thin line of warm light on the horizon. The captive, the tall man in a torn undyed tunic, bareheaded, kneels with bound hands. Around him stand three bearded long-haired Frisian tribesmen in shaggy wool cloaks and trousers, one holds a Roman dagger and the red cloak taken from the captive, one a spear. A small timber fort far off on the horizon.",
    6: "Violet twilight in the burned-out fort, charred posts, glowing embers and thin smoke. Men in plain wool stand round a square timber well kerb with two corner posts and lower the dead tall man on ropes held in their hands, he sits slumped in a sling, in an off-white tunic, dark red cloak and belt with a silver dagger sheath, head fallen forward. Jagged fragments of broken dark basalt millstones are heaped on the ground before the kerb. An old man raises both open hands.",
}


def on_paper(im: Image.Image) -> Image.Image:
    rgb = np.asarray(im.convert("RGB"), dtype=np.float32) / 255
    a = np.clip((1 - rgb.min(axis=2) - 0.03) * 7.0, 0, 1)[..., None]
    col = np.clip((rgb - (1 - a)) / np.maximum(a, 0.05), 0, 1)
    return Image.fromarray((np.dstack([col, a]) * 255).astype("uint8"), "RGBA")


def guide(render: Path, podklady: Path) -> Image.Image:
    """Back of the render, the man from the book's drawing at true size, the stake and stones in front: only a guide for FLUX, the drawing does not stay in the picture."""
    points = json.loads((render / "body.json").read_text(encoding="utf-8"))["points"]
    px_m = points["o1"][0] - points["o0"][0]
    man = on_paper(Image.open(podklady / "muz_cely.png"))
    k = 0.95 * px_m / (MAN_FOOT - MAN_HEAD)
    man = man.resize((round(man.width * k), round(man.height * k)), Image.LANCZOS)
    base = Image.open(render / "zadni.png").convert("RGBA")
    x = round(points["floor"][0] - man.width * 0.50)
    y = round(points["floor"][1] - (MAN_FOOT + 30) * k)
    base.alpha_composite(man, (x, y))
    base.alpha_composite(Image.open(render / "predni.png").convert("RGBA"))
    return base.convert("RGB")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    what = sys.argv[1]
    def opt(name, default):
        return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default
    if what == "tvar":     # velsen_obraz.py tvar SCENA.png PODKLADY OUT.png --kde X,Y,SIZE [--seed 7]: the victim's head repainted after the book's reconstruction, pasted back with a soft edge
        scene, podklady, out = Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
        x, y, size = (int(v) for v in opt("--kde", "").split(","))
        im = Image.open(scene).convert("RGB")
        small = out.parent / "_male"
        small.mkdir(exist_ok=True, parents=True)
        crop = small / f"{out.stem}-vyrez.png"
        im.crop((x, y, x + size, y + size)).resize((384, 384), Image.LANCZOS).save(crop)
        face = small / "tvar.png"
        Image.open(podklady / "tvar_stary.png").convert("RGB").resize((280, 350), Image.LANCZOS).save(face)
        prompt = ("Repaint <ref_image_0> exactly: the same head angle, the same pose, the same light and colours, the same clothes and background. "
                  "Only the face changes: it is the man in <ref_image_1>, the same broad heavy jaw, thick dark brows, tired dark eyes with heavy bags, wide nose, weathered skin, short black hair with a ragged fringe, stubble. Same photographic look as the rest. No text.")
        result = gc.generate(prompt, out_dir=small, size="640x640", seed=int(opt("--seed", "7")), style=opt("--styl", "") or None, caller="velsen-tvar",
                             refs=[{"path": str(crop), "role": "geometry"}, {"path": str(face), "role": "subject"}], timeout=3000)[0]
        new = Image.open(result).convert("RGB").resize((size, size), Image.LANCZOS)
        yy, xx = np.mgrid[0:size, 0:size]
        edge = np.minimum.reduce([xx, size - 1 - xx, yy, size - 1 - yy]) / (size * 0.16)
        mask = Image.fromarray((np.clip(edge, 0, 1) ** 1.5 * 255).astype("uint8"), "L")
        im.paste(new, (x, y), mask)
        im.save(out)
        print(out)
    elif what == "pozadi":
        render, out = Path(sys.argv[2]), Path(sys.argv[3])
        out.mkdir(parents=True, exist_ok=True)
        seed = int(opt("--seed", "701"))
        only = [int(x) for x in opt("--jen", "1,2,3,4,5,6").split(",")]
        jobs = {}
        for n in only:
            g = out / f"_guide-{n}.png"
            Image.open(render / f"scena-{n}.png").convert("RGB").resize((560, 341), Image.LANCZOS).save(g)
            jobs[n] = gc.submit(BACK + BACKS[n], size="1024x624", seed=seed + n, refs=[{"path": str(g), "role": "geometry"}], caller="velsen-pozadi")
        for n, j in jobs.items():
            p = gc.download(gc.wait(j, timeout=1500), out)[0]
            p.replace(out / f"pozadi-{n}.png")
            print(out / f"pozadi-{n}.png")
    elif what == "studna":
        render, podklady, out = Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
        out.mkdir(parents=True, exist_ok=True)
        g = out / "predloha.png"
        guide(render, podklady).resize((300, 400), Image.LANCZOS).save(g)     # FLUX on 8 GB: the reference and the picture share the memory
        print("předloha", g)
        jobs = [gc.submit(STUDNA, size="704x928", seed=int(s), refs=[{"path": str(g), "role": "geometry"}], caller="velsen-studna") for s in opt("--seeds", "11").split(",")]
        for j in jobs:
            print(gc.download(gc.wait(j, timeout=3000), out))
    else:
        render, podklady, out = Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
        out.mkdir(parents=True, exist_ok=True)
        only = [int(x) for x in opt("--jen", "1,2,3,4,5,6").split(",")]
        base, style = int(opt("--seed", "501")), opt("--styl", "hist-akademismus")
        small = out / "_male"
        small.mkdir(exist_ok=True)
        jobs = {}
        for n in only:
            g = small / f"predloha-{n}.png"
            Image.open(render / f"scena-{n}.png").convert("RGB").resize((560, 341), Image.LANCZOS).save(g)     # 8 GB: two references at once do not fit next to other programs, the face comes in `tvar`
            jobs[n] = gc.submit(COMMON + FACE + SCENES[n], size="1024x624", seed=base + n, style=style, caller="velsen-sceny",
                                refs=[{"path": str(g), "role": "geometry"}])
        for n, j in jobs.items():
            for p in gc.download(gc.wait(j, timeout=3000), out):
                target = out / f"scena-{n}-s{base + n}.png"
                p.replace(target)
                print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
