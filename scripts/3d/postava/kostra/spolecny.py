# Společný test postupů legionáře: stejné 4 pózy, stejná měřítka, stejné rendery.
# Volá se z Blenderu: exec(open(".../spolecny.py").read()) a pak run_all(ctx).
# ctx: rig, mapa kostí (MAP), body (objekt s kůží), skin_idx (vrcholy kůže stehen pro měření), cloth (objekt látky), cloth_faces (plochy látky nebo None = všechny),
#      prep_pose(callable) volitelně (např. simulace látky), name, out_dir.
import bpy, math, json, os
import numpy as np
from mathutils import Vector, Matrix, Quaternion
from mathutils.bvhtree import BVHTree
SAMJ = os.environ.get("NGM_POZA_SAM", "C:/Users/stock/Documents/000_NGM/GRAFIK/library/3d/rimsky-legionar-v-a-poze-zaklad-pro-kostru/postava/C_result.json")  # 3D body SAM pro pózu běhu C
JEN_POZA = os.environ.get("NGM_POZA")       # jedna póza (úpravy po jedné): přeskočí ostatní pózy i detailní výřezy
PRSTY = {1: 20, 2: 30, 3: 20}
HDRI = "D:/NGM-SKLAD/3d/polyhaven/hdri/art_studio/art_studio_1k.hdr"

def uvolni_prsty(P):                                     # uvolněná ruka: články prstů 20/30/20°, palec poloviční (ohyb kolem lokální X, ověřeno renderem)
    for pb in P:
        if pb.name.startswith("finger") and "-" in pb.name:
            f_, j_ = (int(x) for x in pb.name[6:].split(".")[0].split("-"))
            pb.rotation_mode = "QUATERNION"; pb.rotation_quaternion = Quaternion(Vector((1, 0, 0)), math.radians(PRSTY[j_] * (0.5 if f_ == 1 else 1.0)))

class Poser:
    def __init__(s, rig, MAP):
        s.rig, s.M, s.P = rig, MAP, rig.pose.bones
        s.RM = rig.matrix_world; s.Mi = s.RM.inverted(); s.M3 = s.Mi.to_3x3()
    def upd(s): bpy.context.view_layer.update()
    def b(s, k): return s.P[s.M[k]]
    def W(s, k): return s.RM @ s.b(k).head
    def reset(s):
        for pb in s.P: pb.rotation_mode = "QUATERNION"; pb.matrix_basis = Matrix.Identity(4)
        uvolni_prsty(s.P); s.upd()
    def rot(s, k, Rw):
        pb = s.b(k); h = pb.head.copy()
        pb.matrix = Matrix.Translation(h) @ (s.M3 @ Rw @ s.RM.to_3x3()).to_4x4() @ Matrix.Translation(-h) @ pb.matrix; s.upd()
    def turn(s, k, ax, deg): s.rot(k, Matrix.Rotation(math.radians(deg), 3, Vector(ax)))
    @staticmethod
    def frame(y, x):
        y = y.normalized(); x = (x - y * x.dot(y)).normalized(); return Matrix((x, y, x.cross(y))).transposed()
    def align(s, k, cy, cx, ty, tx): s.rot(k, s.frame(ty, tx) @ s.frame(cy, cx).inverted())
    def aim(s, k, cur, tgt): s.rot(k, cur.normalized().rotation_difference(tgt.normalized()).to_matrix())
    def legs(s, lt, lk, rt, rk):
        s.turn("L_upleg", (1, 0, 0), -lt); s.turn("L_leg", (1, 0, 0), lk); s.turn("R_upleg", (1, 0, 0), -rt); s.turn("R_leg", (1, 0, 0), rk)
    def arms_down(s, deg=25):
        s.turn("L_arm", (0, 1, 0), deg); s.turn("R_arm", (0, 1, 0), -deg)
    def sam(s, path=None):
        R_ = json.load(open(path or SAMJ, encoding="utf-8")); NM = R_["metadata"]["keypoint_names"]; K3 = R_["metadata"]["people"][0]["keypoints_3d"]
        def kp0(n):
            x, y, z = K3[NM.index(n)]; return Vector((x, z, -y))
        low = min(("left", "right"), key=lambda q: kp0(f"{q}-heel").z + kp0(f"{q}-big-toe-tip").z)
        sole = (kp0(f"{low}-big-toe-tip") + kp0(f"{low}-small-toe-tip")) / 2 - kp0(f"{low}-heel")
        _yz = math.hypot(sole.y, sole.z)                     # nadhled kamery předlohy jen z chodidla mířícího ke kameře nebo od ní;
        _ang = math.atan2(sole.z, -sole.y) if sole.y < 0 else math.atan2(-sole.z, sole.y)
        _ang = _ang if _yz > 0.5 * sole.length else 0.0     # chodidlo bokem (předloha z boku) náklon neurčí: dřív otočilo postavu vzhůru nohama
        RX = Matrix.Rotation(max(-0.5, min(0.5, _ang)), 3, "X")   # nejvýš ±29°
        kp = lambda n: RX @ kp0(n)
        hipm = (kp("left-hip") + kp("right-hip")) / 2; nk = kp("neck")
        s.align("hips", s.W("chest") - s.W("hips"), s.W("L_upleg") - s.W("R_upleg"), nk - hipm, kp("left-hip") - kp("right-hip"))
        s.align("chest", s.W("neck") - s.W("chest"), s.W("L_arm") - s.W("R_arm"), nk - hipm, kp("left-shoulder") - kp("right-shoulder"))
        for q, Q in (("L", "left"), ("R", "right")):
            s.align(f"{q}_arm", s.W(f"{q}_fore") - s.W(f"{q}_arm"), s.W(f"{q}_hand") - s.W(f"{q}_fore"), kp(f"{Q}-elbow") - kp(f"{Q}-shoulder"), kp(f"{Q}-wrist") - kp(f"{Q}-elbow"))
            s.aim(f"{q}_fore", s.W(f"{q}_hand") - s.W(f"{q}_fore"), kp(f"{Q}-wrist") - kp(f"{Q}-elbow"))
            s.align(f"{q}_upleg", s.W(f"{q}_leg") - s.W(f"{q}_upleg"), s.W(f"{q}_foot") - s.W(f"{q}_leg"), kp(f"{Q}-knee") - kp(f"{Q}-hip"), kp(f"{Q}-ankle") - kp(f"{Q}-knee"))
            s.aim(f"{q}_leg", s.W(f"{q}_foot") - s.W(f"{q}_leg"), kp(f"{Q}-ankle") - kp(f"{Q}-knee"))
            s.aim(f"{q}_foot", s.W(f"{q}_toe") - s.W(f"{q}_foot"), (kp(f"{Q}-big-toe-tip") + kp(f"{Q}-small-toe-tip")) / 2 - kp(f"{Q}-ankle"))
    def vzprim(s):
        # stoj: krk svisle nad středem kotníků (náklon kamery z chodidla předlohy postavu zaklonil), chodidla pak naplocho jako v klidu
        a = (s.W("L_foot") + s.W("R_foot")) / 2; v = s.W("neck") - a
        s.rot("hips", v.normalized().rotation_difference(Vector((0, 0, 1))).to_matrix())
        B = s.rig.data.bones
        for q in ("L", "R"):
            r0 = s.RM.to_3x3() @ (B[s.M[f"{q}_toe"]].head_local - B[s.M[f"{q}_foot"]].head_local)    # chodidlo v klidové póze
            cur = s.W(f"{q}_toe") - s.W(f"{q}_foot"); h = Vector((cur.x, cur.y, 0)).normalized() * Vector((r0.x, r0.y, 0)).length
            s.aim(f"{q}_foot", cur, h + Vector((0, 0, r0.z)))
    def ik(s, a, b, c, T, pole):                         # dvoukloubová končetina a→b→c: konec c do T, prostřední kloub k pólu
        S = s.W(a); la = (s.W(b) - S).length; lb = (s.W(c) - s.W(b)).length
        u = T - S; d = min(u.length, (la + lb) * 0.995); u.normalize(); v = (pole - u * pole.dot(u)).normalized()
        ca = (la * la + d * d - lb * lb) / (2 * la * d); E = S + u * la * ca + v * la * math.sqrt(max(0.0, 1 - ca * ca))
        s.aim(a, s.W(b) - S, E - S); s.aim(b, s.W(c) - s.W(b), S + u * d - s.W(b))
    def naprah(s):
        # nápřah k hodu oštěpem: SAM z malby dal hluboký podřep s koleny ven (operátor: „spíš padá“).
        # Směr hodu D = od pravého chodidla k levému; zadní noha skoro natažená nese váhu, přední vykročená a mírně pokrčená,
        # boky pootevřené, ramena bokem levým k cíli, hlava k cíli, pravá ruka s pilem vzadu nad ramenem.
        Z = Vector((0, 0, 1)); D = s.W("L_foot") - s.W("R_foot"); D.z = 0; D.normalize(); Fc = D.cross(Z)   # Fc = kam míří hrudník (levý bok k D)
        M = (s.W("L_foot") + s.W("R_foot")) / 2; M.z = 0
        s.align("hips", s.W("chest") - s.W("hips"), s.W("L_upleg") - s.W("R_upleg"), Z - D * 0.08, D * math.cos(0.30) - Fc * math.sin(0.30))   # kroucení boky–ramena jen ~10°: tuhá lorica víc nesnese (rozestoupí se)
        s.align("chest", s.W("neck") - s.W("chest"), s.W("L_arm") - s.W("R_arm"), Z - D * 0.06, D * math.cos(0.12) - Fc * math.sin(0.12))
        s.rot("neck", Fc.rotation_difference(D * 0.8 + Fc * 0.6).to_matrix())
        Lg = (s.W("R_leg") - s.W("R_upleg")).length + (s.W("R_foot") - s.W("R_leg")).length
        FA = M + D * 0.40; RA = M - D * 0.40 + Fc * 0.10
        Hc = (s.W("L_upleg") + s.W("R_upleg")) / 2; off = s.W("R_upleg") - Hc
        tgt = M - D * 0.12; hd = ((tgt + off) - RA); hd.z = 0
        tgt.z = RA.z + math.sqrt(max(0.01, (0.97 * Lg) ** 2 - hd.length ** 2)) - off.z
        hp = s.b("hips"); hp.matrix = Matrix.Translation(s.M3 @ (tgt - Hc)) @ hp.matrix; s.upd()
        Tr = (D * 0.5 + Fc * 0.87).normalized()
        s.ik("L_upleg", "L_leg", "L_foot", FA, D + Z * 0.1); s.ik("R_upleg", "R_leg", "R_foot", RA, Tr)
        B = s.rig.data.bones
        for q, h_ in (("L", D), ("R", Tr)):
            r0 = s.RM.to_3x3() @ (B[s.M[f"{q}_toe"]].head_local - B[s.M[f"{q}_foot"]].head_local)
            s.aim(f"{q}_foot", s.W(f"{q}_toe") - s.W(f"{q}_foot"), h_ * Vector((r0.x, r0.y, 0)).length + Vector((0, 0, r0.z)))
        Ra = s.W("R_arm"); s.ik("R_arm", "R_fore", "R_hand", Ra - D * 0.40 + Z * 0.22 + Fc * 0.10, Vector((0, 0, -1)) - D * 0.3)
        La = s.W("L_arm"); s.ik("L_arm", "L_fore", "L_hand", La + D * 0.35 - Z * 0.25, Vector((0, 0, -1)) + Fc * 0.3)
    def ground(s, objs):
        z = min(min((o.matrix_world @ v.co).z for v in o.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh().vertices) for o in objs)
        hp = s.b("hips"); hp.matrix = Matrix.Translation(s.M3 @ Vector((0, 0, -z))) @ hp.matrix; s.upd()

POSES = [("klid", lambda p: p.arms_down(25)), ("chuze", lambda p: (p.arms_down(25), p.legs(25, 10, -20, 25))),
         ("vypad", lambda p: (p.arms_down(25), p.legs(70, 70, -25, 10))), ("beh_C", lambda p: p.sam())]
# pózy z předloh v2/predlohy_poz: klouby SAM 3D Body vedle C_result.json (<písmeno>_result.json); chybějící se vynechá
for _nm, _f in (("stoj_A", "A_result.json"), ("hod_B", "B_result.json"), ("bod_D", "D_result.json")):
    _pf = os.path.join(os.path.dirname(SAMJ), _f)
    if os.path.exists(_pf): POSES.append((_nm, (lambda p, _pf=_pf: (p.sam(_pf), p.vzprim())) if _nm == "stoj_A" else
                                          (lambda p, _pf=_pf: (p.sam(_pf), p.naprah())) if _nm == "hod_B" else (lambda p, _pf=_pf: p.sam(_pf))))

def ev_coords(o):
    masks = [m for m in o.modifiers if m.type in ("MASK", "SOLIDIFY", "SUBSURF") and m.show_viewport]
    for m in masks: m.show_viewport = False                 # měří se celé tělo a samotná látka (indexy vrcholů); maska, tloušťka a vyhlazení jen pro render
    bpy.context.view_layer.update()
    ev = o.evaluated_get(bpy.context.evaluated_depsgraph_get()); m = ev.to_mesh()
    X = np.empty(len(m.vertices) * 3, np.float32); m.vertices.foreach_get("co", X); X = X.reshape(-1, 3)
    N = np.empty(len(m.vertices) * 3, np.float32); m.vertices.foreach_get("normal", N); N = N.reshape(-1, 3)
    polys = [p.vertices[:] for p in m.polygons]; edges = np.array([e.vertices[:] for e in m.edges])
    Mw = np.array(o.matrix_world); X = X @ Mw[:3, :3].T + Mw[:3, 3]; N = N @ Mw[:3, :3].T
    ev.to_mesh_clear()
    for mm in masks: mm.show_viewport = True
    return X, N, polys, edges

def joint_radius(X, j0, j1, j2, r=0.07):
    """Průměrná vzdálenost kůže od osy kostí v okolí kloubu (loket/koleno)."""
    out = []
    for a_, b_ in ((j0, j1), (j1, j2)):
        ab = b_ - a_; t = np.clip(((X - a_) @ ab) / (ab @ ab), 0, 1); d = np.linalg.norm(X - (a_ + t[:, None] * ab), axis=1); out.append(d)
    d = np.minimum(*out); near = np.linalg.norm(X - j1, axis=1) < r
    return float(np.mean(d[near])) if near.any() else float("nan")

def run_all(ctx):
    rig, MAP, body, cloth = ctx["rig"], ctx["MAP"], ctx["body"], ctx["cloth"]
    p = Poser(rig, MAP); sc = bpy.context.scene; res = {}
    p.reset(); bpy.context.view_layer.update()
    Xr, _, _, Er = ev_coords(cloth); cf = ctx.get("cloth_faces")
    Brest, _, _, _ = ev_coords(body)
    def joints():
        return {q: [np.array(p.W(f"{q}_{a}")) for a in t] for q, t in (("L", ("arm", "fore", "hand")), ("R", ("arm", "fore", "hand")))} | \
               {"K" + q: [np.array(p.W(f"{q}_{a}")) for a in ("upleg", "leg", "foot")] for q in ("L", "R")}
    J0 = joints(); R0 = {k: joint_radius(Brest, *v) for k, v in J0.items()}
    ce = ctx.get("cloth_edges"); Er = Er if ce is None else ce
    rest_len = np.linalg.norm(Xr[Er[:, 0]] - Xr[Er[:, 1]], axis=1)
    skin = ctx["skin_idx"]
    os.makedirs(ctx["out_dir"], exist_ok=True)
    setup_render(sc)
    for pn, pf in POSES:
        if JEN_POZA and pn != JEN_POZA: continue
        p.reset(); pf(p); p.ground(ctx.get("ground_objs", [body]))
        if ctx.get("prep_pose"): ctx["prep_pose"](pn)
        X, N, polys, _ = ev_coords(body); C, _, cpolys, _ = ev_coords(cloth)
        tb = BVHTree.FromPolygons([tuple(x) for x in C], cpolys if cf is None else [cpolys[i] for i in cf])
        poke = sum(1 for v in skin if tb.ray_cast(Vector(X[v]) - Vector(N[v]) * 0.001, -Vector(N[v]), 0.04)[0] is not None)
        L = np.linalg.norm(C[Er[:, 0]] - C[Er[:, 1]], axis=1) / np.maximum(rest_len, 1e-6)
        J = joints(); vol = {k: round(joint_radius(X, *J[k]) / R0[k], 2) for k in J}
        res[pn] = {"kuze_skrz_latku": poke, "trhliny_hran": int((L > 1.6).sum()), "natazeni_p999": round(float(np.percentile(L, 99.9)), 2), "objem_kloubu": vol}
        print("INFO", ctx["name"], pn, res[pn], flush=True)
        for vv, d in {"zepredu": (0.25, -1, 0.08), "zboku": (1, 0, 0.05)}.items():
            shot(sc, os.path.join(ctx["out_dir"], f"{pn}-{vv}.png"), d)
    json.dump(res, open(os.path.join(ctx["out_dir"], "mereni.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return res

def setup_render(sc):
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 32; sc.cycles.use_denoising = True; sc.view_settings.view_transform = "Standard"
    wd = bpy.data.worlds.new("svet_test"); sc.world = wd; wd.use_nodes = True
    env = wd.node_tree.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(HDRI)
    bg = wd.node_tree.nodes["Background"]; wd.node_tree.links.new(env.outputs["Color"], bg.inputs["Color"])
    # světlo z HDRI, ale za postavou jednolitá šedá
    lp = wd.node_tree.nodes.new("ShaderNodeLightPath"); mx = wd.node_tree.nodes.new("ShaderNodeMixShader"); gray = wd.node_tree.nodes.new("ShaderNodeBackground")
    gray.inputs[0].default_value = (0.36, 0.38, 0.37, 1); out = wd.node_tree.nodes["World Output"]
    wd.node_tree.links.new(lp.outputs["Is Camera Ray"], mx.inputs[0]); wd.node_tree.links.new(bg.outputs[0], mx.inputs[1]); wd.node_tree.links.new(gray.outputs[0], mx.inputs[2])
    wd.node_tree.links.new(mx.outputs[0], out.inputs[0])
    cam = bpy.data.objects.new("cam_test", bpy.data.cameras.new("cam_test")); cam.data.type = "ORTHO"; sc.collection.objects.link(cam); sc.camera = cam

def shot(sc, path, d, scale=2.0, ctr=(0, 0, 0.86)):
    cam = sc.camera; sc.render.resolution_x, sc.render.resolution_y = 700, 900
    dv = Vector(d).normalized(); cam.data.ortho_scale = scale
    cam.location = Vector(ctr) + dv * 6; cam.rotation_euler = (-dv).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = path; bpy.ops.render.render(write_still=True)
