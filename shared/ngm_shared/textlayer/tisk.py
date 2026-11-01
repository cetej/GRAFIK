"""Mazání popisků na tištěné mapě, kde je černá jen písmo (sken starší mapy, areál přes celou plochu).

Štětec PhotoCraftu maže celý pás kolem popisku: na mapě irbisů (2026-11-01) vymazal kusy areálu a hranic a křivé
popisky minul. Tady se maže jen pixel písma a plocha i hranice pod ním zůstanou; tiskový rastr se do vymazaného
místa vrátí z okolí. Křivý popisek určuje `path` (lomená čára účaří v pixelech originálu), značky chrání
`markers` (rámečky hvězd, teček, kót).
"""
from __future__ import annotations

import cv2
import numpy as np

from ngm_shared.textlayer import pcraft

DARK = 75                       # jas, pod kterým je pixel písmo (hranice a horstva na mapě irbisů jsou světlejší)
INK_MAX = 90                    # popisek s kanálem aspoň takhle světlým není černá tiskařská barva
OUTSIDE_MAX = 0.2              # víc černé mimo popisky než tenhle podíl: černé není jen písmo
GRAIN_SIGMA = 3.0               # co je jemnější než tohle, je tiskový rastr


def _gray(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)


def _corridor(shape: tuple, elements: list[dict]) -> np.ndarray:
    """Kde smí být písmo: rámeček popisku, u křivého pás kolem jeho účaří."""
    out = np.zeros(shape, np.uint8)
    for el in elements:
        x0, y0, x1, y1 = [int(v) for v in el["box"]]
        line = el.get("erase_path") or el.get("path")       # původní křivka, když česká leží jinde
        if line:
            pts = np.array(line, np.int32).reshape(-1, 1, 2)
            cv2.polylines(out, [pts], False, 1, thickness=max(8, int(el.get("path_width") or y1 - y0)))
        else:
            pad = max(4, shape[1] // 250)       # rámeček od Claude bývá o kus tahu menší než písmo
            out[max(y0 - pad, 0):y1 + pad, max(x0 - pad, 0):x1 + pad] = 1
    return out > 0


def only_ink(img: np.ndarray, elements: list[dict]) -> bool:
    """Je černá jen písmo? Všechny popisky černé a mimo ně jen drobnost (značky, měřítko). Reliéf a fotka tudy
    nejdou: Everest má barevné i bílé popisky a poměr tmavých pixelů stejný jako sken."""
    if any(max(pcraft.st.hex_to_rgb(el["color"])) >= INK_MAX for el in elements):
        return False
    dark = _gray(img) < DARK
    inside = _corridor(dark.shape, elements)
    return bool(int((dark & inside).sum()) and (dark & ~inside).sum() < OUTSIDE_MAX * (dark & inside).sum())


def _regrain(img: np.ndarray, filled: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Vrátí do vymazaných míst tiskový rastr: jemná struktura z nejbližšího nedotčeného místa stejné barvy."""
    src = img.astype(np.float32)
    detail = src - cv2.GaussianBlur(src, (0, 0), GRAIN_SIGMA)
    smooth = cv2.GaussianBlur(filled.astype(np.float32), (0, 0), GRAIN_SIGMA)
    out = filled.astype(np.float32)
    H, W = mask.shape
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    for i in range(1, n):
        x, y, w, h = stats[i][:4]
        here = lab[y:y + h, x:x + w] == i
        target = smooth[y:y + h, x:x + w][here].mean(axis=0)
        best, best_err = None, 1e9
        for step in (1, 2, 3):
            for dy in (-h * step, 0, h * step):
                for dx in (-w * step, 0, w * step):
                    a, b = x + dx, y + dy
                    if (dx, dy) == (0, 0) or a < 0 or b < 0 or a + w > W or b + h > H or mask[b:b + h, a:a + w].any():
                        continue
                    err = float(np.abs(smooth[b:b + h, a:a + w][here].mean(axis=0) - target).sum())
                    if err < best_err:
                        best, best_err = (a, b), err
        if best and best_err < 30:
            a, b = best
            out[y:y + h, x:x + w][here] += detail[b:b + h, a:a + w][here]
    return np.clip(out, 0, 255).astype(np.uint8)


def erase(img: np.ndarray, elements: list[dict], markers: list[list[float]]) -> tuple[np.ndarray, list[dict]]:
    """Vymaže pixely písma. Vrací (obraz bez textu, sazbu popisků ve tvaru `pcraft.erase`)."""
    gray = _gray(img)
    keep = np.zeros(gray.shape, np.uint8)
    for x0, y0, x1, y1 in markers:
        keep[max(int(y0), 0):int(y1), max(int(x0), 0):int(x1)] = 1
    ink = (gray < DARK) & _corridor(gray.shape, elements) & (keep == 0)
    # křivý popisek kříží hranice: ty jsou z rozptýlených tiskových bodů, tah písma je souvislý a otevření ho nechá
    k = max(3, 2 * round(img.shape[1] / 1500) + 1)
    bent = _corridor(gray.shape, [el for el in elements if el.get("path")])
    solid = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_OPEN, np.ones((k, k), np.uint8)) > 0
    # zbytky tahů: co je těsně u písma, a osamocené skvrny větší než tiskový bod
    near = cv2.dilate(solid.astype(np.uint8), np.ones((3 * k, 3 * k), np.uint8)) > 0
    n, lab, stats, _ = cv2.connectedComponentsWithStats((ink & bent).astype(np.uint8), connectivity=8)
    spots = np.isin(lab, [i for i in range(1, n) if 3 * k * k <= stats[i][4] <= 40 * k * k])
    ink = (ink & ~bent) | (ink & bent & (solid | near | spots))
    # okraj tahu je ve skenu rozmazaný a má barevný lem z tisku
    grow = max(3, 2 * round(img.shape[1] / 500) + 1)
    mask = cv2.dilate(ink.astype(np.uint8), np.ones((grow, grow), np.uint8))
    mask[keep > 0] = 0
    # doplňuje se z obrazu bez rastru: jednotlivé tiskové body by se roztáhly do barevné mozaiky
    smooth = cv2.medianBlur(cv2.inpaint(img, mask, 5, cv2.INPAINT_TELEA), 2 * round(img.shape[1] / 400) + 1)
    filled = img.copy()
    filled[mask > 0] = cv2.inpaint(smooth, mask, 5, cv2.INPAINT_TELEA)[mask > 0]
    clean = _regrain(img, filled, mask)
    rot_px = pcraft._rot_size(elements, img.shape[1])
    layout = []
    for el in elements:
        el["upright"] = True
        n_src = el["en"].count("\n") + 1
        pitch = rot_px * 1.55 if el["angle"] else (el["box"][3] - el["box"][1]) / n_src
        dx, dy = el.get("offset") or (0, 0)     # popisek, který by se česky srazil se sousedem
        layout.append({"L": pcraft._length(el), "pitch": pitch, "rot_px": rot_px, "curve": None, "plate": None,
                       "center": ((el["box"][0] + el["box"][2]) / 2 + dx, (el["box"][1] + el["box"][3]) / 2 + dy),
                       "protect": keep, "residue": pcraft._dark_left(img, clean, el)})
    return clean, layout
