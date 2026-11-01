# Renders Tesla's machines one by one under the heavy lock, free:
#   python scripts/3d/tesla_render.py OUT_DIR motor civka vez turbina [--samples 96] [--res W H] [--gpu]
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "shared")]

TIMEOUT_S = 1800
SHOTS = ("motor", "civka", "civka-bez", "vez", "vez-nad", "hala", "turbina", "elektrarna", "transformator", "prijimac", "lod", "trubice", "trubice2")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from engine.config import find_blender
    from ngm_shared.heavy_lock import heavy

    out = sys.argv[1]
    shots = [a for a in sys.argv[2:] if a in SHOTS]
    rest = [a for a in sys.argv[2:] if a not in SHOTS]
    if not shots:
        print("no known shot in", rest)
        return 1
    blender = find_blender()
    for shot in shots:
        with heavy("blender", owner="grafik", caller="plakat", wait_s=1200):
            run = subprocess.run([blender, "-b", "--factory-startup", "-P", str(Path(__file__).with_name("tesla_stroje.py")), "--", shot, out, *rest],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_S)
        lines = [line for line in run.stdout.splitlines() if line.startswith("STATS") or "Error" in line or "Traceback" in line]
        print(shot, run.returncode, *lines, sep=" | ")
        if run.returncode or not any(line.startswith("STATS") for line in lines):
            print(run.stdout[-1500:], run.stderr[-1500:])
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
