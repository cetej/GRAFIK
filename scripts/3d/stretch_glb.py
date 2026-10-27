# Fit a generated GLB to real dimensions without turning wheels into ovals (free):
#   blender -b -P stretch_glb.py -- in.glb out.glb LENGTH WIDTH HEIGHT [rigid_end_share]
# Uniform scale to the real height, then lengthen only the middle of the body: both ends
# (rigid_end_share of the length each, default 0.22) keep their shape, so wheels stay round.
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
src, dst, L, W, H = a[0], a[1], float(a[2]), float(a[3]), float(a[4])
rigid = float(a[5]) if len(a) > 5 else 0.22
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
up = 2 if "--yup" not in a else 1
long_ax = max((i for i in range(3) if i != up), key=lambda i: size[i])
wide_ax = 3 - up - long_ax
s = H / size[up]
cur_len = size[long_ax] * s
end = rigid * cur_len
mid = cur_len - 2 * end
k = (L - 2 * end) / mid  # stretch factor of the middle part
print("uniform", round(s, 3), "length before", round(cur_len, 3), "middle stretch", round(k, 3))
for o in objs:
    for v in o.data.vertices:
        c = (v.co - lo) * s
        t = c[long_ax]
        if t > end:
            t = end + min(t - end, mid) * k + max(t - end - mid, 0)
        c[long_ax] = t
        c[wide_ax] *= W / (size[wide_ax] * s)
        v.co = c
    o.data.update()
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB")
pts = [v.co for o in objs for v in o.data.vertices]
print("BBOX", " ".join(f"{max(p[i] for p in pts) - min(p[i] for p in pts):.3f}" for i in range(3)))
