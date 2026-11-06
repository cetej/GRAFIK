# Zkušební pózy kostry: -- <kostra.blend> <out_dir> <hdri>
# Póza = otočení kostí kolem os světa (stupně X, Y, Z) v klidovém rámci kosti; X dopředu/dozadu, Y do strany, Z kroucení.
import bpy, sys, os, math
from mathutils import Euler, Vector
args = sys.argv[sys.argv.index("--") + 1:]
BLEND, OUT, HDRI = (os.path.abspath(a) for a in args[:3])
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=BLEND)
rig = bpy.data.objects["kostra"]
POZY = {
    "vypad": {"pelvis": (0, 0, 10), "spine": (12, 0, -5), "chest": (5, 0, -10),
              "thigh.L": (-60, 0, 0), "shin.L": (55, 0, 0), "foot.L": (5, 0, 0),
              "thigh.R": (28, 0, 0), "shin.R": (12, 0, 0), "foot.R": (-20, 0, 0),
              "upperarm.R": (-80, -35, 0), "forearm.R": (-15, 0, 0),
              "upperarm.L": (-45, 30, 0), "forearm.L": (-75, 0, 0)},
    "hod_pilem": {"spine": (-5, 0, 18), "chest": (-5, 0, 15), "head": (0, 0, -25),
                  "thigh.L": (-30, 0, 0), "shin.L": (15, 0, 0), "thigh.R": (18, 0, 0), "shin.R": (8, 0, 0),
                  "upperarm.R": (25, 95, 0), "forearm.R": (60, 0, 0),
                  "upperarm.L": (-85, 25, 0), "forearm.L": (-10, 0, 0)},
    "krok": {"thigh.L": (-25, 0, 0), "shin.L": (20, 0, 0), "thigh.R": (20, 0, 0), "shin.R": (25, 0, 0), "foot.R": (-15, 0, 0),
             "upperarm.L": (20, -38, 0), "forearm.L": (-15, 0, 0), "upperarm.R": (-25, 38, 0), "forearm.R": (-25, 0, 0)},
}
sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 24; sc.cycles.use_denoising = True
sc.render.resolution_x = 900; sc.render.resolution_y = 1100
sc.view_settings.view_transform = "Standard"
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
env = wd.node_tree.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(HDRI)
wd.node_tree.links.new(env.outputs["Color"], wd.node_tree.nodes["Background"].inputs["Color"])
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.data.type = "ORTHO"; cam.data.ortho_scale = 2.3
sc.collection.objects.link(cam); sc.camera = cam
for pb in rig.pose.bones: pb.rotation_mode = "QUATERNION"
for name, poza in {"klid": {}, **POZY}.items():
    for pb in rig.pose.bones:
        rest = pb.bone.matrix_local.to_quaternion()
        r = poza.get(pb.name, (0, 0, 0))
        q = Euler([math.radians(a) for a in r], "XYZ").to_quaternion()
        pb.rotation_quaternion = rest.inverted() @ q @ rest
    bpy.context.view_layer.update()
    for vn, d in {"sikmo": (-0.6, -0.8, 0.1), "zboku": (1, 0, 0.05)}.items():
        dv = Vector(d).normalized()
        cam.location = Vector((0, 0, 0.95)) + dv * 6
        cam.rotation_euler = (-dv).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = os.path.join(OUT, f"{name}-{vn}.png")
        bpy.ops.render.render(write_still=True)
print("DONE")
