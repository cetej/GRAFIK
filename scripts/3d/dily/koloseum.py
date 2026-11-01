"""Koloseum z dílů podle pramenů: python scripts/3d/dily/koloseum.py > scripts/3d/dily/koloseum.json

Řez po patrech: rekonstrukční řez, který dodal operátor (odečteno po metrech přes síť), a Rosengarten Fig 225. Hypogeum: půdorys
AmphitheatrumFlavium (po metrech přes síť), italské heslo (ústřední chodba, křivé chodby, 80 výtahů), anglické (dvě patra). Pod hledištěm je prostor:
tenká deska pod stupni, radiální stěny a schodiště, ne plný klín. Rozměry mimo fakta jsou řád metrů. Popis je generovaný, aby se
opakující se patra psala jednou a dala se změnit na jednom místě. Řez v obraze vede typickým polem se schodištěm.
"""
import json
import sys

A, B = 94.0, 77.75      # poloosy vnějšího obrysu: 188 × 155,5 m
AA, AB = 43.0, 27.0     # aréna: 86 × 54 m (italské heslo), jiné zdroje 83 × 48
AXES = [A, B]
ARENA = [AA, AB]
BOTTOM = -13.0          # platea in tufo asi 13 m (italské heslo, německé uvádí 7 m)
HYP = -6.0              # dno hypogea: odhad, zdroje hloubku neuvádějí
WALL_TOP = -0.6         # koruna zdí hypogea, na ní leží trámy podlahy arény
TOP = 48.5
CORNICE = (10.5, 23.0, 35.2)    # římsy fasády
FLOOR_2, FLOOR_3, FLOOR_4, FLOOR_5 = 13.2, 25.2, 34.0, 39.5     # podlahy uvnitř, římsa je níž: nad ní je sokl dalšího patra
EDGE = -51.0            # okraj arény jako odsazení od fasády
# prstence od fasády dovnitř: fasáda, ochoz 1, prstenec 2, ochoz 2, prstenec 3
RING_1, WALK_1, RING_2, WALK_2, RING_3 = -2.4, -7.4, -9.4, -14.4, -16.4

parts = []


def add(typ, nazev, **fields):
    parts.append({"typ": typ, "nazev": nazev, **fields})


def ring(name, outer, inner, z0, z1, material, axes=AXES, **fields):
    add("prstenec", name, osy=axes, profil=[[inner, z0], [outer, z0], [outer, z1], [inner, z1]], material=material, **fields)


def row(name, lo, hi, step=(0, 0, 0), count=1, material="cihla", mirror=("x", "y")):
    add("rada", name, od=list(lo), do=list(hi), krok=list(step), pocet=count, zrcadlo=list(mirror), material=material)


def walls(name, profile, count, thick, phase=0.0, material="travertin", axes=AXES, shift=0.0):
    add("pricky", name, osy=axes, profil=[list(p) for p in profile], pocet=count, tloustka=thick, faze=phase, posun=shift, material=material)


# -- základ a terasa ---------------------------------------------------------------------------------------------------
ring("zaklad", 0.0, EDGE, BOTTOM, 0.0, "tuf", rez="tmava")
add("disk", "zaklad_pod_arenou", osy=ARENA, z0=BOTTOM, z1=HYP, material="beton", rez="tmava")
ring("zemina", 20.0, 0.0, BOTTOM, -0.35, "zemina", okoli=True, rez="kamen")
ring("terasa", 20.0, 0.0, -0.35, 0.0, "travertin", okoli=True)
add("sloupy", "kamenne_sloupky", osy=AXES, odsazeni=18.0, pocet=80, z0=0.0, d=0.7, drik=3.2, rad="hladky", material="travertin", okoli=True)
add("prstenec", "stupne_paty", osy=AXES, profil=[[0.0, 0.0], [1.6, 0.0], [1.6, 0.3], [0.8, 0.3], [0.8, 0.6], [0.0, 0.6]], material="travertin", okoli=True)

# -- hypogeum podle půdorysu: rovné řady cel podél hlavní osy, příčná chodba na malé ose, dvě křivé zdi, volné pilíře, zubatý okraj ----------
X0 = 1.6                # příčná chodba na malé ose: řady začínají tady
ring("hypogeum_obvod", 0.0, -1.2, HYP, WALL_TOP, "tuf", ARENA)
# vnitřní řady: 12 cel × 4 = 48 výtahů, ústřední chodba |y| < 1
INNER_PITCH, INNER_N = 2.1, 12
INNER_END = X0 + INNER_PITCH * INNER_N + 0.5
row("stred_zed", (X0, 5.6, HYP), (INNER_END, 6.4, WALL_TOP))
row("stred_pricky", (X0, 1.0, HYP), (X0 + 0.5, 5.6, WALL_TOP), (INNER_PITCH, 0, 0), INNER_N + 1)
row("stred_hlavy", (X0 - 0.25, 1.0, HYP), (X0 + 0.75, 1.4, WALL_TOP), (INNER_PITCH, 0, 0), INNER_N + 1)
# vnější řady: 8 cel × 4 = 32 výtahů, dohromady 80 jako v italském hesle; na konci větší komora
OUTER_PITCH, OUTER_N, OUTER_END = 2.0, 8, 22.0
row("bok_zed_vnitrni", (X0, 9.2, HYP), (OUTER_END, 9.8, WALL_TOP))
row("bok_zed_vnejsi", (X0, 12.0, HYP), (OUTER_END, 12.6, WALL_TOP))
row("bok_pricky", (X0, 9.8, HYP), (X0 + 0.45, 12.0, WALL_TOP), (OUTER_PITCH, 0, 0), OUTER_N + 1)
row("bok_konec", (OUTER_END - 0.5, 9.8, HYP), (OUTER_END, 12.0, WALL_TOP))
# dveře z cel do chodeb, ve dvou patrech
for level, z0, height in (("dole", HYP, 2.3), ("nahore", -2.8, 1.9)):
    add("otvory", f"dvere_stred_{level}", cile=["stred_zed"], stred=[X0 + 0.5 + (INNER_PITCH - 0.5) / 2, 6.0, z0], krok=[INNER_PITCH, 0], pocet=INNER_N, smer="y", sirka=1.0, vyska=height, hloubka=1.4, zrcadlo=["x", "y"])
    add("otvory", f"dvere_bok_{level}", cile=["bok_zed_vnitrni", "bok_zed_vnejsi"], stred=[X0 + 0.45 + (OUTER_PITCH - 0.45) / 2, 10.9, z0], krok=[OUTER_PITCH, 0], pocet=OUTER_N, smer="y", sirka=0.9, vyska=height, hloubka=4.2, zrcadlo=["x", "y"])
# křížové pilíře na konci ústřední chodby
row("osa_kriz_a", (29.6, 1.2, HYP), (30.4, 3.8, WALL_TOP), (4.75, 0, 0), 3, "tuf")
row("osa_kriz_b", (28.8, 2.1, HYP), (31.2, 2.9, WALL_TOP), (4.75, 0, 0), 3, "tuf")
# dvě křivé zdi z tufových kvádrů, přerušené příčnou chodbou a na koncích
E1, E2 = [42.5, 20.5], [34.5, 17.2]
ring("krivka_vnejsi", 0.0, -0.8, HYP, WALL_TOP, "tuf", E1)
ring("krivka_vnitrni", 0.0, -0.8, HYP, WALL_TOP, "tuf", E2)
add("vyrez", "pricna_chodba", cile=["krivka_vnejsi", "krivka_vnitrni"], kvadr={"od": [-X0, -60, -7], "do": [X0, 60, 1]})
add("vyrez", "konce_vnejsi", cile=["krivka_vnejsi"], kvadr={"od": [-60, -2.2, -7], "do": [60, 2.2, 1]})
add("vyrez", "konce_vnitrni", cile=["krivka_vnitrni"], kvadr={"od": [-60, -6.4, -7], "do": [60, 6.4, 1]})
add("arkady", "pruchody_vnejsi", cil="krivka_vnejsi", osy=E1, odsazeni=[-1.2, 0.4], z0=HYP, vyska=2.8, sirka=1.5, pocet=24, faze=0.25)
add("arkady", "pruchody_vnitrni", cil="krivka_vnitrni", osy=E2, odsazeni=[-1.2, 0.4], z0=HYP, vyska=2.8, sirka=1.5, pocet=20, faze=0.25)
# volné pilíře a zubatý okraj
walls("volne_pilire", [(-0.5, HYP), (0.5, HYP), (0.5, WALL_TOP), (-0.5, WALL_TOP)], 44, 1.0, 0.0, "tuf", [41.5, 24.0])
walls("zuby_dlouhe", [(-3.4, HYP), (0.0, HYP), (0.0, WALL_TOP), (-3.4, WALL_TOP)], 44, 0.8, 0.5, "cihla", ARENA)
walls("zuby_kratke", [(-1.9, HYP), (0.0, HYP), (0.0, WALL_TOP), (-1.9, WALL_TOP)], 44, 2.6, 0.0, "tuf", ARENA)
# dřevěné pavlače dělí podzemí na dvě patra
row("pavlac_stred", (X0, 6.4, -3.05), (OUTER_END, 9.2, -2.8), material="drevo")
row("pavlac_bok", (X0, 12.6, -3.05), (15.0, 15.5, -2.8), material="drevo")
# výtahy v celách
add("zdvihadla", "vytahy_stred", stred=[X0 + 0.5 + (INNER_PITCH - 0.5) / 2, 3.4], krok=[INNER_PITCH, 0], pocet=INNER_N, zrcadlo=["x", "y"], z0=HYP, z1=WALL_TOP, sirka=1.25, delka=1.5, material="drevo")
add("zdvihadla", "vytahy_bok", stred=[X0 + 0.45 + (OUTER_PITCH - 0.45) / 2, 10.9], krok=[OUTER_PITCH, 0], pocet=OUTER_N, zrcadlo=["x", "y"], z0=HYP, z1=WALL_TOP, sirka=1.15, delka=1.5, material="drevo")
# tunely z hypogea pod hledištěm ven, servisní chodba pod podiem
add("otvory", "tunel_hlavni", cile=["zaklad", "hypogeum_obvod", "zemina"], stred=[-73.0, 0.0, HYP], smer="x", sirka=4.2, vyska=4.0, hloubka=62.0, zrcadlo=["x"])
add("otvory", "tunel_cisarsky", cile=["zaklad", "hypogeum_obvod"], stred=[0.0, -51.5, HYP], smer="y", sirka=3.6, vyska=3.6, hloubka=51.0, zrcadlo=["y"])
add("ochoz", "galerie_pod_podiem", cile=["zaklad"], osy=AXES, od=-50.0, do=-46.8, z0=HYP, vyska=4.4)
# podlaha arény: trámy, prkna, písek, poklopy výtahů
row("tramy", (-44.0, -28.0, WALL_TOP), (-43.6, 28.0, -0.25), (1.6, 0, 0), 55, "drevo", ())
add("dutina", "tramy_orez", cile=["tramy"], osy=ARENA, profil=[[-0.1, -1.0], [20.0, -1.0], [20.0, 0.2], [-0.1, 0.2]])
add("disk", "arena_podlaha", osy=ARENA, z0=-0.25, z1=0.0, material="drevo")
add("disk", "arena_pisek", osy=ARENA, z0=0.0, z1=0.12, material="pisek")
row("poklopy_stred", (X0 + 0.65, 2.75, 0.12), (X0 + 1.95, 4.05, 0.15), (INNER_PITCH, 0, 0), INNER_N, "drevo")
row("poklopy_bok", (X0 + 0.6, 10.25, 0.12), (X0 + 1.85, 11.55, 0.15), (OUTER_PITCH, 0, 0), OUTER_N, "drevo")

# -- hlediště: tenké desky se stupni, pod nimi je prostor ----------------------------------------------------------------
PRIMUM, IMMUM, SUMMUM = "maenianum_primum", "secundum_immum", "secundum_summum"
SLAB = 1.3
SEATS = ((PRIMUM, -46.6, -37.2, 7.0, 13.6, 18), (IMMUM, -35.6, -18.0, 15.6, 27.0, 30), (SUMMUM, -16.4, -10.2, 33.4, 39.3, 12))
ring("zed_areny", EDGE, EDGE + 1.0, 0.0, 3.8, "mramor")
ring("panely_podia", EDGE - 0.04, EDGE, 0.5, 3.3, "freska")
add("arkady", "mezery_panelu", cil="panely_podia", osy=AXES, odsazeni=[EDGE - 0.1, EDGE + 0.04], z0=0.0, vyska=5.0, sirka=0.5, pocet=60, tvar="obdelnik", ref=EDGE)
add("hlediste", "podium", osy=AXES, od=-50.3, do=-46.6, z0=4.0, z1=6.6, stupnu=4, tloustka=1.0, material="mramor")
for name, od, do, z0, z1, steps in SEATS:
    add("hlediste", name, osy=AXES, od=od, do=do, z0=z0, z1=z1, stupnu=steps, tloustka=SLAB, material="mramor")
add("prstenec", "balteus_prvni", osy=AXES, profil=[[-37.4, 12.2], [-35.6, 14.2], [-35.6, 15.6], [-36.3, 15.6], [-36.3, 14.8], [-37.4, 14.8]], material="mramor")
add("prstenec", "zed_soch", osy=AXES, profil=[[-18.0, 25.7], [RING_3, 25.7], [RING_3, 33.5], [-18.3, 33.5], [-18.3, 33.0], [-18.0, 33.0]], material="travertin")


def under(d):
    """Spodek hlediště v odsazení d."""
    if d >= -35.6:
        return 15.6 + (27.0 - 15.6) * (d + 35.6) / 17.6 - SLAB
    return 7.0 + (13.6 - 7.0) * (d + 46.6) / 9.4 - SLAB


# radiální stěny pod hledištěm; v polích mezi nimi je vidět dál na další stěnu, jako v řezu
UNDER = [(-50.0, 0.0), (RING_3, 0.0), (RING_3, under(RING_3) + 0.3), (-35.6, under(-35.6) + 0.3), (-37.2, under(-37.2) + 0.3), (-46.6, under(-46.6) + 0.3), (-50.0, 3.2)]
walls("stena_pod_hledistem", UNDER, 80, 1.0, 0.5)
for name, od, do, z0, height in (("chodba_1", -22.0, -17.4, 0.0, 6.0), ("chodba_2", -29.0, -24.4, 0.0, 6.0), ("chodba_3", -36.0, -31.2, 0.0, 9.5), ("chodba_4", -43.0, -38.0, 0.0, 4.6),
                                 ("chodba_1_nahore", -22.0, -17.4, FLOOR_2, 5.5), ("chodba_2_nahore", -29.0, -24.4, FLOOR_2, 3.8)):
    add("ochoz", name, cile=["stena_pod_hledistem"], osy=AXES, od=od, do=do, z0=z0, vyska=height)
# soustředné zdi mezi chodbami až pod hlediště, v každém poli dveře; pole se schodištěm jsou otevřená
for name, inner, outer in (("zed_4", -24.2, -22.6), ("zed_5", -31.0, -29.6), ("zed_6", -37.6, -36.2), ("zed_7", -44.4, -43.2)):
    add("prstenec", name, osy=AXES, profil=[[inner, 0.0], [outer, 0.0], [outer, under(outer) + 0.3], [inner, under(inner) + 0.3]], material="travertin")
    add("arkady", f"dvere_{name}", cil=name, osy=AXES, odsazeni=[inner - 0.3, outer + 0.3], z0=0.0, vyska=4.6, sirka=2.4, pocet=40, faze=0.5, ref=0.0)
    add("arkady", f"schodiste_{name}", cil=name, osy=AXES, odsazeni=[inner - 0.3, outer + 0.3], z0=0.0, vyska=40.0, sirka=3.0, pocet=40, tvar="obdelnik", ref=0.0)

# -- obvodové prstence a klenby ochozů: tři patra, dva ochozy nad sebou ---------------------------------------------------
ring("fasada", 0.0, RING_1, 0.0, TOP, "travertin")
ring("prstenec_2", WALK_1, RING_2, 0.0, FLOOR_5, "travertin")
ring("prstenec_3", WALK_2, RING_3, 0.0, FLOOR_4, "travertin")
ARCH_LEVELS = ((0.0, 7.4), (FLOOR_2 - 0.2, 6.6), (FLOOR_3, 6.4))
for level, (z0, height) in enumerate(ARCH_LEVELS, 1):
    add("arkady", f"oblouky_{level}", cil="fasada", osy=AXES, odsazeni=[RING_1 - 0.4, 0.4], z0=z0, vyska=height, sirka=4.2, pocet=80, ref=0.0)
    add("arkady", f"oblouky_prstenec_2_{level}", cil="prstenec_2", osy=AXES, odsazeni=[RING_2 - 0.4, WALK_1 + 0.4], z0=z0, vyska=height, sirka=4.2, pocet=80, ref=0.0)
    add("arkady", f"oblouky_prstenec_3_{level}", cil="prstenec_3", osy=AXES, odsazeni=[RING_3 - 0.4, WALK_2 + 0.4], z0=z0, vyska=height, sirka=3.4, pocet=80, ref=0.0)
add("arkady", "okna_atiky", cil="fasada", osy=AXES, odsazeni=[RING_1 - 0.4, 0.4], z0=37.6, vyska=2.4, sirka=1.6, pocet=40, tvar="obdelnik", ref=0.0)
add("arkady", "okna_prstenec_2", cil="prstenec_2", osy=AXES, odsazeni=[RING_2 - 0.4, WALK_1 + 0.4], z0=34.6, vyska=3.0, sirka=2.2, pocet=40, tvar="obdelnik", ref=0.0)
for level, (z0, z1, crown, floor) in enumerate(((7.4, FLOOR_2, 12.0, FLOOR_2), (19.8, FLOOR_3, 24.2, FLOOR_3), (32.0, FLOOR_4, 33.4, FLOOR_4)), 1):
    name = f"strop_{level}"
    ring(name, RING_1, RING_3, z0, floor, "beton")
    for walk, outer, inner in (("a", RING_1, WALK_1), ("b", RING_2, WALK_2)):
        add("ochoz", f"klenba_{level}{walk}", cile=[name], osy=AXES, od=inner, do=outer, z0=crown - 5.5, vyska=5.5)
ring("strop_4", RING_1, -10.6, 38.6, FLOOR_5, "beton")
ring("antresola", RING_2, -17.6, 20.2, 20.7, "beton")       # úroveň 2a: mezipatro ve vnitřním ochozu
# podesty schodišť
ring("podesta_1", -24.8, -31.0, 7.4, 8.0, "beton")
ring("podesta_2", -26.0, -31.0, 12.6, FLOOR_2, "beton")
ring("podesta_2b", RING_3, -17.6, 12.6, FLOOR_2, "beton")


def flight(name, d0, z0, d1, z1, steps, plaster=True, count=40, width=2.6, thick=0.9):
    """Schodiště v poli jako díl se stupni; omítka na stěnách pole je pás rovnoběžný se stupni, stěny mají tloušťku 1 m."""
    points = []
    for i in range(steps):
        a, b, z = d0 + (d1 - d0) * i / steps, d0 + (d1 - d0) * (i + 1) / steps, z0 + (z1 - z0) * (i + 1) / steps
        points += [(a, z), (b, z)]
    points += [(d1, max(0.0, z1 - thick)), (d0, max(0.0, z0 - thick))]
    walls(name, points, count, width, 0.0)
    if plaster:
        band = [(d0, z0 + 0.1), (d1, z1 + 0.1), (d1, z1 + 2.8), (d0, z0 + 2.8)]
        walls(f"{name}_omitka_a", band, 40, 0.05, 0.25, "omitka", shift=-0.53)
        walls(f"{name}_omitka_b", band, 40, 0.05, 0.75, "omitka", shift=0.53)


flight("schody_1", -16.8, 0.0, -25.0, 8.0, 24)       # z ochozu dovnitř na podestu
flight("schody_2", -25.0, 8.0, -17.6, FLOOR_2, 16)   # zpátky ven na podlahu 2. patra
flight("schody_3", -29.0, FLOOR_2, -17.8, 20.7, 22)  # do mezipatra 2a
flight("schody_4", -16.0, 20.7, -10.4, FLOOR_3, 14, plaster=False)
flight("schody_5", -9.8, FLOOR_3, -14.2, 32.0, 20, plaster=False)
flight("schody_6", -2.8, FLOOR_4, -7.2, 38.6, 14, plaster=False, count=40)
flight("schody_k_podiu", -38.4, 0.2, -45.8, 6.4, 18)
for name, od, do, z0, height, in (("dado_chodba", -36.0, -31.2, 0.0, 2.6),):
    band = [(od, z0), (do, z0), (do, z0 + height), (od, z0 + height)]
    walls(f"{name}_a", band, 40, 0.05, 0.25, "omitka", shift=-0.53)
    walls(f"{name}_b", band, 40, 0.05, 0.75, "omitka", shift=0.53)

# -- výstupy na hlediště s nízkým zábradlím, uličky ------------------------------------------------------------------------
for name, seat, centre, phase in (("primum", PRIMUM, -43.5, 0.0), ("immum", IMMUM, -28.0, 0.5), ("summum", SUMMUM, -13.0, 0.0)):
    add("sachty", f"vystup_{name}", cile=[seat], osy=AXES, odsazeni=centre, ref=0.0, pocet=40, faze=phase, sirka=1.9, delka=3.2, z=[0.0, 42.0])
    od, do, z0, z1 = next((s[1], s[2], s[3], s[4]) for s in SEATS if s[0] == seat)
    level = [z0 + (z1 - z0) * (d - od) / (do - od) for d in (centre - 1.6, centre + 1.6)]
    rail = [(centre - 1.6, level[0] - 0.3), (centre + 1.6, level[1] - 0.3), (centre + 1.6, level[1] + 0.7), (centre - 1.6, level[0] + 0.7)]
    walls(f"zabradli_{name}_a", rail, 40, 0.22, phase, "freska", shift=-1.06)
    walls(f"zabradli_{name}_b", rail, 40, 0.22, phase, "freska", shift=1.06)
for name, od, do, z0, z1, steps in SEATS:
    add("schodiste", f"ulicky_{name}", cile=[name], osy=AXES, od=od, do=do, z0=z0 - 0.2, z1=z1 - 0.2, sirka=1.0, pruchod=4.0, stupnu=steps * 2, pocet=76, faze=0.25)

# -- fasáda: řády, soklová pásma, římsy ------------------------------------------------------------------------------------
for name, order, z0, shaft, d in (("polosloupy_1", "dorsky", 0.3, 8.2, 1.05), ("polosloupy_2", "ionsky", FLOOR_2 - 0.3, 7.0, 0.95), ("polosloupy_3", "korintsky", FLOOR_3 - 0.1, 6.6, 0.9)):
    add("sloupy", name, osy=AXES, odsazeni=0.05, pocet=80, faze=0.5, z0=z0, d=d, drik=shaft, rad=order, material="travertin")
add("sloupy", "pilastry_atiky", osy=AXES, odsazeni=0.02, pocet=80, faze=0.5, z0=CORNICE[2] + 0.4, d=0.8, drik=10.2, rad="korintsky", material="travertin")
for i, z in enumerate(CORNICE, 1):
    add("prstenec", f"rimsa_{i}", osy=AXES, profil=[[RING_1, z - 0.9], [0.5, z - 0.9], [0.65, z - 0.5], [0.95, z], [0.65, z + 0.35], [RING_1, z + 0.35]], material="travertin")
for i, (z0, z1) in enumerate(((CORNICE[0] + 0.35, FLOOR_2 - 0.2), (CORNICE[1] + 0.35, FLOOR_3 - 0.05)), 2):
    ring(f"sokl_{i}", 0.25, RING_1, z0, z1, "travertin")
add("prstenec", "korunni_rimsa", osy=AXES, profil=[[RING_1, TOP - 1.2], [0.7, TOP - 1.2], [1.1, TOP - 0.3], [0.7, TOP], [RING_1, TOP]], material="travertin")
walls("konzoly", [(0.0, TOP - 7.0), (0.95, TOP - 7.0), (0.95, TOP - 6.5), (0.0, TOP - 6.2)], 240, 0.6)
add("sloupy", "stozary_velaria", osy=AXES, odsazeni=0.55, pocet=240, z0=TOP - 6.5, d=0.5, drik=15.0, rad="stozar", material="drevo")

# -- nahoře: sochy v arkádách, sochy v aedikulách na zdi nad hledištěm, kolonáda s dřevěnými sedadly ---------------------------
add("sochy", "sochy_patro_2", osy=AXES, odsazeni=-1.2, pocet=80, z0=FLOOR_2 - 0.2, vyska=3.8, material="mramor")
add("sochy", "sochy_patro_3", osy=AXES, odsazeni=-1.2, pocet=80, z0=FLOOR_3, vyska=3.6, material="mramor")
add("arkady", "dvere_zdi_soch", cil="zed_soch", osy=AXES, odsazeni=[-18.5, RING_3 + 0.3], z0=27.4, vyska=3.0, sirka=1.5, pocet=20, tvar="obdelnik", ref=0.0)
add("sochy", "aedikuly", osy=AXES, odsazeni=-18.0, pocet=80, preskoc=4, aedikula=True, z0=27.5, vyska=3.0, material="mramor")
add("hlediste", "summum_in_ligneis", osy=AXES, od=-9.4, do=RING_1, z0=39.9, z1=45.2, z_dno=FLOOR_5, stupnu=12, tloustka=0.35, material="drevo")
walls("kozy_a", [(-9.2, FLOOR_5), (-8.6, FLOOR_5), (-2.6, 45.0), (-3.2, 45.0)], 40, 0.3, 0.0, "drevo")
walls("kozy_b", [(-3.2, FLOOR_5), (-2.6, FLOOR_5), (-8.6, 40.5), (-9.2, 40.5)], 40, 0.3, 0.0, "drevo")
ring("pas_omitka", RING_1, RING_1 - 0.05, 45.1, 45.8, "omitka")
add("sloupy", "kolonada", osy=AXES, odsazeni=-10.0, pocet=112, z0=FLOOR_5, d=0.72, drik=5.7, rad="korintsky", material="mramor")
add("prstenec", "strop_kolonady", osy=AXES, profil=[[-10.8, 46.5], [RING_1, 46.5], [RING_1, TOP], [-10.5, TOP], [-11.0, 47.6]], material="mramor")

# -- oživení: plachty jako ukázka v jednom výseku, lidé ------------------------------------------------------------------
add("plachty", "velarium", osy=AXES, od=-40.0, do=0.55, z_dov=38.0, z_ven=TOP + 6.0, azimut=[10.0, 62.0], pocet=13, prohyb=2.2, lana=[-38.0, 170.0])
BACK = [-40.0, 170.0]
for name, od, do, z0, z1, count, height in (("lide_podium", -50.0, -47.0, 4.3, 6.5, 110, 1.2), ("lide_primum", -46.2, -37.6, 7.4, 13.2, 400, 1.15), ("lide_immum", -35.2, -18.6, 16.0, 26.7, 400, 1.15),
                                            ("lide_summum", -16.0, -10.6, 33.9, 39.0, 300, 1.15), ("lide_ligneis", -9.0, -3.0, 40.3, 44.8, 240, 1.15)):
    add("lide", name, osy=AXES, od=od, do=do, z0=z0, z1=z1, pocet=count, azimut=BACK, vyska=height)
add("lide", "gladiatori", osy=ARENA, od=-20.0, do=-3.0, z0=0.12, pocet=14, azimut=[-30.0, 150.0], vyska=1.8)
add("lide", "lide_venku", osy=AXES, od=3.0, do=17.0, z0=0.0, pocet=170, azimut=[[100.0, 195.0], [-100.0, -5.0]], vyska=1.75)
for name, od, do, z0 in (("lide_ochoz_1", -6.8, -3.0, 0.0), ("lide_ochoz_1b", -13.8, -10.0, 0.0), ("lide_ochoz_2", -6.8, -3.0, FLOOR_2), ("lide_ochoz_3", -6.8, -3.0, FLOOR_3)):
    add("lide", name, osy=AXES, od=od, do=do, z0=z0, pocet=70, azimut=[[172.0, 200.0], [262.0, 290.0]], vyska=1.75)
add("lide", "lide_chodba", osy=ARENA, od=-26.3, do=-26.0, z0=HYP, pocet=40, azimut=[0.0, 360.0], vyska=1.75)
add("lide", "lide_pavlac", osy=ARENA, od=-19.3, do=-18.6, z0=-2.8, pocet=30, azimut=[0.0, 360.0], vyska=1.75)

ANCHORS = [{"nazev": k, "xyz": v} for k, v in {
    "k_velarium": [62.0, 40.0, 49.0], "k_stozary": [-47.0, 66.5, 55.0], "k_ligneis": [-16.0, 64.0, 43.0], "k_aedikula": [-10.0, 59.0, 30.0],
    "k_vstup": [-A * 0.72, -B * 0.695, 3.0], "k_socha": [0.0, -B + 1.2, FLOOR_2 + 2.0], "k_sloupek": [A + 5.0, -60.0, 1.5], "k_arena": [20.0, 8.0, 0.12],
    "k_hypogeum": [-14.0, 0.0, -3.0], "k_zaklad": [-68.0, 0.0, -9.0], "k_pilire": [0.0, -66.0, 1.0],
    "r_podium": [-45.0, 0.0, 6.0], "r_primum": [-52.0, 0.0, 10.0], "r_immum": [-67.0, 0.0, 20.8], "r_summum": [-81.0, 0.0, 36.0], "r_ligneis": [-88.0, 0.0, 41.5], "r_kolonada": [-84.0, 0.0, 47.0],
    "r_klenba": [-89.1, 0.0, 11.0], "r_vomitorium": [-59.0, 0.0, 4.0], "r_schody": [-75.0, 0.0, 3.5], "r_zaklad": [-60.0, 0.0, -9.0], "r_tunel": [-62.0, 0.0, -4.0],
    "h_vytah": [X0 + 1.3, -3.4, -1.0], "h_cela": [10.0, -10.9, -0.6], "h_stredni": [20.0, 0.0, -5.5], "h_krivka": [-25.0, -13.5, -0.6], "h_pilir": [-37.0, -8.0, -0.6], "h_tunel": [-43.0, 0.0, -5.0], "h_zub": [32.0, -18.5, -0.6],
    "f_dorsky": [3.4, -B - 0.5, 5.0], "f_ionsky": [3.4, -B - 0.5, 17.0], "f_korintsky": [3.4, -B - 0.5, 28.5], "f_pilastr": [3.4, -B - 0.5, 41.0], "f_stozar": [8.3, -B - 0.9, TOP + 4.0],
}.items()]

spec = {"nazev": "Koloseum", "dim": {"length": 188.0, "width": 155.5, "height": TOP}, "dily": parts,
        "kotvy": ANCHORS,
        "zdroje": {"délka 188, šířka 156, výška 48,5": "fakta f3, f5 a italské heslo", "aréna 86 × 54": "italské heslo, anglické 83 × 48",
                   "základ asi 13 m z tufu": "italské heslo, německé uvádí 7 m", "dno hypogea -6 m": "odhad",
                   "skladba hypogea (řady cel, křivé zdi, pilíře)": "půdorys AmphitheatrumFlavium, po metrech", "80 výtahů": "italské heslo; rozdělení 48 + 32 je odhad podle půdorysu",
                   "dvě patra hypogea": "anglické heslo", "úrovně, schodiště, klenby, zeď se sochami": "rekonstrukční řez od operátora a Rosengarten Fig 225, řád metrů",
                   "dřevěná sedadla a kolonáda nahoře": "italské heslo (maenianum summum in ligneis), řez", "sochy v arkádách": "anglické heslo", "240 stožárů": "anglické heslo",
                   "kamenné sloupky 18 m od stavby": "anglické heslo; počet 80 a výška jsou odhad",
                   "plachty a lidé": "oživení obrazu, tvar plachet podle anglického hesla (síť lan, otvor uprostřed), rozmístění vymyšlené"}}
sys.stdout.reconfigure(encoding="utf-8")
print(json.dumps(spec, ensure_ascii=False, indent=1))
