"""Stands in for `blender -b --factory-startup -P <script> -- args` in the 3D tests.

render_views.py: writes 8 small RGBA PNGs and a STATS line; stretch.py: copies the GLB and prints BBOX.
FAKE_BLENDER_MODE=empty renders transparent views, =crash exits 1 with a stderr message,
=slow sleeps past the time limit. FAKE_BLENDER_TRACE=<file> appends one line per call
(the GPU lock state at that moment), so tests can see the lock was held.
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

from PIL import Image

script, args = Path(sys.argv[1]).name, sys.argv[sys.argv.index("--") + 1:]
mode = os.environ.get("FAKE_BLENDER_MODE", "")
trace = os.environ.get("FAKE_BLENDER_TRACE")
if trace:
    lock = Path(os.environ.get("FAKE_BLENDER_LOCK", ""))
    with open(trace, "a", encoding="utf-8") as f:
        f.write(json.dumps({"script": script, "args": args,
                            "lock": lock.read_text(encoding="utf-8") if lock.is_file() else None}) + "\n")
if mode == "crash":
    print("Error: Python: Traceback … RuntimeError: GLB import failed", file=sys.stderr)
    sys.exit(1)
if mode == "slow":
    time.sleep(30)

if script == "render_views.py":
    glb, out = Path(args[0]), Path(args[1])
    if not glb.read_bytes().startswith(b"glTF"):
        print("STATS " + json.dumps({"verts": 0, "faces": 0}))
        sys.exit(3)
    print("STATS " + json.dumps({"verts": 1234, "faces": 2000, "objects": 1, "bbox": [4.7, 1.7, 1.5],
                                 "blender": "fake 0.0"}))
    for az in range(0, 360, 45):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        if mode != "empty":
            im.paste((200, 200, 200, 255), (16, 16, 48, 48))
        im.save(out / f"az{az:03d}.png")
        print(f"VIEW az{az:03d}")
elif script == "stretch.py":
    shutil.copy(args[0], args[1])
    print("BBOX " + json.dumps([float(args[2]), float(args[3]), float(args[4])]))
