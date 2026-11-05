# Sonda: samostatné kusy sítě (loose parts) v okolí boků – je původní meč / dýka oddělitelná?
import bpy, bmesh, sys, os
import numpy as np
GLB = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
body = max((o for o in bpy.context.scene.objects if o.type == "MESH"), key=lambda o: len(o.data.vertices))
bpy.context.view_layer.objects.active = body
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bm = bmesh.new(); bm.from_mesh(body.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)  # švy UV rozpojují síť na ostrůvky
bm.verts.ensure_lookup_table()
seen = np.zeros(len(bm.verts), bool); comps = []
for v0 in bm.verts:
    if seen[v0.index]: continue
    stack = [v0]; seen[v0.index] = True; idx = []
    while stack:
        v = stack.pop(); idx.append(v.index)
        for e in v.link_edges:
            w = e.other_vert(v)
            if not seen[w.index]: seen[w.index] = True; stack.append(w)
    comps.append(idx)
co = np.array([v.co for v in bm.verts])
print("components", len(comps))
for c in sorted(comps, key=len, reverse=True)[:25]:
    p = co[c]; lo, hi = p.min(0), p.max(0)
    print(len(c), "lo", lo.round(3), "hi", hi.round(3))
