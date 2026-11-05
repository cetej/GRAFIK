# Sonda: kde v modelu leží štít, puklice a pochva meče (podle barvy textury pod vrcholy a polohy).
# blender -b --factory-startup --python sonda_dily.py -- <model.glb>
import bpy, sys, os
import numpy as np

GLB = os.path.abspath(sys.argv[sys.argv.index("--") + 1])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
obj = max((o for o in bpy.context.scene.objects if o.type == "MESH"), key=lambda o: len(o.data.vertices))
bpy.context.view_layer.objects.active = obj
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = obj.data
co = np.array([v.co for v in me.vertices]); n = len(co)
uv = np.zeros((len(me.loops), 2)); me.uv_layers.active.data.foreach_get("uv", uv.ravel())
lv = np.zeros(len(me.loops), int); me.loops.foreach_get("vertex_index", lv)
vuv = np.zeros((n, 2)); vuv[lv] = uv
mat = me.materials[0]
img = next(nd.image for nd in mat.node_tree.nodes if nd.type == "TEX_IMAGE" and nd.image and nd.image.colorspace_settings.name != "Non-Color")
w, h = img.size
px = np.array(img.pixels[:], np.float32).reshape(h, w, 4)[..., :3]
c = px[np.clip((vuv[:, 1] * h).astype(int), 0, h - 1), np.clip((vuv[:, 0] * w).astype(int), 0, w - 1)]
r, g, b = c.T
mx = c.max(1); mn = c.min(1); sat = (mx - mn) / np.maximum(mx, 1e-4)
hue = np.degrees(np.arctan2(np.sqrt(3) * (g - b), 2 * r - g - b)) % 360
np.savez(os.path.join(os.path.dirname(GLB) or ".", "sonda.npz"), co=co, col=c, hue=hue, sat=sat)
lo, hi = co.min(0), co.max(0)
print("bbox lo", lo.round(3), "hi", hi.round(3))
red = (sat > 0.55) & ((hue < 15) | (hue > 340)) & (mx > 0.35)
blue = (b > r + 0.03) & (b > g) & (mx < 0.45)
print("red verts", red.sum(), "x", np.percentile(co[red, 0], [2, 98]).round(3), "y", np.percentile(co[red, 1], [2, 98]).round(3), "z", np.percentile(co[red, 2], [2, 98]).round(3))
print("blue verts", blue.sum(), "x", np.percentile(co[blue, 0], [2, 98]).round(3), "y", np.percentile(co[blue, 1], [2, 98]).round(3), "z", np.percentile(co[blue, 2], [2, 98]).round(3))
for xs in np.linspace(lo[0], hi[0], 13):
    s = (co[:, 0] > xs - 0.02) & (co[:, 0] < xs + 0.02) & red
    if s.sum() > 50:
        print(f"x {xs:.3f}: red y {np.percentile(co[s, 1], 5):.3f}..{np.percentile(co[s, 1], 95):.3f} z {co[s, 2].min():.3f}..{co[s, 2].max():.3f} n {s.sum()}")
