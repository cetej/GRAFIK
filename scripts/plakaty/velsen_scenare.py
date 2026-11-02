# The five other scenes of "Who killed him?" in the style and with the victim of the accepted article picture (velsen_hero.py is scene 4). Local FLUX, one reference at most; on the page a scene is about 560 px wide, so 1024 x 672 is enough and fits when other programs share the graphics card.
#   python scripts/plakaty/velsen_scenare.py LIB 1,5,6 --seeds 501,502
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "shared")]
from ngm_shared import grafik_client as gc  # noqa: E402

LOOK = "A nineteenth-century history painting in the manner of Jean-Leon Gerome: precise natural drawing, sober natural colours, restrained light, nothing theatrical. "
RULES = ("Nobody looks at the camera. A real moment caught in motion, the figures overlapping, some cut by the edge of the frame. Correct human proportions and perspective. Ordinary lean tired men, plain used dirty gear, no gold, no ornament, no bodybuilders. "
         "No text, no chimneys, no glass, no lantern, no log walls, no planks on the houses. ")
FORT = "a Roman fort on the Dutch coast in the first century: long low barracks of smooth pale lime-plastered wattle with a dark timber frame and thatched roofs, an earth rampart faced with timber, mud"
VICTIM = "the man of <ref_image_0>: the same face, heavy jaw, deep-set eyes, thick dark brows, short black hair, stubble, a man past thirty, very tall and square-built, lean"
DRESS = "an off-white wool tunic to the knee with a soldier's belt, a dark red wool cloak, Roman caligae"
SOLDIERS = "Roman soldiers of the time of Tiberius in plain iron mail shirts over dull tunics, plain iron helmets with cheek pieces, hobnailed caligae, long flat oval shields, no plate armour, no band cuirass, no round shields"
FRISIANS = "bearded long-haired Germanic Frisians in undyed long-sleeved wool tunics, wool trousers and thick checked cloaks, no armour, no helmets, long narrow-headed spears and round wooden shields"
HOODED = "Roman soldiers off duty, not monks: each in a knee-length hooded wool travelling cloak of dull brown, the hood pulled over the face, bare muscular shins below the cloak, open-work hobnailed Roman caligae sandals, a leather soldier's belt where the cloak falls open"
WELL = "a low square well head of stacked squared oak beams, knee-high and one metre wide, black water deep inside, no stone, no crossbeam, no gallows, no roof, no well house"
SCENES = {
    1: (True, f"Grey dawn, the storming of {FORT}, smoke drifting from a burning thatched roof. Low viewpoint in the mud below the rampart. {FRISIANS} pour over the rampart and run at the defenders. In the middle {VICTIM}, in {DRESS}, no armour, no helmet, reels backwards with a long spear stuck in his side, mouth open, arms thrown out, his knees giving way. Behind him {SOLDIERS} fight back, one man down in the mud in the foreground."),
    2: (True, f"Night inside {FORT}, cold moonlight, a small clay oil lamp on the ground, the bare mast of a ship behind the roofs. Exactly three men, seen from low down and close. On the ground {WELL}. Two men in {HOODED} kneel on either side of it and with care let a dead man down into it feet first over the beams: {VICTIM}, dead, eyes shut, his head fallen to one side, limp and heavy, in {DRESS}, his legs already in the well head and bent at the knee, his body half out, his arms hanging. One man holds him from behind under the armpits, leaning back under the weight; the other holds his belt and looks back over his shoulder towards the dark buildings."),
    3: (True, f"Cold grey morning with pale fog inside {FORT}. The viewpoint is behind a rank of soldiers, whose backs and helmets fill the near left and right edges of the picture, out of focus. In the open muddy space beyond them two of the {SOLDIERS} force a prisoner down on his knees in the mud, one pulling his bound arms up behind him. The prisoner, {VICTIM}, in only a long ungirded off-white tunic, no belt, kneels sunk in the mud, bent forward, his head at the height of the belts of the men over him. Behind him, looking down at him, stands a lean hard old centurion, bareheaded and grey-haired, in mail with a harness of round silver medals on his chest, greaves and a dark red cloak, shouting, a twisted vine stick no longer than his arm raised in his hand. More soldiers in ranks fade in the fog."),
    5: (True, f"Blue dusk, sea mist over a tidal marsh, reeds, black mud, shallow water, a thin line of warm light on the horizon, the low dark line of a timber fort far off. {FRISIANS} drag a bound Roman captive through the mud by a rope round his neck: {VICTIM}, in a torn off-white tunic, stumbling, falling on one knee, head down, his face twisted with pain. One Frisian pulls the rope ahead of him, one walks behind with a spear, one has the captive's dark red cloak over his arm, two more come along behind, small in the mist."),
    6: (False, f"Violet twilight in the demolished burned-out ruin of {FORT}: charred posts, ash, heaps of burnt clay, thin smoke. On the ground {WELL}. Three men in plain undyed wool tunics fill the well and work without looking up: one kneels at the rim and tips in a jagged half-moon fragment of a shattered quern, the thick round stone snapped in two through its centre hole, rough grey porous lava with a raw broken edge, not a whole disc; one drives a long peeled wooden pole down into the well with both hands; one empties a basket of burnt clay lumps. An old grey-bearded man in a plain wool tunic and cloak stands at the rim, head bowed, eyes shut, murmuring, and pours a little from a small dark clay jar. Under the black water in the well a dark red cloth can just be seen. No cubes, no bricks, no raised arms."),
}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    lib, names = Path(sys.argv[1]), [int(n) for n in sys.argv[2].split(",")]
    seeds = [int(s) for s in sys.argv[sys.argv.index("--seeds") + 1].split(",")]
    out = lib / "scenare"
    out.mkdir(parents=True, exist_ok=True)
    face = lib / "hero/_muz-male.png"
    for n in names:
        needs_face, body = SCENES[n]
        for seed in seeds:     # one at a time: a long queue outlasts the client's wait
            refs = [{"path": str(face), "role": "subject"}] if needs_face else []
            target = out / f"s{n}-{seed}.png"
            if target.exists():
                continue
            size = sys.argv[sys.argv.index("--size") + 1] if "--size" in sys.argv else "1024x672"
            for attempt in range(40):      # other programs may hold the graphics card for a while; try again, do not give up the batch
                try:
                    job = gc.submit(LOOK + RULES + body, size=size, seed=seed, refs=refs, caller="velsen-scenare")
                    gc.download(gc.wait(job, timeout=1500), out)[0].replace(target)
                    break
                except gc.EngineUnavailable as e:
                    print(f"{target.name}: pokus {attempt + 1}: {str(e)[:90]}", flush=True)
                    time.sleep(180)
            print(target.name, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
