# A light copy of a GLB for the Studio viewer (run by engine/models3d.py, free, CPU only):
#   blender -b --factory-startup -P engine/blender/decimate.py -- model.glb viewer.glb TARGET_TRIANGLES
# Collapse-decimates every mesh to ~TARGET_TRIANGLES in total and writes geometry only (no materials,
# textures, UVs or normals: the viewer shows clay and computes smooth normals itself). World positions stay as in the source, so a camera picked in
# the viewer renders the same view from model.glb. Prints `STATS {json}` of the source like render_views.py.
import json
import sys

import bmesh
import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
src, dst, target = args[0], args[1], int(args[2])

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not objs:
    print("STATS " + json.dumps({"verts": 0, "faces": 0}))
    sys.exit(3)
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
tris = sum(len(p.vertices) - 2 for o in objs for p in o.data.polygons)
print("STATS " + json.dumps({
    "verts": sum(len(o.data.vertices) for o in objs), "faces": sum(len(o.data.polygons) for o in objs),
    "triangles": tris, "objects": len(objs), "bbox": [round(v, 4) for v in (hi - lo)],
    "blender": bpy.app.version_string}), flush=True)

# generated meshes come unwelded (Hunyuan3D: 3 vertices per face); welding shrinks the file ~3x and lets
# the collapse keep the surface closed
for o in objs:
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6 * max(hi - lo))
    bm.to_mesh(o.data)
    bm.free()
tris_welded = sum(len(p.vertices) - 2 for o in objs for p in o.data.polygons)
ratio = min(1.0, target / max(tris_welded, 1))
for o in objs:
    o.data.materials.clear()
    if ratio < 1.0:
        m = o.modifiers.new("dec", "DECIMATE")
        m.decimate_type = "COLLAPSE"
        m.ratio = ratio
        m.use_collapse_triangulate = True
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", export_apply=True, export_materials="NONE",
                          export_texcoords=False, export_vertex_color="NONE", export_normals=False, export_animations=False)
out_tris = sum(len(p.vertices) - 2 for o in objs for p in o.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.polygons)
print("VIEWER " + json.dumps({"triangles": out_tris, "ratio": round(ratio, 4)}), flush=True)
