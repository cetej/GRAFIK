# The cloak drifting behind the man in the well, from local FLUX so it matches his painted figure; a 3D sheet came out as a red egg.
#   python scripts/plakaty/velsen_plast.py LIB --seeds 401,402,403,404
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "shared"), str(Path(__file__).parent)]
from ngm_shared import grafik_client as gc  # noqa: E402
from sazba import cutout  # noqa: E402

PROMPT = ("A single heavy dark red wool cloak, crumpled and bunched, drifting upward in a large soft mass with deep natural folds, no person in it, seen from the front. Muted dark crimson, used rough wool, soft light from the upper left. "
          "A naturalistic painting with precise drawing. The whole cloak in the frame on a plain pale grey wall, nothing else, no text.")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    lib = Path(sys.argv[1])
    seeds = [int(s) for s in sys.argv[sys.argv.index("--seeds") + 1].split(",")]
    out = lib / "skupiny"
    jobs = {seed: gc.submit(PROMPT, size="768x768", seed=seed, caller="velsen-plast") for seed in seeds}
    for seed, j in jobs.items():
        target = out / f"plast-s{seed}.png"
        gc.download(gc.wait(j, timeout=1500), out)[0].replace(target)
        cutout(target, out / f"plast-s{seed}-cut.png", shadow=0.0, erode=1)
        print(target.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
