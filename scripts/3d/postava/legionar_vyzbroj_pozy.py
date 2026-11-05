# Legionář s kostrou: výzbroj jako tuhé díly v rukou a na opasku, pózy zadané cíli rukou a nohou (IK).
# blender -b --factory-startup --python vyzbroj_pozy.py -- <kostra.blend> <out_dir> <hdri> [poza ...]
# Souřadnice v metrech, voják hledí k -Y, +X je jeho levá strana. Výstup: <poza>.blend, <poza>.glb, rendery.
import bpy, bmesh, sys, os, math
from mathutils import Vector, Matrix, Quaternion, Euler

args = sys.argv[sys.argv.index("--") + 1:]
BLEND, OUT, HDRI = (os.path.abspath(a) for a in args[:3])
ONLY = args[3:]
os.makedirs(OUT, exist_ok=True)

# ---------------- pózy ----------------
# ruka: grip = střed sevřené pěsti, osa = osa předmětu v pěsti (k hrotu / k horní hraně / k čepeli),
#       klouby = kam míří hřbet prstů; drzi = co je v ruce
# noha: kotnik, smer = kam míří špička (vodorovně), spicka = zvednutí paty (stupně)
# telo: pánev posun a otočení, páteř/hrudník/hlava otočení kolem os světa (stupně X dopředu, Y do boku, Z kroucení)
POZY = {
    "A_stoj": {
        "panev": ((0, 0, 0), (0, 0, 0)),
        "telo": {"spine": (0, 0, 0), "chest": (0, 0, 0), "head": (0, 0, 0)},
        "R": {"grip": (-0.27, -0.16, 1.16), "osa": (0, 0, 1), "klouby": (-0.4, -1, 0), "drzi": "pilum", "pilum_grip": 1.16},
        "L": {"grip": (0.17, -0.27, 0.98), "osa": (1, 0, 0), "klouby": (0, -1, 0), "drzi": "stit"},
        "nohy": {"L": ((0.14, 0.055, 0.105), (0.15, -1, 0), 0), "R": ((-0.14, 0.055, 0.105), (-0.15, -1, 0), 0)},
        "mec": "v_pochve",
    },
    "B_hod_pilem": {
        "panev": ((0.0, 0.08, -0.07), (0, 0, -25)),
        "telo": {"spine": (-6, 0, -12), "chest": (-6, 5, -15), "head": (0, 0, 40)},
        "R": {"grip": (-0.30, 0.30, 1.72), "osa": (0.15, -1, 0.30), "klouby": (0, 0.3, 1), "drzi": "pilum", "pilum_grip": 0.85},
        "L": {"grip": (0.24, -0.32, 1.10), "osa": (1, 0.5, 0), "klouby": (0.3, -1, 0), "drzi": "stit"},
        "nohy": {"L": ((0.22, -0.42, 0.105), (0.2, -1, 0), 0), "R": ((-0.24, 0.42, 0.105), (-0.6, -1, 0), 0)},
        "mec": "v_pochve",
    },
    "C_utok_behem": {
        "panev": ((0.0, -0.05, -0.04), (0, 0, 8)),
        "telo": {"spine": (14, 0, 6), "chest": (6, 0, 6), "head": (-15, 0, -8)},
        "R": {"grip": (-0.29, -0.10, 0.92), "osa": (-0.30, -1, -0.15), "klouby": (-1, 0, -0.3), "drzi": "pilum", "pilum_grip": 0.75},
        "L": {"grip": (0.13, -0.42, 0.95), "osa": (1, 0.2, 0), "klouby": (0, -1, 0), "drzi": "stit"},
        "nohy": {"L": ((0.12, -0.42, 0.42), (0.1, -1, -0.3), 0), "R": ((-0.12, 0.40, 0.16), (-0.1, -1, 0), 35)},
        "mec": "v_pochve",
    },
    "D_bodnuti_gladiem": {
        "panev": ((0.0, -0.08, -0.13), (0, 0, 20)),
        "telo": {"spine": (10, 0, 5), "chest": (4, 0, 6), "head": (-10, 0, -12)},
        "R": {"grip": (-0.30, -0.42, 1.40), "osa": (0.25, -1, 0.0), "klouby": (0, 0, 1), "drzi": "gladius"},
        "L": {"grip": (0.06, -0.58, 0.84), "osa": (1, 0.35, 0), "klouby": (-0.2, -1, 0), "drzi": "stit"},
        "nohy": {"L": ((0.20, -0.52, 0.105), (0.2, -1, 0), 0), "R": ((-0.22, 0.42, 0.105), (-0.5, -1, 0), 0)},
        "mec": "v_ruce",
    },
}
# ---------------- materiály a díly (rozměry v m) ----------------
def mat(name, rgb, rough, metal=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    return m

def join(objs, name, smooth=False):
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join(); o = bpy.context.active_object; o.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if smooth:
        for f in o.data.polygons: f.use_smooth = True
    return o

def cyl(r1, r2, z0, z1, m, verts=20, x=0.0, y=0.0):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=z1 - z0, location=(x, y, (z0 + z1) / 2))
    o = bpy.context.object; o.data.materials.append(m); return o

def box(sx, sy, sz, loc, m, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc); o = bpy.context.object; o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        md = o.modifiers.new("b", "BEVEL"); md.width = bevel; md.segments = 2
        bpy.ops.object.modifier_apply(modifier="b")
    o.data.materials.append(m); return o

IRON = WOOD = BRASS = RED = LEATH = None
def materials():
    global IRON, WOOD, BRASS, RED, LEATH, DARK
    IRON = mat("zelezo", (0.50, 0.50, 0.52), 0.30, 1.0)
    WOOD = mat("drevo", (0.32, 0.17, 0.08), 0.6)
    BRASS = mat("mosaz", (0.62, 0.40, 0.13), 0.42, 1.0)
    RED = mat("stit_cervena", (0.45, 0.03, 0.03), 0.55)
    LEATH = mat("kuze", (0.13, 0.07, 0.04), 0.6)
    DARK = mat("pochva", (0.05, 0.035, 0.03), 0.45)
    global PAINT
    PAINT = mat("stit_malba", (1, 1, 1), 0.6)
    nt = PAINT.node_tree; tx = nt.nodes.new("ShaderNodeTexImage")
    # malba štítu z lokálního FLUXu leží u kostry v knihovně (v3/stit_malba.png); jinou cestu dá STIT_MALBA
    tx.image = bpy.data.images.load(os.environ.get("STIT_MALBA") or os.path.join(os.path.dirname(BLEND), "stit_malba.png"))
    tx.image.pack()
    nt.links.new(tx.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])

def make_pilum(grip_at):
    """Osa +Z, pata v z=0; vrací díl posunutý tak, že bod úchopu je v počátku."""
    p = [cyl(0.011, 0.013, 0.0, 0.08, IRON),                     # botka
         cyl(0.0135, 0.0125, 0.08, 1.30, WOOD),                  # násada
         cyl(0.0125, 0.020, 1.30, 1.335, WOOD, 4),                # jehlanový klín
         cyl(0.020, 0.010, 1.335, 1.40, WOOD, 4),
         cyl(0.0095, 0.0095, 1.37, 1.40, IRON),                   # objímka
         cyl(0.0042, 0.0042, 1.40, 1.97, IRON, 12),               # železný krk
         cyl(0.0045, 0.0095, 1.97, 1.985, IRON, 4),               # osazení
         cyl(0.0095, 0.0, 1.985, 2.03, IRON, 4)]                  # hrot
    o = join(p, "pilum")
    o.data.transform(Matrix.Translation((0, 0, -grip_at)))
    return o

def make_gladius(in_hand=True):
    """Pompejský gladius, osa +Z k hrotu, střed rukojeti v počátku."""
    p = [box(0.032, 0.020, 0.012, (0, 0, -0.058), WOOD, 0.004),     # hlavice (zploštělá)
         cyl(0.013, 0.013, -0.050, 0.040, WOOD, 16),                 # rukojeť
         box(0.075, 0.034, 0.022, (0, 0, 0.052), WOOD, 0.006),       # záštita
         box(0.050, 0.007, 0.43, (0, 0, 0.063 + 0.215), IRON),        # čepel
         ]
    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=0.036, radius2=0, depth=0.06, location=(0, 0, 0.523))
    tip = bpy.context.object; tip.scale = (1, 0.2, 1); tip.rotation_euler = (0, 0, math.radians(45)); tip.data.materials.append(IRON)
    p.append(tip)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.022, location=(0, 0, -0.072))
    pm = bpy.context.object; pm.scale = (1, 1, 0.75); pm.data.materials.append(WOOD); p.append(pm)
    return join(p, "gladius")

def make_scabbard(with_hilt):
    """Pochva gladia, osa +Z vzhůru, ústí v z=0 (hlavice nad ním, když je meč uvnitř)."""
    p = [box(0.062, 0.022, 0.46, (0, 0, -0.23), DARK, 0.006)]
    for z, h in ((-0.012, 0.024), (-0.09, 0.016), (-0.17, 0.016), (-0.43, 0.02)):
        p.append(box(0.066, 0.026, h, (0, 0, z), BRASS, 0.003))
    bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=0.02, radius2=0, depth=0.05, location=(0, 0, -0.475))
    ch = bpy.context.object; ch.rotation_euler = (math.pi, 0, 0); ch.data.materials.append(BRASS); p.append(ch)
    o = join(p, "pochva")
    if with_hilt:
        g = make_gladius(); g.data.transform(Matrix.Translation((0, 0, -0.063)))  # záštita na ústí
        g.data.transform(Matrix.Diagonal((1, 1, -1, 1)))  # čepel dolů do pochvy
        o = join([o, g], "pochva")
    return o

def make_pugio():
    p = [box(0.040, 0.014, 0.21, (0, 0, -0.105), IRON, 0.004)]
    for z in (-0.01, -0.06, -0.12): p.append(box(0.044, 0.018, 0.012, (0, 0, z), BRASS, 0.002))
    p.append(box(0.036, 0.016, 0.008, (0, 0, 0.006), IRON, 0.002))
    p.append(cyl(0.008, 0.008, 0.010, 0.055, WOOD, 16))
    p.append(box(0.032, 0.012, 0.008, (0, 0, 0.060), IRON, 0.002))
    return join(p, "pugio")

def make_shield():
    """Scutum: válcová výseč, R 0,42 m, výška 1,05 m, tětiva ~0,64 m. Úchop v počátku podél X,
    líc míří k -Y (od ruky), okraje se ohýbají k +Y (k tělu)."""
    R, H, half = 0.42, 1.05, 0.80   # půlúhel výseče v rad
    bm = bmesh.new()
    nu, nv = 32, 16
    rows = []
    for j in range(nv + 1):
        z = -H / 2 + H * j / nv; row = []
        for i in range(nu + 1):
            t = -half + 2 * half * i / nu
            row.append(bm.verts.new((R * math.sin(t), -0.06 + R * (1 - math.cos(t)), z)))
        rows.append(row)
    uvl = bm.loops.layers.uv.new("UVMap")
    for j in range(nv):
        for i in range(nu):
            f_ = bm.faces.new((rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i]))
            for lp, (ii, jj) in zip(f_.loops, ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))):
                lp[uvl].uv = (1 - ii / nu, jj / nv)   # líc k -Y: obraz zleva doprava při pohledu zepředu
    me = bpy.data.meshes.new("stit"); bm.to_mesh(me); bm.free()
    board = bpy.data.objects.new("stit", me); bpy.context.scene.collection.objects.link(board)
    board.data.materials.append(PAINT); board.data.materials.append(WOOD); board.data.materials.append(BRASS)
    sol = board.modifiers.new("t", "SOLIDIFY"); sol.thickness = 0.012; sol.offset = 1
    sol.material_offset = 1; sol.material_offset_rim = 2     # rub dřevo, hrana mosaz
    bpy.context.view_layer.objects.active = board; board.select_set(True)
    bpy.ops.object.modifier_apply(modifier="t")
    for f in board.data.polygons: f.use_smooth = True
    # uv pro malbu: u podél oblouku, v podél výšky
    parts = [board]
    # mosazný lem nahoře a dole, kování na bocích
    for z in (-H / 2, H / 2):
        bm = bmesh.new(); prev = None
        pts = [(R * math.sin(-half + 2 * half * i / 48) * 1.0, -0.06 + R * (1 - math.cos(-half + 2 * half * i / 48)), z) for i in range(49)]
        me = bpy.data.meshes.new("lem"); o = bpy.data.objects.new("lem", me); bpy.context.scene.collection.objects.link(o)
        cv = bpy.data.curves.new("lemc", "CURVE"); cv.dimensions = "3D"; sp = cv.splines.new("POLY"); sp.points.add(len(pts) - 1)
        for k, pt in enumerate(pts): sp.points[k].co = (pt[0], pt[1] - 0.002, pt[2], 1)
        cv.bevel_depth = 0.008; cv.bevel_resolution = 2
        co = bpy.data.objects.new("lem", cv); bpy.context.scene.collection.objects.link(co)
        bpy.data.objects.remove(o)
        for ob in bpy.context.selected_objects: ob.select_set(False)
        co.select_set(True); bpy.context.view_layer.objects.active = co; bpy.ops.object.convert(target="MESH")
        co = bpy.context.active_object; co.data.materials.append(BRASS); parts.append(co)
    # puklice: čtvercová deska + kopule (líc v y = -0,06)
    parts.append(box(0.17, 0.006, 0.17, (0, -0.078, 0), mat("zelezo_deska", (0.33, 0.33, 0.34), 0.45, 1.0), 0.004))
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=0.065, location=(0, -0.080, 0))
    dm = bpy.context.object; dm.scale = (1, 0.6, 1); dm.data.materials.append(IRON)
    bm = bmesh.new(); bm.from_mesh(dm.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y > 0.001], context="VERTS"); bm.to_mesh(dm.data); bm.free()
    for f in dm.data.polygons: f.use_smooth = True
    parts.append(dm)
    # vodorovné držadlo za puklicí
    parts.append(cyl(0.013, 0.013, -0.075, 0.075, WOOD, 12))
    parts[-1].rotation_euler = (0, math.pi / 2, 0); bpy.ops.object.transform_apply(rotation=True)
    return join(parts, "stit")

# ---------------- kostra: úchop, IK ----------------
def setup(rig):
    """Rámce úchopu v klidové poloze (svět) pro obě ruce."""
    G = {}
    B = rig.data.bones; M = rig.matrix_world
    for s in ("L", "R"):
        W = M @ B[f"hand.{s}"].head_local; K = M @ B[f"hand.{s}"].tail_local; T = M @ B[f"fingers2.{s}"].tail_local
        Th = M @ B[f"thumb1.{s}"].head_local
        n = Vector((0, -1, 0))                        # dlaň míří dopředu
        d = (K - W).normalized()
        g = d.cross(n).normalized()                   # osa napříč dlaní
        if g.dot(Th - W) < 0: g = -g                  # +g = strana palce
        C = K + (T - K) * 0.30 + n * 0.022            # střed pěsti
        back = -n                                     # hřbet prstů po sevření ~ směr prstů ohnutých do dlaně
        f = (d - g * d.dot(g)).normalized()           # klouby míří podél prstů (pěst)
        G[s] = {"W": W, "C": C, "g": g, "f": f, "n": n, "d": d}
    return G

def frame(a, f):
    a = Vector(a).normalized(); f = Vector(f); f = (f - a * f.dot(a)).normalized()
    return Matrix((a, f, a.cross(f))).transposed()

def curl(rig, s, ang_f, ang_t):
    for bn, ang in ((f"fingers1.{s}", ang_f), (f"fingers2.{s}", ang_f * 0.9), (f"thumb1.{s}", ang_t), (f"thumb2.{s}", ang_t * 0.8)):
        pb = rig.pose.bones[bn]; b = pb.bone
        rest = b.matrix_local.to_quaternion()
        d = (b.tail_local - b.head_local).normalized()
        axis = d.cross(Vector((0, -1, 0))).normalized()
        if bn.startswith("thumb"): axis = d.cross(Vector((0, -1, 0)) + Vector((0, 0, 0))).normalized()
        q = Quaternion(axis, math.radians(ang))
        pb.rotation_mode = "QUATERNION"; pb.rotation_quaternion = rest.inverted() @ q @ rest

def world_rot(rig, name, eul):
    pb = rig.pose.bones[name]; pb.rotation_mode = "QUATERNION"
    rest = pb.bone.matrix_local.to_quaternion()
    q = Euler([math.radians(a) for a in eul], "XYZ").to_quaternion()
    pb.rotation_quaternion = rest.inverted() @ q @ rest

def empty(name, mw):
    e = bpy.data.objects.get(name) or bpy.data.objects.new(name, None)
    if e.name not in bpy.context.scene.collection.objects: bpy.context.scene.collection.objects.link(e)
    e.matrix_world = mw; return e

def build_pose(rig, G, P):
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"; pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0)
        for c in list(pb.constraints): pb.constraints.remove(c)
    # pánev a trup
    (dx, dy, dz), prot = P["panev"]
    world_rot(rig, "pelvis", prot)
    pp = rig.pose.bones["pelvis"]
    pp.location = pp.bone.matrix_local.to_3x3().inverted() @ Vector((dx, dy, dz))
    for bn, e in P["telo"].items(): world_rot(rig, bn, e)
    # ruce: IK na předloktí (2 kosti), ruka kopíruje natočení cíle
    for s in ("L", "R"):
        h = P[s]; g = G[s]
        Rrest = frame(g["g"], g["f"]); Rt = frame(h["osa"], h["klouby"])
        R = Rt @ Rrest.inverted()
        C = Vector(h["grip"]); Wt = C + R @ (g["W"] - g["C"])
        hb = rig.data.bones[f"hand.{s}"]
        tgt = empty(f"cil_ruka.{s}", Matrix.Translation(Wt) @ (R @ hb.matrix_local.to_3x3()).to_4x4())
        side = 1 if s == "L" else -1
        pole = empty(f"pol_loket.{s}", Matrix.Translation(Vector((0.45 * side, 0.45, 1.0))))
        c = rig.pose.bones[f"forearm.{s}"].constraints.new("IK"); c.target = tgt; c.pole_target = pole; c.chain_count = 2
        c.pole_angle = math.radians(-90 if s == "L" else -90)
        cr = rig.pose.bones[f"hand.{s}"].constraints.new("COPY_ROTATION"); cr.target = tgt
        curl(rig, s, 80, 35)
    # nohy: IK na holeni, chodidlo podle směru
    for s in ("L", "R"):
        ank, dirv, toe = P["nohy"][s]
        fb = rig.data.bones[f"foot.{s}"]
        d0 = (fb.tail_local - fb.head_local); d0h = Vector((d0.x, d0.y, 0)).normalized()
        dv = Vector(dirv)
        yaw = math.atan2(dv.y, dv.x) - math.atan2(d0h.y, d0h.x)
        pitch = math.atan2(dv.z, Vector((dv.x, dv.y, 0)).length)
        Rf = Matrix.Rotation(yaw, 3, "Z")
        if toe or pitch:  # zvednutá pata / skloněná špička kolem příčné osy chodidla
            ax = (Rf @ Vector((-d0h.y, d0h.x, 0))).normalized()
            Rf = Matrix.Rotation(-math.radians(toe) + pitch, 3, ax) @ Rf
        tgt = empty(f"cil_noha.{s}", Matrix.Translation(Vector(ank)) @ (Rf @ fb.matrix_local.to_3x3()).to_4x4())
        side = 1 if s == "L" else -1
        kp = Vector(ank) + Vector((dv.x, dv.y, 0)).normalized() * 0.6 + Vector((0.05 * side, 0, 0.45))
        pole = empty(f"pol_koleno.{s}", Matrix.Translation(kp))
        c = rig.pose.bones[f"shin.{s}"].constraints.new("IK"); c.target = tgt; c.pole_target = pole; c.chain_count = 2
        c.pole_angle = math.radians(-90)
        cr = rig.pose.bones[f"foot.{s}"].constraints.new("COPY_ROTATION"); cr.target = tgt
    bpy.context.view_layer.update()

def attach(obj, rig, bone, mw_rest):
    """Díl položený v klidové poloze, přivázaný ke kosti (jde s ní)."""
    obj.matrix_world = mw_rest
    pb = rig.pose.bones[bone]
    mw = obj.matrix_world.copy()
    obj.parent = rig; obj.parent_type = "BONE"; obj.parent_bone = bone
    bpy.context.view_layer.update()
    obj.matrix_world = mw

def place_props(rig, G, P):
    """Výzbroj se položí do cílové pózy podle cíle ruky a přiváže ke kosti ruky (pózovaná kost)."""
    made = []
    for s in ("L", "R"):
        h = P[s]
        Rt = frame(h["osa"], h["klouby"]); C = Vector(h["grip"])
        if h["drzi"] == "pilum":
            o = make_pilum(h["pilum_grip"])
            # osa dílu +Z → osa úchopu
            M = Matrix.Translation(C) @ Rt.to_4x4() @ Matrix.Rotation(math.radians(90), 4, "Y")
        elif h["drzi"] == "gladius":
            o = make_gladius()
            M = Matrix.Translation(C) @ Rt.to_4x4() @ Matrix.Rotation(math.radians(90), 4, "Y")
        else:
            o = make_shield()
            # držadlo (osa X dílu) = osa úchopu; líc (−Y dílu) ve směru kloubů
            M = Matrix.Translation(C) @ Rt.to_4x4() @ Matrix.Diagonal((1, -1, -1, 1))
        o.matrix_world = M
        mwp = o.matrix_world.copy()
        o.parent = rig; o.parent_type = "BONE"; o.parent_bone = f"hand.{s}"
        bpy.context.view_layer.update(); o.matrix_world = mwp
        made.append(o)
    return made

def hip_props(rig, G, P, S):
    """Pochva gladia na pravém boku, pugio na levém; v klidové poloze, přivázané k pánvi."""
    made = []
    sc = make_scabbard(with_hilt=(P["mec"] == "v_pochve"))
    sc.matrix_world = Matrix.Translation((-0.205, 0.0, 1.015)) @ Matrix.Rotation(math.radians(-8), 4, "Y") @ Matrix.Rotation(math.radians(-90), 4, "Z")
    pg = make_pugio()
    pg.matrix_world = Matrix.Translation((0.195, 0.03, 1.00)) @ Matrix.Rotation(math.radians(6), 4, "Y") @ Matrix.Rotation(math.radians(90), 4, "Z")
    return [sc, pg]

# ---------------- běh ----------------
bpy.ops.wm.open_mainfile(filepath=BLEND)
rig = bpy.data.objects["kostra"]; body = bpy.data.objects["legionar"]
materials()
G = setup(rig)
for k, v in G.items(): print("INFO grip", k, {a: tuple(round(c, 3) for c in b) for a, b in v.items()})
# díly na boku v klidové poloze, přivázané k pánvi (před pózou)
for pb in rig.pose.bones:
    pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0)
bpy.context.view_layer.update()

sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 32; sc.cycles.use_denoising = True
sc.render.resolution_x = 1000; sc.render.resolution_y = 1100
sc.view_settings.view_transform = "Standard"
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
env = wd.node_tree.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(HDRI)
wd.node_tree.links.new(env.outputs["Color"], wd.node_tree.nodes["Background"].inputs["Color"])
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.data.type = "ORTHO"; cam.data.ortho_scale = 2.6
sc.collection.objects.link(cam); sc.camera = cam
S = 1.5179
for name, P in POZY.items():
    if ONLY and name not in ONLY: continue
    for o in [o for o in bpy.data.objects if o.name.split(".")[0] in ("pilum", "gladius", "stit", "pochva", "pugio", "lem")]:
        bpy.data.objects.remove(o, do_unlink=True)
    for pb in rig.pose.bones:
        for c in list(pb.constraints): pb.constraints.remove(c)
        pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0)
    bpy.context.view_layer.update()
    hips = hip_props(rig, G, P, S)
    for o in hips:
        mw = o.matrix_world.copy(); o.parent = rig; o.parent_type = "BONE"; o.parent_bone = "pelvis"
        bpy.context.view_layer.update(); o.matrix_world = mw
    build_pose(rig, G, P)
    bpy.context.view_layer.update()
    props = place_props(rig, G, P)
    bpy.context.view_layer.update()
    for vn, d in {"sikmo": (-0.55, -0.85, 0.12), "zboku": (1, 0, 0.05), "zepredu": (0, -1, 0.05)}.items():
        dv = Vector(d).normalized()
        cam.location = Vector((0, -0.05, 1.0)) + dv * 6
        cam.rotation_euler = (-dv).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = os.path.join(OUT, f"{name}-{vn}.png")
        bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, f"{name}.blend"), copy=True)
    # pevný model v póze pro knihovnu: tělo s použitou kostrou + kopie dílů ve světových souřadnicích
    dg = bpy.context.evaluated_depsgraph_get()
    tmp = []
    for o in [body] + props + hips:
        me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), depsgraph=dg)
        c = bpy.data.objects.new(o.name + "_pevny", me); c.matrix_world = o.matrix_world.copy()
        bpy.context.scene.collection.objects.link(c); tmp.append(c)
    for ob in bpy.context.selected_objects: ob.select_set(False)
    for c in tmp: c.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, f"{name}.glb"), export_format="GLB", use_selection=True)
    for c in tmp: bpy.data.objects.remove(c, do_unlink=True)
    print("INFO hotovo", name)
print("DONE")
