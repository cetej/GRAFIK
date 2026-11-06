# Tělo legionáře (varianta 1): muž z Itálie doby císařské, 1,66 m, svalnatý, snědý, tmavé vlasy a oči. MPFB2 (CC0), kostra "default".
# BLENDER_USER_RESOURCES=GRAFIK/run/mpfb_profil blender (profil s MPFB2 a balíky MakeHuman, viz mpfb_instalace.py)
# blender -b --python telo_v1.py -- <out.blend> <render_dir> <hdri>
import bpy, sys, os
import numpy as np
from mathutils import Vector
args = sys.argv[sys.argv.index("--") + 1:]
OUT, RDIR, HDRI = (os.path.abspath(a) for a in args[:3])
os.makedirs(RDIR, exist_ok=True)
from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.locationservice import LocationService
DATA = LocationService.get_user_data("")
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)

VYSKA = 1.66
macro = {"gender": 1.0, "age": 0.5, "muscle": 1.0, "weight": 0.62, "proportions": 0.55, "height": 0.5,
         "cupsize": 0.5, "firmness": 0.5, "race": {"asian": 0.0, "caucasian": 0.9, "african": 0.1}}
body = HumanService.create_human(macro_detail_dict=macro)
s = VYSKA / max(v.co.z for v in body.data.vertices)
body.scale = (s, s, s)
for o in bpy.context.selected_objects: o.select_set(False)
body.select_set(True); bpy.context.view_layer.objects.active = body
bpy.ops.object.transform_apply(scale=True)
body.name = "telo"
rig = HumanService.add_builtin_rig(body, "default"); rig.name = "kostra"
HumanService.set_character_skin(os.path.join(DATA, "skins", "young_caucasian_male", "young_caucasian_male.mhmat"), body, skin_type="ENHANCED_SSS")
assets = {}
for t, f in (("Eyes", "eyes/high-poly/high-poly.mhclo"), ("Eyebrows", "eyebrows/eyebrow002/eyebrow002.mhclo"),
             ("Eyelashes", "eyelashes/eyelashes01/eyelashes01.mhclo"), ("Hair", "hair/short02/short02.mhclo")):
    before = set(bpy.data.objects)
    HumanService.add_mhclo_asset(os.path.join(DATA, f), body, asset_type=t)
    assets[t] = [o for o in bpy.data.objects if o not in before]

def tint(mat, rgb):
    """Násobí barvu povrchu (texturu i hodnotu) zadaným tónem."""
    nt = mat.node_tree
    for b in [n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"]:
        sock = b.inputs["Base Color"]
        if sock.is_linked:
            src = sock.links[0].from_socket
            mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0; mix.inputs[7].default_value = (*rgb, 1)
            nt.links.new(src, mix.inputs[6]); nt.links.new(mix.outputs[2], sock)
        else:
            c = sock.default_value; sock.default_value = (c[0] * rgb[0], c[1] * rgb[1], c[2] * rgb[2], 1)

# pleť: snědý tón přímo do textury (sdílí ji SSS i barva), matnější povrch
for img in bpy.data.images:
    if "lightskinned" in img.name.lower() and "diffuse" in img.name.lower():
        px = np.array(img.pixels[:], np.float32).reshape(-1, 4)
        px[:, :3] *= np.array((0.80, 0.67, 0.54), np.float32)
        img.pixels[:] = px.ravel(); img.pack()
def matte(nt, seen):
    for n in nt.nodes:
        for nm, val in (("Roughness", 0.68), ("Specular IOR Level", 0.25), ("Coat Weight", 0.0), ("Sheen Weight", 0.0)):
            if nm in n.inputs and not n.inputs[nm].is_linked: n.inputs[nm].default_value = val
        if n.type == "VALUE" and ("rough" in n.name.lower() or "rough" in n.label.lower()): n.outputs[0].default_value = 0.68
        if n.type == "GROUP" and n.node_tree and n.node_tree.name not in seen:
            seen.add(n.node_tree.name); matte(n.node_tree, seen)
for m in body.data.materials:
    if m and m.use_nodes:
        matte(m.node_tree, set())
# tmavé vlasy a obočí
for o in assets["Hair"] + assets["Eyebrows"]:
    for m in o.data.materials:
        if m and m.use_nodes: tint(m, (0.12, 0.08, 0.06))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("INFO vyska", round(max((body.matrix_world @ v.co).z for v in body.data.vertices), 3), "kosti", len(rig.data.bones))

sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 48; sc.cycles.use_denoising = True
sc.view_settings.view_transform = "Standard"
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
env = wd.node_tree.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(HDRI)
wd.node_tree.links.new(env.outputs["Color"], wd.node_tree.nodes["Background"].inputs["Color"])
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.data.type = "ORTHO"
sc.collection.objects.link(cam); sc.camera = cam
def shot(fn, ctr, d, scale, rx, ry):
    sc.render.resolution_x, sc.render.resolution_y = rx, ry
    dv = Vector(d).normalized(); cam.data.ortho_scale = scale
    cam.location = Vector(ctr) + dv * 6; cam.rotation_euler = (-dv).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(RDIR, fn); bpy.ops.render.render(write_still=True)
shot("cele.png", (0, 0, 0.84), (-0.35, -1, 0.05), 1.95, 1000, 1000)
shot("hlava.png", (0, 0, VYSKA - 0.13), (-0.3, -1, 0.05), 0.36, 700, 700)
print("DONE")
