# Fit a GLB to real dimensions (free; engine/models3d.py, from scripts/3d/stretch_glb.py):
#   blender -b --factory-startup -P engine/blender/stretch.py -- in.glb out.glb LENGTH WIDTH HEIGHT PART
# PART: middle  uniform scale to the height, then only the middle of the long axis is lengthened
#               (both ends, 22 % each, keep their shape so wheels stay round)
#       end-max / end-min  only the last 35 % at the +/- end of the long axis is lengthened
#               (the +X end faces the 0° view, the -X end the 180° view; +Y 90°, -Y 270°)
#       all     every axis scaled to its dimension on its own
# Prints `BBOX {json}` with the resulting size.
import json
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
src, dst, L, W, H, part = a[0], a[1], float(a[2]), float(a[3]), float(a[4]), a[5]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
for o in objs:  # bake transforms so vertex coordinates are world coordinates
    o.data.transform(o.matrix_world)
    o.matrix_world.identity()
pts = [v.co for o in objs for v in o.data.vertices]
lo = Vector([min(p[i] for p in pts) for i in range(3)])
hi = Vector([max(p[i] for p in pts) for i in range(3)])
size = hi - lo
up = 2
long_ax = max((0, 1), key=lambda i: size[i])
wide_ax = 1 - long_ax
s = H / size[up]
cur_len = size[long_ax] * s


def remap(t):
    """Position along the long axis (0 … cur_len, scaled) -> stretched position (0 … L)."""
    if part == "all":
        return t * L / cur_len
    if part == "middle":
        end = 0.22 * cur_len
        mid = cur_len - 2 * end
        k = (L - 2 * end) / mid
        return t if t <= end else end + min(t - end, mid) * k + max(t - end - mid, 0)
    seg = 0.35 * cur_len
    k = (L - cur_len + seg) / seg
    if part == "end-max":
        start = cur_len - seg
        return t if t <= start else start + (t - start) * k
    if part == "end-min":
        return t * k if t <= seg else seg * k + (t - seg)
    raise SystemExit(f"unknown part {part}")


for o in objs:
    for v in o.data.vertices:
        c = (v.co - lo) * s
        c[long_ax] = remap(c[long_ax])
        c[wide_ax] *= W / (size[wide_ax] * s)
        v.co = c
    o.data.update()
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB")
pts = [v.co for o in objs for v in o.data.vertices]
print("BBOX " + json.dumps([round(max(p[i] for p in pts) - min(p[i] for p in pts), 3) for i in range(3)]))
