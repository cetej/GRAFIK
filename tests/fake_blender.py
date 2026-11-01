"""Stands in for `blender -b --factory-startup -P <script> -- args` in the 3D tests.

render_views.py: writes 8 small RGBA PNGs (or one with --camera / --scene) and a STATS line; stretch.py: copies the GLB
and prints BBOX; decimate.py: copies the GLB and prints STATS and VIEWER.
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

CUTS = ("arkady", "vyrez", "ochoz", "schodiste", "sachty", "otvory", "dutina")
STATS = {"verts": 1234, "faces": 2000, "objects": 1, "bbox": [4.7, 1.7, 1.5], "blender": "fake 0.0"}


def view(path):
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    if mode != "empty":
        im.paste((200, 200, 200, 255), (16, 16, 48, 48))
    im.save(path, "PNG")


if script == "lod_parts.py":
    out, spec = Path(args[0]), json.loads(Path(args[1]).read_text(encoding="utf-8"))
    out.write_bytes(b"glTF\x02\x00\x00\x00" + b"\x00" * 64)
    names = [p["nazev"] for p in spec["dily"] if p["typ"] not in CUTS]
    Path(f"{out}.dily.json").write_text(json.dumps({"dily": {n: {"material": "kamen", "bbox": [[0, 0, 0], [1, 1, 1]]} for n in names},
                                                    "bez_kontaktu": []}), encoding="utf-8")
    sys.exit(0)
if script == "render_parts.py":
    spec, out, req = json.loads(Path(args[0]).read_text(encoding="utf-8")), Path(args[1]), json.loads(args[2])
    names = [p["nazev"] for p in spec["dily"] if p["typ"] not in CUTS]
    view(out / "obraz.png")
    layers = {}
    if req.get("vrstvy"):
        layers = req.get("skupiny") or {n: [n] for n in names}
        for name in layers:
            view(out / f"vrstva-{name}.png")
    (out / "body.json").write_text(json.dumps({"pohled": req["pohled"], "res": req["res"], "points": {n: [10, 10] for n in names},
                                               "viditelne": names, "vrstvy": layers, "zarizeni": "CPU"}), encoding="utf-8")
    print("STATS " + json.dumps({"parts": len(names), "device": "CPU"}))
    sys.exit(0)
if script == "render_views.py" and "--scene" in args:
    spec = json.loads(Path(args[args.index("--scene") + 1]).read_text(encoding="utf-8"))
    for o in spec["objects"]:
        if o["kind"] == "glb" and not Path(o["glb"]).read_bytes().startswith(b"glTF"):
            print("STATS " + json.dumps({"verts": 0, "faces": 0}))
            sys.exit(3)
    print("STATS " + json.dumps({**STATS, "objects": len(spec["objects"])}))
    view(Path(args[args.index("--scene") + 2]))
    print("VIEW camera")
    sys.exit(0)
if script in ("render_views.py", "decimate.py"):
    glb, out = Path(args[0]), Path(args[1])
    if not glb.read_bytes().startswith(b"glTF"):
        print("STATS " + json.dumps({"verts": 0, "faces": 0}))
        sys.exit(3)
    print("STATS " + json.dumps(STATS))
if script == "decimate.py":
    shutil.copy(args[0], args[1])
    print("VIEWER " + json.dumps({"triangles": 2000, "ratio": 1.0}))
elif script == "render_views.py" and "--camera" in args:
    json.loads(args[args.index("--camera") + 1])
    view(out)
    print("VIEW camera")
elif script == "render_views.py":
    for az in range(0, 360, 45):
        view(out / f"az{az:03d}.png")
        print(f"VIEW az{az:03d}")
elif script == "stretch.py":
    shutil.copy(args[0], args[1])
    print("BBOX " + json.dumps([float(args[2]), float(args[3]), float(args[4])]))
