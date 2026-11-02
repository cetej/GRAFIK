# Groups of people for the Velsen scenes: one studio picture from local FLUX per group, so the men really hold each other. The operator accepted this look ("Ty postavy jsou prima").
#   python scripts/plakaty/velsen_skupiny.py OUT g3,centurion --seeds 61,62,63
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "shared")]
from ngm_shared import grafik_client as gc  # noqa: E402

STUDIO = ("Plain flat light grey studio background, seamless floor, even soft light, soft shadow on the floor under the feet, nothing else in the picture. Everybody whole from head to feet with space around. "
          "A documentary photograph of ordinary tired men in a sober archaeological reconstruction, northern Europe in cold weather. Everything plain, used, dull and dirty: no gold, no polish, no ornament, no bodybuilders. No text. ")
# No swords, daggers or crest in the prompt: the generator draws long medieval swords and turns the crest round, so they are pasted in as exact models (scripts/3d/velsen_gladius.py, velsen_dyka.py).
NOARMS = "Nothing at the belt: no sword, no dagger, no scabbard, no sheath, no weapons at all"
CALIGA = "wearing open-work hobnailed leather caligae as in the reference, sandals of cut straps laced up the ankle with bare toes, no boots, no socks, not barefoot"
BELT = "one narrow leather belt with a row of plain rectangular silver-plated plates and a small brass buckle"
# Lower Rhine about AD 28. Dress from the book (Driessen, van Driel-Murray 2026): fig. 2.10 and p. 42, 155 "off-duty dress"; caliga p. 57; gear: docs/spikes/2026-11-01-velsen.md
VICTIM = "a very tall big-boned square-built man looking over thirty, wide square shoulders, square heavy jaw, long strong limbs, lean with a flat belly, not fat, worn out by service, thick dark brows, tired dark eyes with bags, weathered skin, short black hair with a ragged fringe, stubble"
TUNIC = "a wide T-shaped undyed off-white wool tunic with wide loose sleeves to the elbow, reaching the knee"
OFFDUTY = (f"{TUNIC}, hitched over {BELT} so that the cloth blouses above it, a thick dark brown wool cloak wrapped round his shoulders and neck, {CALIGA}")
LEG = (f"Roman legionary as in the reference, an ordinary thin tired man with short hair and stubble. A cuirass of plain dull grey iron bands closed down the front, ending at the waist, the shoulders fully covered by curved iron shoulder bands. Under it a dull red wool tunic with sleeves to the elbow, reaching the knee, a wool scarf at the neck, a dark brown wool cloak thrown back over the shoulders. "
       "Plain dull iron helmet with hinged cheek pieces and a broad neck guard, no crest. One narrow belt, no hanging straps, no strips, no skirt. {CALIGA}. {NOARMS}")
# The centurion and the legionary after the two reference pictures the operator chose (Legio X Fretensis reenactors, Pinterest, licence unknown: only a reference).
CENT = (f"Exactly the armour and gear of the man in <ref_image_0>: the cuirass of bronze scales, the harness of dark straps with nine round silver medals (phalerae) on the chest, the fringed strips at the waist, the bronze greaves, the iron and bronze helmet with cheek pieces, and above it the TRANSVERSE crest of black horsehair on a bronze arc, running sideways from ear to ear so that from the front it is a wide half-circle. A dark red wool cloak over the left shoulder, a pale wool scarf at the neck. "
        f"But another man: lean hard old soldier of about fifty, hollow cheeks, deep lines, thin mouth, grey stubble. His right hand holds a thin straight vine stick no longer than his arm, pointing down. {CALIGA}. {NOARMS}. Worn, used, dull metal, real and dirty")
CENT3 = (f"Exactly the armour and gear of the man in <ref_image_0>: a shirt of dull iron mail with fringed shoulders, over it a harness of crossed dark red straps with seven round worn silver medals (phalerae), two twisted metal collars on the chest, a row of strips with a fringe at the waist, plain silver-grey greaves on the shins, a dark red wool cloak behind, a dark red tunic. The iron helmet with cheek pieces and neck guard, and above it the TRANSVERSE crest of pale horsehair on a metal arc, running sideways from ear to ear so that from the front it is a wide half-circle. His left hip carries a short sword with a ball pommel, its hilt high at the lowest ribs, his right hip a short dagger. "
         f"In his right hand a thin twisted natural vine stick reaching the ground. {CALIGA}. A lean hard old soldier of about fifty, hollow cheeks, deep lines, thin mouth, grey stubble, not fat. Worn, used, real and dirty")
FRISIAN = "bearded long-haired Germanic Frisian of the first century: long-sleeved undyed wool tunic with no armour, no mail, wool trousers, thick checked wool cloak pinned at the shoulder, simple leather shoes, skin weathered by sea wind"
# name: size, reference in ../postavy or ../podklady (only the dress or the armour), text
GROUPS = {
    "sedici": ("640x960", "muz_barva", f"A photograph of a real person, not a drawing: exactly the pose, the clothes and the things of the man in <ref_image_0>, seen from the same side. A dead man sits on the floor with knees drawn up to his chest, both hands round his shins, head bowed to his right, eyes shut. {VICTIM}. A pale off-white wool tunic, a big dark red wool cloak bunched behind his left shoulder and round his neck, fastened with a small bronze brooch, a narrow belt of plain silver plates, an iron ring on his hand. On his left foot one open-work leather caliga, the right foot bare. Natural dull colours, nothing else in the picture."),
    "g3": ("1024x672", "op_legionar", f"Three men close together in a row, seen from the front. In the middle {VICTIM} kneels upright on both knees facing us, head up, hands tied behind his back, stripped of belt and cloak, only {TUNIC}, hanging loose. Each side of him stands the same kind of soldier: {LEG}, each of the two grips his upper arm firmly with one hand and pushes him down, the other arm hangs free, they look down at him."),
    "centurion": ("640x960", "op_centurio", f"One man standing, seen from the front, a real person. {CENT}."),
    "centurion3": ("640x960", "op_centurio3", f"A photograph of a real person, not a drawing, one man standing, seen from the front, natural dull colours. {CENT3}."),
    "rady": ("1024x672", "op_legionar", f"A row of eight Roman soldiers standing to attention side by side in two ranks seen from the front, most in plain shirts of dull iron mail, some in iron band cuirasses. {LEG}. Each holds a tall curved rectangular shield of plain dirty leather-covered wood resting on the ground and a javelin."),
    "g1": ("1024x672", "op_legionar", f"A fight, seen from the side. On the right {VICTIM}, bareheaded, in the same gear as this soldier: {LEG}, reels back wounded with his arms flung out and his head thrown back. On the left two of them, each a {FRISIAN}, lunge at him with long narrow-headed spears held low in both hands, one also has a round wooden shield with an iron boss."),
    "g2": ("768x1152", "pokus_muz", f"Two men in long dark hooded wool cloaks over plain wool tunics, no armour, faces hidden deep in the hoods, bent forward straining, hold between them under the armpits the sagging dead body of {VICTIM}: chin fallen on his chest, head lolling to one side, eyes shut, mouth slack, knees buckled, arms dangling, a dead weight dragged along with his toes on the floor, in {OFFDUTY}. {NOARMS}."),
    "g4": ("1024x672", "pokus_muz", f"A plain old wooden crate at knee height. {VICTIM}, in {OFFDUTY}, seen from the side, is forced to bend forward at the hips over the crate, his chest pressed down on top of it, legs straight behind it, his head turned to us grimacing with pain. Three furious Roman soldiers, ordinary thin men, each in {TUNIC} and a belt, no armour, no helmets, {CALIGA}, hold him down: one presses his neck down with both hands, one twists his arm up behind his back, the third stands behind his hips with his right arm raised high and the fist clenched, empty. {NOARMS}."),
    "g5": ("1152x768", None, f"In the middle {VICTIM} kneels on both knees facing us, hands bound in front of him, only {TUNIC}, bareheaded. Around him stand three men, each a {FRISIAN}: one has a folded dark brown cloak over his left arm and his right fist clenched, empty, at his hip, one leans on a long spear, one looks down with folded arms."),
    "g6": ("1152x768", None, f"Three men, each a {FRISIAN} without the cloak, in plain wool, stand side-on and haul on two thick hemp ropes that run to the right, leaning back with feet braced. In front of them an old grey-bearded man in a long undyed wool robe, no armour, faces the same way, both arms raised with open palms, head lifted, solemn."),
}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    out, names = Path(sys.argv[1]), sys.argv[2].split(",")
    seeds = [int(s) for s in sys.argv[sys.argv.index("--seeds") + 1].split(",")]
    out.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for name in names:
        size, ref, text = GROUPS[name]
        refs = []
        if ref:  # 8 GB: the reference stays small next to the picture
            small = out / f"_{ref}-male.png"
            im = Image.open(next(f for d in ("postavy", "podklady", "centurio") for f in (out.parent / d).glob(f"{ref}.*") if f.suffix != ".json")).convert("RGB")
            im.thumbnail((270, 360))
            im.save(small)
            refs = [{"path": str(small), "role": "subject"}]
            if "<ref_image_0>" not in text:
                text = f"Dress and gear as in <ref_image_0>, not its pose or its face, in natural colours. {text}"
        for seed in seeds:
            jobs[name, seed] = gc.submit(STUDIO + text, size=size, seed=seed, refs=refs, caller="velsen-skupiny")
    for (name, seed), j in jobs.items():
        p = gc.download(gc.wait(j, timeout=1500), out)[0]
        target = out / f"{name}-s{seed}.png"
        p.replace(target)
        print(target.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
