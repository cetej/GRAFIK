# Vkládá se do postava_s_vystroji.py (exec) po nahrad_vystroj.py: zbraně z generátoru (vystroj_dily.py, zadání zbrane_legionar*.json)
# srovnané na skutečnou délku a v pózách s předlohou sevřené v pěsti. Bez model.glb se zbraň vynechá.
ZBR = os.path.join(os.path.dirname(VYSTROJ), "zbrane")
DELKA = {"pilum": 2.0, "gladius": 0.65, "scutum": 1.05}          # celková délka, štít výška (formát 1,05 × 0,58 m, prohnutí 18 cm vybral operátor 2026-11-07 na postavě)
# póza -> ruka -> (zbraň, kam míří hrot); štít vždy levou rukou, lícem od těla
# hrot: "nahoru" = svisle, číslo = míří tam, kam líc štítu (k nepříteli), zvednutý o tolik (B hod nahoru, C běh s hrotem dolů)
ZBR_POZY = {"stoj_A": {"R": ("pilum", "nahoru"), "L": ("scutum", None)}, "hod_B": {"R": ("pilum", 0.5), "L": ("scutum", None)},
            "beh_C": {"R": ("pilum", -0.3), "L": ("scutum", None)}, "bod_D": {"R": ("gladius", 0.0), "L": ("scutum", None)}}
PEST = {1: 75, 2: 95, 3: 60}                                     # sevřená pěst kolem násady, palec poloviční
ZB = {}; ZB_STITY = []

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

def stit_z_tvaru(slozka, H=None, W=0.58, S=0.18):
    # scutum z tvarů (model z generátoru měl rozmazanou malbu, držadlo skrz desku a nestejnou tloušťku): deska jako výseč válce
    # 1,05 × 0,58 m, prohnutí 18 cm, tloušťka 1,2 cm, mosazný lem, železná deska s puklicí, dřevěné vodorovné držadlo vzadu.
    # Malba = čistý pohled z lokálního FLUXu, zrcadlený podle osy puklice (textura-lic.png, textura-rub.png). Výška Z, šířka X, líc na −Y.
    H = H or DELKA["scutum"]; T = 0.012
    R = (W * W / 4 + S * S) / (2 * S); Yc = R - S / 2                        # střed křivosti za štítem, líc uprostřed na y = −S/2
    def img_mat(nm, f):
        m = bpy.data.materials.new(nm); m.use_nodes = True; nt = m.node_tree; b = nt.nodes["Principled BSDF"]
        tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = bpy.data.images.load(os.path.join(slozka, f)); nt.links.new(tx.outputs["Color"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.6; return m
    mats = [img_mat("stit_lic", "textura-lic.png"), img_mat("stit_rub", "textura-rub.png"), _mat("stit_mosaz", (0.72, 0.52, 0.2), 1.0, 0.35),
            _mat("stit_zelezo", (0.45, 0.45, 0.47), 1.0, 0.4), _mat("stit_drevo", (0.3, 0.17, 0.08), 0.0, 0.6)]
    bm = bmesh.new(); uvl = bm.loops.layers.uv.new()
    def slab(Rf, w, h, t, mf, mb, ms, uv, z0=0.0):
        th = math.asin(min(0.999, w / 2 / Rf)); nu = max(4, int(w / 0.01)); nv = max(4, int(h / 0.01))
        P = lambda r, i, j: Vector((r * math.sin(-th + 2 * th * i / nu), Yc - r * math.cos(-th + 2 * th * i / nu), z0 - h / 2 + h * j / nv))
        U = lambda i: (math.sin(-th + 2 * th * i / nu) / math.sin(th) + 1) / 2
        F = [[bm.verts.new(P(Rf, i, j)) for j in range(nv + 1)] for i in range(nu + 1)]
        B = [[bm.verts.new(P(Rf - t, i, j)) for j in range(nv + 1)] for i in range(nu + 1)]
        def face(vs, m, uvs=None):
            f = bm.faces.new(vs); f.material_index = m
            if uvs:
                for l, u in zip(f.loops, uvs): l[uvl].uv = u
        for i in range(nu):
            for j in range(nv):
                u0, u1, v0, v1 = U(i), U(i + 1), j / nv, (j + 1) / nv   # malba je pohled zepředu: u podle průmětu x, ne podle oblouku
                face((F[i][j], F[i + 1][j], F[i + 1][j + 1], F[i][j + 1]), mf, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)] if uv else None)
                face((B[i][j], B[i][j + 1], B[i + 1][j + 1], B[i + 1][j]), mb, [(1 - u0, v0), (1 - u0, v1), (1 - u1, v1), (1 - u1, v0)] if uv else None)
        for i in range(nu):
            face((F[i][0], B[i][0], B[i + 1][0], F[i + 1][0]), ms); face((F[i][nv], F[i + 1][nv], B[i + 1][nv], B[i][nv]), ms)
        for j in range(nv):
            face((F[0][j], F[0][j + 1], B[0][j + 1], B[0][j]), ms); face((F[nu][j], B[nu][j], B[nu][j + 1], F[nu][j + 1]), ms)
    slab(R, W, H, T, 0, 1, 2, True)                                       # deska
    ZP = 0.018                                                            # puklice je na malbě o 1,8 cm nad středem
    slab(R + 0.007, 0.225, 0.245, 0.007, 3, 3, 3, False, ZP)             # železná deska puklice před lícem, kryje namalovanou
    bm.normal_update()
    o = bpy.data.objects.new("scutum_novy", bpy.data.meshes.new("scutum_novy")); bm.to_mesh(o.data); bm.free(); sc.collection.objects.link(o)
    for m in mats: o.data.materials.append(m)
    kusy = [o]
    th = math.asin(W / 2 / R); rl = R - T / 2                              # mosazný lem po obvodu: spodní hrana zleva doprava, horní zpět
    pts = [(rl * math.sin(a), Yc - rl * math.cos(a), z) for z, sm in ((-H / 2, 1), (H / 2, -1)) for a in (sm * (-th + 2 * th * k / 24) for k in range(25))]
    cu = bpy.data.curves.new("lem", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = 0.009; cu.bevel_resolution = 3
    sp = cu.splines.new("POLY"); sp.points.add(len(pts) - 1)
    for p_, q_ in zip(sp.points, pts): p_.co = (*q_, 1)
    sp.use_cyclic_u = True
    lo_ = bpy.data.objects.new("lem", cu); sc.collection.objects.link(lo_); sel([lo_]); bpy.ops.object.convert(target="MESH"); lo_ = bpy.context.view_layer.objects.active
    lo_.data.materials.clear(); lo_.data.materials.append(mats[2]); kusy.append(lo_)
    y0 = -S / 2
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.065, segments=32, ring_count=16, location=(0, y0 - 0.007, ZP)); d_ = bpy.context.active_object
    d_.scale = (1, 0.75, 1); d_.data.materials.append(mats[3]); kusy.append(d_)                     # polokoule puklice (zadní půlka je v desce)
    rub = lambda x: Yc - math.sqrt((R - T) ** 2 - x * x)                    # rub desky v místě x (deska je prohnutá, držadlo ji nesmí protnout)
    yg = rub(0.12) + 0.022                                                # držadlo 2,2 cm za rubem i na koncích
    bpy.ops.mesh.primitive_cylinder_add(radius=0.016, depth=0.24, vertices=16, location=(0, yg, 0), rotation=(0, math.pi / 2, 0))
    g_ = bpy.context.active_object; g_.data.materials.append(mats[4]); kusy.append(g_)              # držadlo vodorovně za puklicí
    for sx in (-0.12, 0.12):                                              # úchyty od rubu k držadlu
        y1 = rub(abs(sx)) + 0.002; bpy.ops.mesh.primitive_cube_add(size=1, location=(sx, (y1 + yg) / 2, 0)); b_ = bpy.context.active_object
        b_.scale = (0.03, yg - y1 + 0.016, 0.04); b_.data.materials.append(mats[4]); kusy.append(b_)
    for k_ in kusy: sel([k_]); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    sel(kusy); bpy.ops.object.join(); o = bpy.context.view_layer.objects.active; o.name = "scutum_novy"
    for f in o.data.polygons: f.use_smooth = f.material_index != 1
    return o, Vector((0, yg, 0))                                            # pěst svírá držadlo

_DIL0 = DIL; DIL = ZBR
for d in DELKA:
    if d == "pilum" and not os.path.exists(os.path.join(ZBR, d, "model.glb")):
        o = pilum_z_tvaru(); ZB[d] = {"o": o, "uchop": Vector((0.0, 0, 0))}; o.hide_render = o.hide_viewport = True
        for f in o.data.polygons: f.use_smooth = True
        print("INFO zbran pilum z tvaru, delka m 2.0", flush=True); continue
    if d == "scutum" and os.path.exists(os.path.join(ZBR, d, "textura-lic.png")):
        # NGM_STITY="výška,šířka,prohnutí;…" = víc formátů štítu na zkoušku (fotky každé pózy se vyfotí s každým), jinak jeden výchozí
        _fm = [tuple(float(x) for x in f_.split(",")) for f_ in os.environ.get("NGM_STITY", "").split(";") if f_] or [(DELKA[d], 0.58, 0.18)]
        for H_, W_, S_ in _fm:
            o, g_ = stit_z_tvaru(os.path.join(ZBR, d), H_, W_, S_); o.hide_render = o.hide_viewport = True; ZB_STITY.append({"o": o, "uchop": g_, "nazev": f"{H_:.2f}x{W_:.2f}x{S_:.2f}"})
        ZB[d] = dict(ZB_STITY[0]); o = ZB[d]["o"]; g_ = ZB[d]["uchop"]
        print("INFO zbran scutum z tvaru, vyska m", DELKA[d], "uchop", tuple(round(x, 3) for x in g_), flush=True); continue
    if not os.path.exists(os.path.join(ZBR, d, "model.glb")): continue
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
def _kolize_pripravit(z):                                          # zjednodušená kopie pro kontrolu průniků (štít z generátoru má 500 tisíc ploch)
    m_ = z["o"].data.copy(); bm_ = bmesh.new(); bm_.from_mesh(m_); bmesh.ops.triangulate(bm_, faces=bm_.faces[:])
    if len(bm_.faces) > 4000:
        bm_.to_mesh(m_); bm_.free(); tmp = bpy.data.objects.new("tmp_kol", m_); sc.collection.objects.link(tmp)
        dm = tmp.modifiers.new("d", "DECIMATE"); dm.ratio = 4000 / len(m_.polygons); sel([tmp]); bpy.ops.object.modifier_apply(modifier="d")
        m_ = tmp.data; bpy.data.objects.remove(tmp, do_unlink=True)
    else:
        bm_.to_mesh(m_); bm_.free()
    z["kol"] = (np.array([v.co[:] for v in m_.vertices]), [p_.vertices[:] for p_ in m_.polygons])
for z in list(ZB.values()) + ZB_STITY: _kolize_pripravit(z)

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

def _ik(p_, sd, T):                                                 # paže: zápěstí do T, loket dolů a ven
    ven = p_.W(f"{sd}_arm") - p_.W("chest"); ven.z = 0
    p_.ik(f"{sd}_arm", f"{sd}_fore", f"{sd}_hand", T, Vector((0, 0, -1)) + ven.normalized() * 0.5)

def _smer_hodu(pn):                                                 # směr hodu z Poser.naprah (od zadního chodidla k přednímu)
    return Vector(rig["smer_hodu"]) if "smer_hodu" in rig else _vpred()

def zbr_ruce(pn):
    if pn == "stoj_A":                                                # stoj (předloha A, rekonstruktéři): vodorovné držadlo jako kufr, paže volně dolů, štít před levým stehnem
        p_ = Poser(rig, MAP); f_ = _vpred(); lev = Vector((0, 0, 1)).cross(f_)
        p_.aim("L_arm", p_.W("L_fore") - p_.W("L_arm"), (Vector((0, 0, -1)) + lev * 0.12 + f_ * 0.15).normalized())
        p_.aim("L_fore", p_.W("L_hand") - p_.W("L_fore"), (Vector((0, 0, -1)) + f_ * 0.55).normalized())   # pěst před stehnem mimo sukni: ruka v látce ji simulace zvedne
    elif ZBR_POZY.get(pn, {}).get("L", ("",))[0] == "scutum":       # boj (rekonstruktéři): horní hrana štítu pod očima, pěst ve stejném směru od hrudi
        p_ = Poser(rig, MAP); M = rig.matrix_world
        oci = (M @ rig.pose.bones["head"].head).z + 0.09; hrud = p_.W("chest"); w = p_.W("L_hand") - hrud; w.z = 0
        T = hrud + w.normalized() * max(0.25, min(0.45, w.length)); T.z = oci - 0.03 - DELKA["scutum"] / 2
        _ik(p_, "L", T)
        print("INFO", pn, "pest z", round(T.z, 2), "horni hrana stitu", round(T.z + DELKA["scutum"] / 2, 2), "oci", round(oci, 2), flush=True)
    R_ = ZBR_POZY.get(pn, {}).get("R")
    if R_ and R_[0] == "pilum" and pn == "hod_B":   # úchop: dřík leží v dlani podél kloubů, zápěstí se natočí k pilu
        X = (_smer_hodu(pn) + Vector((0, 0, R_[1]))).normalized()      # (operátor: pěst napříč dříku = „neúchop“, ohnuté zápěstí = „zlomené“)
        M = rig.matrix_world; P = rig.pose.bones; f = (M @ P["wrist.R"].head - M @ P["lowerarm01.R"].head).normalized()
        Xp = (X - f * X.dot(f)).normalized()                        # jen otočení kolem předloktí: loket postavil Poser.naprah kolmo na pilum
        p_ = Poser(rig, MAP); _, osa, _ = _ruka("R"); osa = osa if osa.dot(Xp) >= 0 else -osa
        p_.rot("R_hand", osa.rotation_difference(Xp).to_matrix())
        _, osa, _ = _ruka("R"); osa = osa if osa.dot(X) >= 0 else -osa; p_.rot("R_hand", osa.rotation_difference(X).to_matrix())   # zbytek = úklon zápěstí do 20°
        ruka = (M @ P["finger3-1.R"].head - M @ P["wrist.R"].head).normalized(); o2 = _ruka("R")[1]
        print("INFO", pn, "ohnuti zapesti deg", round(math.degrees(ruka.angle(f)), 1), "osa pesti k pilu deg", round(math.degrees(min(o2.angle(X), (-o2).angle(X))), 1), flush=True)
    for sd, (d, _) in ZBR_POZY.get(pn, {}).items():
        if d not in ZB: continue
        for pb in rig.pose.bones:
            if pb.name.startswith("finger") and "-" in pb.name and pb.name.endswith("." + sd):
                f_, j_ = (int(x) for x in pb.name[6:].split(".")[0].split("-"))
                pb.rotation_mode = "QUATERNION"; pb.rotation_quaternion = Quaternion(Vector((1, 0, 0)), math.radians(PEST[j_] * (0.6 if f_ == 1 else 1.0)))
    bpy.context.view_layer.update()

def zbr_umisti(pn):
    for z in ZB.values(): z["o"].hide_render = z["o"].hide_viewport = True
    vpred = _vpred(); F = vpred                                          # líc štítu: vodorovně od hrudníku přes levou pěst ven = k nepříteli
    if pn != "stoj_A" and ZBR_POZY.get(pn, {}).get("L", ("",))[0] == "scutum":   # u A stojí štít u boku lícem dopředu
        F = _ruka("L")[0] - rig.matrix_world @ rig.pose.bones["spine03"].head; F.z = 0; F = F.normalized() if F.length > 1e-6 else vpred
    for sd, (d, hrot) in ZBR_POZY.get(pn, {}).items():
        if d not in ZB: continue
        G, osa, n = _ruka(sd); o = ZB[d]["o"]
        if d == "scutum":                                                 # štít svisle
            Z = Vector((0, 0, 1)); Y = -F; X = Y.cross(Z)
        elif hrot == "nahoru":                                            # pilum u nohy svisle hrotem nahoru (předloha A)
            X = Vector((0, 0, 1)); Z = (n - X * n.dot(X)).normalized(); Y = Z.cross(X)
        else:
            if d == "gladius":                                            # bodnutí: čepel prodlužuje předloktí
                X = (G - rig.matrix_world @ rig.pose.bones[f"lowerarm01.{sd}"].head).normalized()
            else:                                                         # hod a běh: hrot tam, kam líc štítu (k nepříteli); osa pěsti je napříč a o směru nerozhodne
                X = ((_smer_hodu(pn) if pn == "hod_B" else F) + Vector((0, 0, hrot))).normalized()   # hod: k cíli, ne podle líce štítu
            Z = (n - X * n.dot(X)).normalized(); Y = Z.cross(X)
        R = Matrix((X, Y, Z)).transposed().to_4x4()
        o.matrix_world = Matrix.Translation(G) @ R @ Matrix.Translation(-ZB[d]["uchop"])
        o.hide_render = o.hide_viewport = False
    bpy.context.view_layer.update()
    _bez_pruniku(pn, F)

def _bvh(d, Mw):
    V, Pf = ZB[d]["kol"]; Mn = np.array(Mw); W = V @ Mn[:3, :3].T + Mn[:3, 3]
    return BVHTree.FromPolygons([tuple(x) for x in W], Pf)

def _bez_pruniku(pn, F):
    # zbraně jsou samostatné objekty, ale stojí jen podle pěsti: tady se nesmí protnout s tělem ani navzájem.
    # Z těla se vynechá pěst a předloktí, které zbraň drží. Štít ustoupí po směru líce, kopí a meč se pootočí kolem pěsti.
    poza = {sd: d for sd, (d, _) in ZBR_POZY.get(pn, {}).items() if d in ZB}
    if not poza: return
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get()); me = ev.to_mesh(); Mb = np.array(body.matrix_world)
    X = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get("co", X); X = X.reshape(-1, 3) @ Mb[:3, :3].T + Mb[:3, 3]
    M = rig.matrix_world; skryj = np.zeros(len(X), bool)
    for sd in poza:
        e_ = np.array(M @ rig.pose.bones[f"lowerarm01.{sd}"].head); g_ = np.array(_ruka(sd)[0])
        ab = g_ - e_; t = np.clip(((X - e_) @ ab) / (ab @ ab), 0, 1); skryj |= np.linalg.norm(X - (e_ + t[:, None] * ab), axis=1) < 0.09
    tb = BVHTree.FromPolygons([tuple(x) for x in X], [p_.vertices[:] for p_ in me.polygons if not skryj[list(p_.vertices)].any()])
    ev.to_mesh_clear()
    if "L" in poza and poza["L"] == "scutum":
        o = ZB["scutum"]["o"]; n_ = 0
        while tb.overlap(_bvh("scutum", o.matrix_world)) and n_ < 25:
            o.matrix_world = Matrix.Translation(F * 0.01) @ o.matrix_world; n_ += 1
        print("INFO", pn, "stit odsunut od tela o cm", n_, flush=True)
    for sd, d in poza.items():
        if d == "scutum": continue
        o = ZB[d]["o"]; M0 = o.matrix_world.copy(); G, osa, n = _ruka(sd)
        prekazky = [tb] + ([_bvh("scutum", ZB["scutum"]["o"].matrix_world)] if "scutum" in poza.values() else [])
        def koliz(Mw):
            b_ = _bvh(d, Mw); return sum(len(x.overlap(b_)) for x in prekazky)
        best = (koliz(M0), 0, None)
        if best[0]:
            for uhel in (5, -5, 10, -10, 15, -15, 20, -20, 25, -25, 30, -30, 40, -40):
                for ax in (n, osa.cross(n)):
                    Mw = Matrix.Translation(G) @ Matrix.Rotation(math.radians(uhel), 4, ax) @ Matrix.Translation(-G) @ M0; k_ = koliz(Mw)
                    if k_ < best[0]: best = (k_, uhel, Mw)
                if best[0] == 0: break
            if best[2] is not None: o.matrix_world = best[2]
        print("INFO", pn, d, "pruniku", best[0], "pootoceno o", best[1], flush=True)
    bpy.context.view_layer.update()
