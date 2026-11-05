# Sonda: souřadnice + normály vrcholů (po spojení švů) pro výpočet povrchu boku a štítu.
import bpy, bmesh, sys, os
import numpy as np
GLB = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
body = max((o for o in bpy.context.scene.objects if o.type == "MESH"), key=lambda o: len(o.data.vertices))
bpy.context.view_layer.objects.active = body
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bm = bmesh.new(); bm.from_mesh(body.data); bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
bm.normal_update()
np.savez(os.path.join(os.path.dirname(GLB), "normaly.npz"), co=np.array([v.co for v in bm.verts]), nr=np.array([v.normal for v in bm.verts]))
