# Runs a Blender script of the Velsen infographics under the machine-wide heavy lock.
#   python scripts/3d/velsen_studna_run.py velsen_studna.py OUT_DIR [--w 900 --h 1200 --samples 48]
#   python scripts/3d/velsen_studna_run.py velsen_sceny.py OUT_DIR [--jen 1,2]
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "shared")]
from engine.config import find_blender  # noqa: E402
from ngm_shared.heavy_lock import heavy  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
script = ROOT / "scripts/3d" / sys.argv[1]
with heavy("blender", owner="grafik", caller=script.stem, wait_s=900):
    run = subprocess.run([find_blender(), "-b", "--factory-startup", "--python-exit-code", "1", "-P", str(script), "--", *sys.argv[2:]],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1500)
print(run.stdout[-700:])
if run.returncode:
    print(run.stderr[-1800:])
raise SystemExit(run.returncode)
