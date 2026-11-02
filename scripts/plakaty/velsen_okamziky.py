# The six Velsen scenes as moments: one whole picture each, from local FLUX, written as what is happening at that second (book ch. 11), not people lined up facing us.
# The operator on the cut-out groups: "zamrzlá scéna z ochotnického divadla"; a kneeling man as tall as the standing ones.
#   python scripts/plakaty/velsen_okamziky.py OUT 3,2 --seeds 201,202 [--styl malba|foto]
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "shared")]
from ngm_shared import grafik_client as gc  # noqa: E402

LOOK = {
    "malba": "A nineteenth-century history painting in the manner of Jean-Leon Gerome: precise natural drawing, sober natural colours, soft air, restrained light, nothing theatrical. ",
    "foto": "A still from a serious historical film, shot on location with natural light, documentary realism, muted natural colours, sharp detail, motion in the figures. ",
}
RULES = ("Nobody looks at the camera. The men are busy with what is happening, seen at an angle, overlapping each other, at different distances, some cut by the edge of the frame, a real moment caught in motion, not a line of people on a stage. Correct human proportions and perspective. "
         "Ordinary tired men in plain, used, dirty gear, no gold, no ornament, no bodybuilders. No drawn swords, no long swords, no daggers unless the text names one. Buildings have smooth pale plastered walls with a dark timber frame and thatched roofs, never log cabins or planks. No text. ")
LEG = ("Roman legionaries of the time of Tiberius: plain dull iron band cuirasses ending at the waist with iron shoulder bands, dull red wool tunics to the knee, dark brown wool cloaks and scarves, plain iron helmets with cheek pieces and neck guards, open-work hobnailed caligae")
CENT = ("the centurion of <ref_image_0> as a real man, lean, hard and old, in the same mail, the same harness of round silver medals on the chest, the same greaves and dark red cloak, and on his helmet the same crest running sideways across the head from ear to ear, a wide half-circle seen from the front, in his hand a twisted vine stick no longer than his arm")
VICTIM = "a very tall big-boned square-built man looking over thirty, lean and not fat, heavy jaw, thick dark brows, short black hair, stubble"
DRESS = "a wide undyed off-white wool tunic to the knee, a narrow belt with plain silver plates, a thick dark brown wool cloak, open-work caligae"
FRISIANS = "bearded long-haired Germanic Frisians in undyed long-sleeved wool tunics, wool trousers and thick checked cloaks, no armour, no mail, long narrow-headed spears and round wooden shields"
FORT = "a small Roman timber fort on the Dutch coast: plastered wattle-and-daub barracks with thatched roofs, an earth and timber rampart, mud"
# number: reference, text
SCENES = {
    1: ("op_legionar", f"The soldiers' armour as in <ref_image_0>, not its pose. Grey dawn, the storming of {FORT}, smoke drifting from a burning thatched roof. Low viewpoint in the mud below the rampart. {FRISIANS} pour over the wattle breastwork and run at the defenders. In the middle {VICTIM}, one of the {LEG}, reels backwards with a spear point in him, his arms thrown out, his helmet falling off, a comrade beside him turning to catch him, others fighting with shields and javelins behind them, one man down in the mud in the foreground."),
    2: (None, f"Night in {FORT}, cold moonlight, one small oil lamp on the ground. Exactly three men in the picture. In the middle a square timber well head with two corner posts. A dead man hangs upright in the well, feet first: he is sunk in the shaft to his waist, only his head, shoulders and chest above the kerb, his legs out of sight in the well. He is {VICTIM}, dead, in {DRESS}, chin fallen on his chest, eyes shut, arms hanging. On either side of the kerb stands a man in a long dark hooded wool cloak, face hidden in the hood, bending over and straining, holding him under the armpit, letting him down. One of the two looks back over his shoulder towards the dark buildings. The mast of a ship behind the roofs."),
    3: ("op_centurio3", f"Cold grey morning with pale fog inside {FORT}. The viewpoint is behind a rank of soldiers: their backs and helmets fill the near left and right edges of the picture, out of focus. In the open muddy space beyond them, two of the {LEG} force a prisoner down on his knees in the mud, one pulls his bound arms up behind him, one presses his neck down. The prisoner, {VICTIM}, in only a long ungirded off-white tunic, no belt, kneels sunk in the mud, bent forward: his head is only at the height of the belts of the men standing over him. Behind the prisoner, facing us and looking down at him, stands {CENT}, shouting, his stick raised. Beyond, more soldiers in ranks fade in the fog, some looking away."),
    4: (None, f"Night in a narrow alley between plastered barracks, one torch on the wall throwing hard orange light and black shadows. Soldiers in plain off-white tunics, no armour, no helmets, furious, hold down {VICTIM}, in {DRESS}, forcing him to bend forward over a wooden crate, chest on the crate: one presses his neck down with both hands, one twists his arm up his back, a third behind his hips raises his right fist high, empty. A fourth keeps watch at the mouth of the alley with his back to us. A broken vine stick and an iron helmet in the mud."),
    5: (None, f"Blue dusk, sea mist over a tidal marsh, reeds, black mud, shallow water, a thin line of warm light on the horizon, the low dark line of a timber fort far off. {FRISIANS} drag a bound Roman captive through the mud by a rope round his neck: {VICTIM}, in a torn off-white tunic, stumbling, falling on one knee, head down. One Frisian pulls the rope ahead of him, one walks behind with a spear, one has the captive's dark brown cloak over his arm, two more come along behind, small in the mist."),
    6: (None, f"Violet twilight in the burned-out ruin of {FORT}: charred posts, ash, thin smoke. Around a square timber well head with two corner posts, men in plain wool are closing the well: two lean back paying out ropes that go down into the shaft, one heaves a broken dark basalt millstone over the edge with both hands, another comes carrying a heavy fragment against his chest, a long wooden stake lies ready on the kerb. An old grey-bearded man in an undyed wool robe stands at the head of the well with both arms raised, chanting. Heaps of broken millstones and burnt clay on the ground."),
}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    out, names = Path(sys.argv[1]), [int(n) for n in sys.argv[2].split(",")]
    seeds = [int(s) for s in sys.argv[sys.argv.index("--seeds") + 1].split(",")]
    look = sys.argv[sys.argv.index("--styl") + 1] if "--styl" in sys.argv else "malba"
    out.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for n in names:
        ref, text = SCENES[n]
        refs = []
        if ref:     # 8 GB: the reference stays small next to the picture
            small = out / f"_{ref}-male.png"
            im = Image.open(next(f for f in out.parent.glob(f"centurio/{ref}.*") if f.suffix != ".json")).convert("RGB")
            im.thumbnail((270, 360))
            im.save(small)
            refs = [{"path": str(small), "role": "subject"}]
        for seed in seeds:
            jobs[n, seed] = gc.submit(LOOK[look] + RULES + text, size="1024x624" if refs else "1152x704", seed=seed, refs=refs, caller="velsen-okamziky")
    for (n, seed), j in jobs.items():
        p = gc.download(gc.wait(j, timeout=1500), out)[0]
        target = out / f"s{n}-{look}-{seed}.png"
        p.replace(target)
        print(target.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
