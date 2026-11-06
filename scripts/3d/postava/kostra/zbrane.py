# Vkládá se do postava_s_vystroji.py (exec) po nahrad_vystroj.py: zbraně z generátoru (vystroj_dily.py, zadání zbrane_legionar*.json)
# srovnané na skutečnou délku a v pózách s předlohou sevřené v pěsti. Bez model.glb se zbraň vynechá.
ZBR = os.path.join(os.path.dirname(VYSTROJ), "zbrane")
DELKA = {"pilum": 2.0, "gladius": 0.65, "scutum": 1.05}          # celková délka (štít výška), m
# póza -> ruka -> (zbraň, kam míří hrot); štít vždy levou rukou, lícem od těla
ZBR_POZY = {"stoj_A": {"R": ("pilum", "nahoru"), "L": ("scutum", None)}, "hod_B": {"R": ("pilum", "vpred"), "L": ("scutum", None)},
            "beh_C": {"R": ("pilum", "vpred"), "L": ("scutum", None)}, "bod_D": {"R": ("gladius", "vpred"), "L": ("scutum", None)}}
PEST = {1: 75, 2: 95, 3: 60}                                     # sevřená pěst kolem násady, palec poloviční
ZB = {}

def _hlavni_osy(o):
    # síť do vlastních hlavních os (X nejdelší, Z nejkratší), střed do počátku, měřítko na skutečnou délku
    C = co(o); c0 = C.mean(0); _, _, Vt = np.linalg.svd(C - c0, full_matrices=False)
    if np.linalg.det(Vt) < 0: Vt[2] *= -1
    R4 = Matrix([list(Vt[0]) + [0], list(Vt[1]) + [0], list(Vt[2]) + [0], [0, 0, 0, 1]])
    o.data.transform(R4 @ Matrix.Translation(-Vector(c0))); C = co(o)
    return C

def _otoc(o, osa, deg):
    o.data.transform(Matrix.Rotation(math.radians(deg), 4, osa))

def _mat(nm, rgb, kov, drsnost):
    m = bpy.data.materials.new(nm); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Metallic"].default_value = kov; b.inputs["Roughness"].default_value = drsnost
    return m

def pilum_z_tvaru():
    # pilum 2,0 m podél X, hrot na +X: botka, násada, hranolek, olověná koule, železný dřík, jehlanový hrot (Hunyuan tenké kopí odmítl)
    drevo = _mat("pilum_drevo", (0.22, 0.11, 0.05), 0.0, 0.6); zelezo = _mat("pilum_zelezo", (0.30, 0.30, 0.31), 1.0, 0.45)
    kusy = []
    def kus(op, x0, x1, mat, **kw):
        op(location=((x0 + x1) / 2, 0, 0), rotation=(0, math.pi / 2, 0), **kw); o = bpy.context.active_object
        o.data.materials.append(mat); kusy.append(o)
    kus(bpy.ops.mesh.primitive_cone_add, -1.0, -0.92, zelezo, vertices=16, radius1=0.004, radius2=0.013, depth=0.08)
    kus(bpy.ops.mesh.primitive_cylinder_add, -0.92, 0.33, drevo, vertices=16, radius=0.0135, depth=1.25)
    kus(bpy.ops.mesh.primitive_cube_add, 0.33, 0.39, drevo, size=1); kusy[-1].scale = (0.032, 0.032, 0.06)   # lokální Z je po otočení podél násady
    bpy.ops.mesh.primitive_uv_sphere_add(location=(0.425, 0, 0), radius=0.03, segments=24, ring_count=12); kusy.append(bpy.context.active_object); kusy[-1].data.materials.append(zelezo)
    kus(bpy.ops.mesh.primitive_cylinder_add, 0.39, 0.965, zelezo, vertices=12, radius=0.0045, depth=0.575)
    kus(bpy.ops.mesh.primitive_cone_add, 0.965, 1.0, zelezo, vertices=4, radius1=0.009, radius2=0.0, depth=0.035)
    for o in kusy: sel([o]); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    sel(kusy); bpy.ops.object.join(); o = bpy.context.view_layer.objects.active; o.name = "pilum_novy"
    return o

_DIL0 = DIL; DIL = ZBR
for d in DELKA:
    if d == "pilum" and not os.path.exists(os.path.join(ZBR, d, "model.glb")):
        o = pilum_z_tvaru(); ZB[d] = {"o": o, "uchop": Vector((0.0, 0, 0))}; o.hide_render = o.hide_viewport = True
        for f in o.data.polygons: f.use_smooth = True
        print("INFO zbran pilum z tvaru, delka m 2.0", flush=True); continue
    if not os.path.exists(os.path.join(ZBR, d, "model.glb")): continue
    if d == "scutum":                                             # osy z generátoru: výška Z, šířka X, puklice na −Y (hlavní osy sítě štít natočily)
        o = nacti(d); C = co(o); lo, hi = C.min(0), C.max(0)
        o.data.transform(Matrix.Scale(DELKA[d] / float(hi[2] - lo[2]), 4) @ Matrix.Translation(-Vector((lo + hi) / 2))); C = co(o)
        ZB[d] = {"o": o, "uchop": Vector((0, float(C[:, 1].min()) + 0.09, 0))}   # pěst 9 cm za čelem puklice: za deskou, v dutině puklice
        o.hide_render = o.hide_viewport = True
        print("INFO zbran scutum vyska m", DELKA[d], "uchop", tuple(round(x, 3) for x in ZB[d]["uchop"]), flush=True); continue
    o = nacti(d); C = _hlavni_osy(o)
    k = DELKA[d] / float(C[:, 0].max() - C[:, 0].min()); o.data.transform(Matrix.Scale(k, 4)); C = co(o); L = float(C[:, 0].max() - C[:, 0].min())
    x0, x1 = float(C[:, 0].min()), float(C[:, 0].max())
    def sirka(lo, hi):                                            # průměrná šířka průřezu v úseku délky
        q = C[(C[:, 0] >= lo) & (C[:, 0] <= hi)]
        return float(np.hypot(q[:, 1].max() - q[:, 1].min(), q[:, 2].max() - q[:, 2].min())) if len(q) else 0.0
    u = 0.30 if d == "pilum" else 0.04                           # hrot: konec s užším průřezem (pilum dlouhý železný dřík, gladius špička)
    if sirka(x1 - u * L, x1) > sirka(x0, x0 + u * L): _otoc(o, "Z", 180); C = co(o); x0, x1 = float(C[:, 0].min()), float(C[:, 0].max())
    g = x0 + (0.5 * L if d == "pilum" else 0.075)                # pilum v polovině, gladius rukojeť 7,5 cm od hlavice
    ZB[d] = {"o": o, "uchop": Vector((g, 0, 0))}
    o.hide_render = o.hide_viewport = True
    for f in o.data.polygons: f.use_smooth = True
    print("INFO zbran", d, "delka m", round(L, 3), "uchop", tuple(round(x, 3) for x in ZB[d]["uchop"]), flush=True)
DIL = _DIL0

def _ruka(sd):
    P = rig.pose.bones; M = rig.matrix_world
    W = M @ P[f"wrist.{sd}"].head; K = M @ P[f"finger3-1.{sd}"].head; I = M @ P[f"finger2-1.{sd}"].head; Pk = M @ P[f"finger5-1.{sd}"].head
    T = M @ P[f"finger3-3.{sd}"].tail
    osa = (I - Pk).normalized(); delka = (K - W); n = osa.cross(delka).normalized()
    if (T - W).dot(n) < 0: n = -n                                   # dlaň = strana, ke které se prsty ohýbají
    G = W + delka * 0.85 + n * 0.022                                 # střed sevřené pěsti
    return G, osa, n

def _vpred():
    M = rig.matrix_world; lev = M @ rig.pose.bones["upperleg01.L"].head - M @ rig.pose.bones["upperleg01.R"].head
    v = lev.cross(Vector((0, 0, 1))); v.z = 0                         # vpřed = kolmo na spojnici kyčlí (osy kořenové kosti MPFB míří podél páteře)
    return v.normalized() if v.length > 1e-6 else Vector((0, -1, 0))

def zbr_ruce(pn):
    if pn == "stoj_A":                                                # štít po levém boku (předloha A): paže podél těla, předloktí vpřed
        p_ = Poser(rig, MAP); f_ = _vpred(); lev = Vector((0, 0, 1)).cross(f_)
        p_.aim("L_arm", p_.W("L_fore") - p_.W("L_arm"), (Vector((0, 0, -1)) + lev * 0.25 + f_ * 0.1).normalized())
        p_.aim("L_fore", p_.W("L_hand") - p_.W("L_fore"), (f_ + lev * 0.15 - Vector((0, 0, 0.5))).normalized())   # pěst níž: horní hrana štítu u ramene
    for sd, (d, _) in ZBR_POZY.get(pn, {}).items():
        if d not in ZB: continue
        for pb in rig.pose.bones:
            if pb.name.startswith("finger") and "-" in pb.name and pb.name.endswith("." + sd):
                f_, j_ = (int(x) for x in pb.name[6:].split(".")[0].split("-"))
                pb.rotation_mode = "QUATERNION"; pb.rotation_quaternion = Quaternion(Vector((1, 0, 0)), math.radians(PEST[j_] * (0.6 if f_ == 1 else 1.0)))
    bpy.context.view_layer.update()

def zbr_umisti(pn):
    for z in ZB.values(): z["o"].hide_render = z["o"].hide_viewport = True
    vpred = _vpred()
    for sd, (d, hrot) in ZBR_POZY.get(pn, {}).items():
        if d not in ZB: continue
        G, osa, n = _ruka(sd); o = ZB[d]["o"]
        if d == "scutum":                                                 # štít svisle, lícem vodorovně od hrudníku přes pěst ven
            F = G - rig.matrix_world @ rig.pose.bones["spine03"].head; F.z = 0; F = F.normalized() if F.length > 1e-6 else vpred
            if pn == "stoj_A": F = vpred                                  # u boku lícem dopředu, ne do strany
            Z = Vector((0, 0, 1)); Y = -F; X = Y.cross(Z)
        elif hrot == "nahoru":                                            # pilum u nohy svisle hrotem nahoru (předloha A)
            X = Vector((0, 0, 1)); Z = (n - X * n.dot(X)).normalized(); Y = Z.cross(X)
        else:
            hint = Vector((0, 0, 1)) if hrot == "nahoru" else (vpred + Vector((0, 0, 0.2))).normalized()
            X = osa if (d == "gladius" or osa.dot(hint) >= 0) else -osa   # gladius čepelí na straně palce
            Z = (n - X * n.dot(X)).normalized(); Y = Z.cross(X)
        R = Matrix((X, Y, Z)).transposed().to_4x4()
        o.matrix_world = Matrix.Translation(G) @ R @ Matrix.Translation(-ZB[d]["uchop"])
        o.hide_render = o.hide_viewport = False
    bpy.context.view_layer.update()
