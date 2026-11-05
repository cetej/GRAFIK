# Profily vorvaně z předloh (operátor 5. 11.: „Stáhni si fotky, kolik potřebuješ a udělej ten model pořádně“), 0 USD:
#   python scripts/3d/vorvan_profily.py
# Bok: kresba NOAA „Sperm whale drawing with skeleton.jpg“ (horní obrázek, public domain) -> hřbet a břicho.
# Shora: letecká fotka NOAA „Sperm whale from above.jpg“ (public domain) -> šířka.
# Předlohy a jejich původ: library/plakaty/vorvan/predlohy/NN.jpg + NN.puvod.json. Výstup scripts/3d/vorvan_profily.json
# (x od špičky hlavy k zářezu ocasní ploutve, vše v podílech délky) a kontrolní obrázky do predlohy/mereni-*.png.
import json
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
DATA = REPO
for up in [REPO, *REPO.parents]:
    if (up / "library" / "plakaty" / "vorvan" / "predlohy").exists():
        DATA = up
        break
REF = DATA / "library" / "plakaty" / "vorvan" / "predlohy"
N = 101   # vzorků po délce


def largest(mask: np.ndarray) -> np.ndarray:
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
    k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    out = (lab == k).astype(np.uint8)
    # díry uvnitř obrysu (světlá místa kresby) zaplnit
    cnts, _ = cv2.findContours(out, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    full = np.zeros_like(out)
    cv2.drawContours(full, cnts, -1, 1, -1)
    return full


def side_profile():
    img = cv2.imread(str(REF / "01.jpg"))
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    top_half = g[: g.shape[0] // 2]                       # horní obrázek je vorvaň s kůží, dole kostra
    mask = largest(cv2.morphologyEx((top_half < 200).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8)))
    cols = np.where(mask.any(0))[0]
    x0, x1 = cols.min(), cols.max()                        # hlava vlevo, ocas vpravo
    rows = []
    for c in range(x0, x1 + 1):
        r = np.where(mask[:, c])[0]
        rows.append((c, r.min(), r.max()))
    rows = np.array(rows, float)
    # ocasní ploutev z boku je tenká čára; zářez = poslední sloupec, kde je tělo ještě vyšší než 3 % délky
    length_px = x1 - x0
    thick = (rows[:, 2] - rows[:, 1]) / length_px
    body_end = x0 + int(np.where(thick > 0.03)[0].max())
    dbg = cv2.cvtColor(mask * 255, cv2.COLOR_GRAY2BGR)
    return rows, x0, x1, body_end, dbg, img


def top_profile():
    img = cv2.imread(str(REF / "17.jpg"))
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    water = np.median(lab[:40, :40].reshape(-1, 3), axis=0)
    dist = np.linalg.norm(lab - water, axis=2)
    mask = largest(cv2.morphologyEx((dist > 22).astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)))
    ys, xs = np.nonzero(mask)
    pts = np.stack([xs, ys], 1).astype(np.float32)
    mean = pts.mean(0)
    _, _, vt = np.linalg.svd(pts - mean, full_matrices=False)
    axis = vt[0]
    # hlava je v horní části snímku (vlevo nahoře)
    if axis[1] > 0:
        axis = -axis
    ang = np.degrees(np.arctan2(axis[1], axis[0]))
    M = cv2.getRotationMatrix2D(tuple(mean), ang + 180, 1.0)
    h, w = mask.shape
    big = max(h, w) * 2
    M[:, 2] += (big / 2 - mean)
    rot = cv2.warpAffine(mask, M, (big, big), flags=cv2.INTER_NEAREST)
    rot_img = cv2.warpAffine(img, M, (big, big))
    cols = np.where(rot.any(0))[0]
    if rot[:, cols.min(): cols.min() + 20].sum() < rot[:, cols.max() - 20: cols.max()].sum():
        rot, rot_img = rot[:, ::-1].copy(), rot_img[:, ::-1].copy()
        cols = np.where(rot.any(0))[0]
    rows = []
    for c in range(cols.min(), cols.max() + 1):
        r = np.where(rot[:, c])[0]
        rows.append((c, r.min(), r.max()))
    return np.array(rows, float), cols.min(), cols.max(), rot, rot_img


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    srows, sx0, sx1, s_end, sdbg, simg = side_profile()
    trows, tx0, tx1, trot, timg = top_profile()
    s_len = s_end - sx0                                   # délka od špičky hlavy k zářezu ploutve
    # osa těla v boku: přímka mezi středem hlavy a středem kořene ocasu, výšky od ní
    t = np.linspace(0, 1, N)
    top = np.interp(sx0 + t * s_len, srows[:, 0], srows[:, 1])
    bot = np.interp(sx0 + t * s_len, srows[:, 0], srows[:, 2])
    mid0 = (top[0] + bot[0]) / 2
    # výška hřbetu a břicha od přímky z prostředka hlavy (podíly délky), kladně nahoru
    ztop = (bot.max() - top) / s_len
    zbot = (bot.max() - bot) / s_len
    # šířka: fotka shora nemá viditelný zářez, kořen ocasu podle délky stejného poměru jako v boku
    t_len = tx1 - tx0
    width = np.array([np.interp(tx0 + ti * t_len, trows[:, 0], trows[:, 2] - trows[:, 1]) for ti in t]) / t_len
    prof = {"zdroj_bok": "predlohy/01.jpg (NOAA, public domain)", "zdroj_shora": "predlohy/17.jpg (NOAA, public domain)",
            "x": t.round(4).tolist(), "hrbet": ztop.round(4).tolist(), "bricho": zbot.round(4).tolist(),
            "sirka": width.round(4).tolist(), "bok_px": [int(sx0), int(s_end), int(sx1)], "shora_px": [int(tx0), int(tx1)]}
    (Path(__file__).with_name("vorvan_profily.json")).write_text(json.dumps(prof, ensure_ascii=False, indent=1), encoding="utf-8")
    # kontrolní obrázky: obrys přes předlohu
    over = simg.copy()
    cnts, _ = cv2.findContours(sdbg[:, :, 0], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(over[: sdbg.shape[0]], cnts, -1, (0, 0, 255), 2)
    cv2.line(over, (int(s_end), 0), (int(s_end), sdbg.shape[0]), (0, 200, 0), 2)
    cv2.imwrite(str(REF / "mereni-bok.png"), over)
    cv2.imwrite(str(REF / "silueta-bok.png"), 255 - sdbg)       # pro lod_check --ref
    over = timg.copy()
    cnts, _ = cv2.findContours(trot, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(over, cnts, -1, (0, 0, 255), 2)
    ys, xs = np.nonzero(trot)
    pad = 30
    cv2.imwrite(str(REF / "mereni-shora.png"), over[ys.min() - pad: ys.max() + pad, xs.min() - pad: xs.max() + pad])
    i = lambda v: int(round(v * (N - 1)))
    print("výška těla / délka max", round(float((ztop - zbot).max()), 3), "u x", round(float(t[np.argmax(ztop - zbot)]), 2))
    print("šířka / délka max", round(float(width.max()), 3), "u x", round(float(t[np.argmax(width)]), 2))
    for x in (0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.6, 0.8, 0.95):
        print(f"x {x:.2f}: hřbet {ztop[i(x)]:.3f} břicho {zbot[i(x)]:.3f} šířka {width[i(x)]:.3f}")


main()
