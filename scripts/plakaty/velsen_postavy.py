# Figures for the Velsen scenes: a posed figure from local FLUX (reference from Pinterest, only a reference), then a paid 3D model (Hunyuan 3.1 Pro, 0.375 USD each) for finer detail in the scene.
#   python scripts/plakaty/velsen_postavy.py refs OUT                     download the chosen pins, record them in the reference library
#   python scripts/plakaty/velsen_postavy.py obraz OUT role[,role] [--seed 1] [--ref FILE]
#   python scripts/plakaty/velsen_postavy.py model OUT role[,role] [--obraz FILE] --confirm-cost
import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "shared")]
from ngm_shared import grafik_client as gc  # noqa: E402

PINS = {
    "legionar": ("https://cz.pinterest.com/pin/4593460587262752640/", "https://i.pinimg.com/originals/05/93/70/05937048092ad4cdb8942685ebf99ddb.jpg", "Legionář v kroužkové zbroji, reenaktor"),
    "segmentata": ("https://cz.pinterest.com/pin/1087971222514017816/", "https://i.pinimg.com/originals/3b/9c/13/3b9c130ffbffa114881458d19b48dc58.png", "Legionář v lorica segmentata"),
    "legionar2": ("https://cz.pinterest.com/pin/4610208389303582592/", "https://i.pinimg.com/originals/e1/ab/9d/e1ab9debfa04754910e1214a18b631be.jpg", "Lorica hamata, reenaktor"),
    "germani": ("https://cz.pinterest.com/pin/680043612466453831/", "https://i.pinimg.com/originals/68/fe/e3/68fee3db774c8ef8f354f907b40a9d36.jpg", "Germánský bojovník s pláštěm a štítem"),
    "german2": ("https://cz.pinterest.com/pin/761741724498535697/", "https://i.pinimg.com/originals/1c/de/4e/1cde4e6142b0600df2f82f8a0078ad6c.jpg", "Germán, kostkovaný plášť, oválný štít"),
    "val": ("https://cz.pinterest.com/pin/635711303624537626/", "https://i.pinimg.com/originals/61/65/de/6165defb201f39846b2999e42b70171f.jpg", "Dřevozemní val, kresba"),
    "brana": ("https://cz.pinterest.com/pin/769130442588720159/", "https://i.pinimg.com/originals/ec/59/e3/ec59e3fc290ed67505f9febca40e55f1.jpg", "Dřevěná brána římské pevnosti, kresba"),
}

STUDIO = ("The whole figure from head to feet with space around it, centred, plain flat light grey studio background, even soft light, no shadow on the wall, nothing else in the picture. "
          "A real person in a historically exact reconstruction, sharp detail of cloth, leather, iron and mail. No text. ")
TUNIC = "knee-length undyed off-white wool tunic with short sleeves, bare legs"
MAIL = ("Roman legionary of about AD 20: long mail shirt of riveted iron rings with doubled shoulders over a red wool tunic, iron Imperial Gallic helmet with cheek pieces and neck guard, "
        "two crossed belts with silver plates, dagger in a decorated sheath at the left hip, sword at the right hip, hobnailed caligae sandals")

ROLES = {
    "kneeling": (None, f"A very tall young man kneels upright on both knees, seen from the front, torso straight, head raised, hands tied behind his back. Torn {TUNIC}, no belt, barefoot, short black hair. Roman soldier stripped of his gear."),
    "soldier": ("legionar", f"{MAIL}. Stands facing the camera, weight on both feet, right arm reaching forward and slightly down as if gripping someone by the arm, left arm at his side, stern face."),
    "fall": ("segmentata", "A huge heavily built Roman legionary of about AD 20, worn out, over thirty, reels backwards wounded and off balance: torso leaning back, left leg stepping back, right knee bent, both arms flung out to the sides, head thrown back, mouth open, bareheaded, short black hair. Banded iron plate armour, early lorica segmentata with bronze fittings, red tunic, belts with silver plates, dagger at the hip, hobnailed sandals."),
    "frisian_spear": ("germani", "A bearded long-haired Germanic Frisian warrior of the first century lunges forward, side-on view facing right, a long spear held low in both hands at hip height, thrusting to the right, front knee bent, back leg straight. Shaggy wool cloak pinned at the shoulder, long-sleeved wool tunic, wool trousers, leather shoes."),
    "frisian_stand": ("german2", "A bearded long-haired Germanic Frisian tribesman of the first century stands facing the camera, slightly turned, his right hand holds a short Roman dagger pointing down, over his left forearm hangs a folded dark red cloak. Shaggy wool cloak pinned at the shoulder, long-sleeved wool tunic, wool trousers, leather shoes."),
    "hooded": (None, "A man in a long dark hooded wool cloak, his face hidden deep in the hood, side-on view facing right, bends forward at the waist with knees bent, both arms reaching forward and down as if gripping someone under the arm and lowering him."),
    "seated": ("muz", "A huge heavily built Roman soldier, dead, over thirty, seen from the front, sits slumped on the ground exactly in the pose of the man in <ref_image_0>: knees drawn up, arms hanging over the shins, head hanging forward. Off-white wool tunic, dark red wool cloak bunched behind his shoulders, belt with silver plates, a silver dagger sheath at his hip, one leather sandal on his left foot, right foot bare, short black hair."),
    "bent": (None, "A huge heavily built man over thirty in an off-white knee-length wool tunic and a silver-plated belt, three-quarter view from the front, is forced to bend forward sharply at the hips, torso horizontal, both hands flat in front of him at waist height as if pressed on a crate, feet apart, head raised, face turned to the camera, grimacing with pain, short black hair."),
    "grip": (None, "A furious Roman soldier in a plain off-white wool tunic and belt, no armour, no helmet, side-on view facing right, lunges forward, leaning in, both arms reaching forward and down with clenched hands gripping, feet wide apart, sandals."),
    "dagger": (None, "A furious Roman soldier in a plain off-white wool tunic and belt, no armour, no helmet, seen from the front, his right arm raised high holding a short leaf-shaped dagger point down, his left hand reaching forward and down, feet apart, sandals."),
    "rope_man": (None, "A bearded man in a plain brown wool tunic and belt, no armour, side-on view facing right, leans back hauling on a rope, both hands holding the rope in front of him at waist height, feet braced apart, leather shoes."),
    "elder": (None, "An old grey-bearded man in a long undyed wool robe and cloak, seen from the front, both arms raised with open palms, head lifted, solemn."),
    "centurion": ("legionar2", f"Roman centurion of about AD 20: {MAIL}, transverse red horsehair crest across the helmet, dark red wool cloak on the shoulders. Stands three-quarter view, both hands hold a straight knotted vine stick diagonally across his body, looks down to his right."),
}


def small_ref(path: Path, out: Path) -> Path:
    """8 GB: the reference must stay small next to the picture."""
    im = Image.open(path).convert("RGB")
    im.thumbnail((270, 360))
    im.save(out)
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    what, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)

    def opt(name, default=None):
        return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default

    if what == "refs":
        for name, (pin, url, title) in PINS.items():
            target = out / f"{name}{Path(url).suffix}"
            if not target.exists():
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                target.write_bytes(urllib.request.urlopen(req, timeout=40).read())
            print(name, target.stat().st_size, gc.add_ref(url, page_url=pin, title=title, license="neznámá, jen předloha").get("id"))
    elif what == "obraz":
        seed = int(opt("--seed", "1"))
        jobs = {}
        for role in sys.argv[3].split(","):
            ref, text = ROLES[role]
            refs = []
            if ref:
                src = next(out.glob(f"{ref}.*"))
                refs = [{"path": str(small_ref(src, out / f"_{ref}-male.png")), "role": "subject"}]
                if "<ref_image_0>" not in text:
                    text = f"The costume and gear of the man in <ref_image_0>, correct them where the text differs. {text}"
            jobs[role] = gc.submit(STUDIO + text, size="640x960" if refs else "768x1152", seed=seed, refs=refs, caller="velsen-postavy")
        for role, j in jobs.items():
            p = gc.download(gc.wait(j, timeout=1500), out)[0]
            target = out / f"{role}-s{seed}.png"
            p.replace(target)
            print(target)
    elif what == "model":
        for role in sys.argv[3].split(","):
            image = Path(opt("--obraz") or out / f"{role}.png")
            m = gc.model3d(refs=[{"path": str(image), "view": "front", "source": "lokální FLUX podle předlohy z Pinterestu"}], title=f"Velsen {role}", method="fal-hunyuan31pro",
                           origin="scripts/plakaty/velsen_postavy.py", confirm_cost="--confirm-cost" in sys.argv, timeout=1500)
            print(role, json.dumps({k: m.get(k) for k in ("model_id", "version", "usd", "cost_usd", "files")}, ensure_ascii=False)[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
