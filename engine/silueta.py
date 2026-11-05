"""Profil tvora z předloh pro díl `telo` (engine/parts_spec.py), 0 USD, jen OpenCV.

Zobecněno ze `scripts/3d/vorvan_profily.py` (vorvaň 5. 11.): model z jedné fotky (TRELLIS, Hunyuan) si hlavu vymyslí, model
z průřezů podle změřených předloh ne. Z boku se měří hřbet a břicho, shora šířka; obojí po délce v podílech délky, výšky nad
nejnižším bodem břicha. Šířku ber z pohledu přímo shora: fotka zešikma ji přecení (vorvaň 0,15 místo 0,12, LEARNINGS 5. 11.).

Maska: průhledné pozadí, jinak všechno, co se od barvy okrajů snímku liší víc než `prah` (v Lab OpenCV, 0 až 255).
Kresba na bílém chce vyšší práh (vorvaň: 49 = tmavší než šedá 200), fotka z vody nižší (22).
"""
from __future__ import annotations

import base64

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

N = 101     # vzorků po délce


class SiluetaError(ValueError):
    pass


class Predloha(BaseModel):
    ref_id: str | None = None
    b64: str | None = None
    vyrez: tuple[float, float, float, float] | None = None     # [x0, y0, x1, y1] v podílech snímku: jen část předlohy (kresba nad kostrou)
    prah: float = 22.0


class SiluetaIn(BaseModel):
    bok: Predloha
    shora: Predloha | None = None
    hlava_bok: str = "vlevo"        # kde je na boční předloze hlava
    obratit_shora: bool = False      # shora se hlava hledá jako tupější konec; tohle ho obrátí
    konec_tloustka: float | None = None     # tělo končí, kde je z boku tenčí než tohle (podíl délky): ocasní ploutev z hrany se nepočítá


def decode(raw: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise SiluetaError("předloha není obrázek")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return img


def crop(img: np.ndarray, box) -> np.ndarray:
    if not box:
        return img
    h, w = img.shape[:2]
    x0, y0, x1, y1 = box
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise SiluetaError("výřez je [x0, y0, x1, y1] v podílech snímku, x0 < x1, y0 < y1")
    return img[int(y0 * h): int(y1 * h), int(x0 * w): int(x1 * w)]


def largest(mask: np.ndarray) -> np.ndarray:
    """Největší souvislá skvrna s vyplněnými dírami (světlá místa kresby uvnitř obrysu)."""
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
    if n < 2:
        raise SiluetaError("na předloze se nenašel žádný tvar (zkus jiný práh nebo výřez)")
    k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    cnts, _ = cv2.findContours((lab == k).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    full = np.zeros(mask.shape, np.uint8)
    cv2.drawContours(full, cnts, -1, 1, -1)
    return full


def mask_of(img: np.ndarray, threshold: float, kernel: str) -> np.ndarray:
    if img.shape[2] == 4 and (img[:, :, 3] < 128).mean() > 0.05:
        raw = img[:, :, 3] > 127
    else:
        lab = cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2LAB).astype(np.float32)
        k = max(4, min(img.shape[:2]) // 25)
        border = np.concatenate([lab[:k, :k], lab[:k, -k:], lab[-k:, :k], lab[-k:, -k:]]).reshape(-1, 3)
        raw = np.linalg.norm(lab - np.median(border, axis=0), axis=2) > threshold
    raw = raw.astype(np.uint8)
    if kernel == "close":       # kresba: obrys z čar uzavřít
        raw = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    else:                       # fotka: šum a pěna kolem pryč
        raw = cv2.morphologyEx(raw, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    return largest(raw)


def columns(mask: np.ndarray) -> np.ndarray:
    """Pro každý sloupec s tvarem: [sloupec, horní řádek, dolní řádek]."""
    cols = np.where(mask.any(0))[0]
    return np.array([(c, *(lambda r: (r.min(), r.max()))(np.where(mask[:, c])[0])) for c in range(cols.min(), cols.max() + 1) if mask[:, c].any()], float)


def side(img: np.ndarray, p: Predloha, head: str, end_thickness: float | None) -> tuple[dict, np.ndarray]:
    img = crop(img, p.vyrez)
    if head == "vpravo":
        img = img[:, ::-1].copy()
    elif head != "vlevo":
        raise SiluetaError("hlava_bok je vlevo nebo vpravo")
    mask = mask_of(img, p.prah, "close")
    rows = columns(mask)
    x0, x1 = rows[0, 0], rows[-1, 0]
    end = x1
    if end_thickness:       # ocasní ploutev z boku je tenká čára: konec těla = poslední sloupec, kde je tělo ještě silnější
        thick = (rows[:, 2] - rows[:, 1]) / (x1 - x0)
        end = rows[int(np.where(thick > end_thickness)[0].max()), 0]
    t = np.linspace(0, 1, N)
    length = end - x0
    top = np.interp(x0 + t * length, rows[:, 0], rows[:, 1])
    bot = np.interp(x0 + t * length, rows[:, 0], rows[:, 2])
    out = {"x": t.round(4).tolist(), "hrbet": ((bot.max() - top) / length).round(4).tolist(), "bricho": ((bot.max() - bot) / length).round(4).tolist()}
    check = img[:, :, :3].copy()
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(check, cnts, -1, (0, 0, 255), 2)
    cv2.line(check, (int(end), 0), (int(end), check.shape[0]), (0, 200, 0), 2)
    return out, check


def top(img: np.ndarray, p: Predloha, flip: bool) -> tuple[list[float], np.ndarray]:
    """Šířka po délce: tvar se srovná podél hlavní osy (SVD), hlava je tupější konec (víc plochy na kraji), `flip` to obrátí."""
    img = crop(img, p.vyrez)
    mask = mask_of(img, p.prah, "open")
    ys, xs = np.nonzero(mask)
    pts = np.stack([xs, ys], 1).astype(np.float32)
    mean = pts.mean(0)
    _, _, vt = np.linalg.svd(pts - mean, full_matrices=False)
    angle = float(np.degrees(np.arctan2(vt[0][1], vt[0][0])))
    big = max(mask.shape) * 2
    rot_m = cv2.getRotationMatrix2D((float(mean[0]), float(mean[1])), angle, 1.0)
    rot_m[:, 2] += big / 2 - mean
    rot = cv2.warpAffine(mask, rot_m, (big, big), flags=cv2.INTER_NEAREST)
    rot_img = cv2.warpAffine(img[:, :, :3], rot_m, (big, big))
    cols = np.where(rot.any(0))[0]
    blunt_right = rot[:, cols.min(): cols.min() + 20].sum() < rot[:, cols.max() - 20: cols.max()].sum()
    if blunt_right != flip:
        rot, rot_img = rot[:, ::-1].copy(), rot_img[:, ::-1].copy()
    rows = columns(rot)
    x0, x1 = rows[0, 0], rows[-1, 0]
    t = np.linspace(0, 1, N)
    width = np.interp(x0 + t * (x1 - x0), rows[:, 0], rows[:, 2] - rows[:, 1]) / (x1 - x0)
    ys, xs = np.nonzero(rot)
    pad = 30
    check = rot_img.copy()
    cnts, _ = cv2.findContours(rot, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(check, cnts, -1, (0, 0, 255), 2)
    check = check[max(ys.min() - pad, 0): ys.max() + pad, max(xs.min() - pad, 0): xs.max() + pad]
    return width.round(4).tolist(), check


def png_b64(img: np.ndarray, width: int = 900) -> str:
    if img.shape[1] > width:
        img = cv2.resize(img, (width, int(img.shape[0] * width / img.shape[1])), interpolation=cv2.INTER_AREA)
    return base64.b64encode(cv2.imencode(".png", img)[1].tobytes()).decode()


def measure(side_img: np.ndarray, body: SiluetaIn, top_img: np.ndarray | None = None) -> dict:
    prof, side_check = side(side_img, body.bok, body.hlava_bok, body.konec_tloustka)
    out = {"profil": prof, "kontrola_bok": png_b64(side_check)}
    if top_img is not None and body.shora is not None:
        prof["sirka"], top_check = top(top_img, body.shora, body.obratit_shora)
        out["kontrola_shora"] = png_b64(top_check)
    h = np.array(prof["hrbet"]) - np.array(prof["bricho"])
    out["vyska_ku_delce"] = round(float(h.max()), 3)
    if "sirka" in prof:
        out["sirka_ku_delce"] = round(max(prof["sirka"]), 3)
    return out


def register(app: FastAPI, reflib) -> None:
    def load(p: Predloha) -> np.ndarray:
        if p.ref_id:
            path = reflib.image_path(p.ref_id)
            if path is None:
                raise HTTPException(404, f"předloha {p.ref_id} v knihovně neexistuje")
            return decode(path.read_bytes())
        if p.b64:
            return decode(base64.b64decode(p.b64.split(",", 1)[-1]))
        raise HTTPException(400, "předloha potřebuje ref_id nebo b64")

    @app.post("/api/v2/models3d/silueta")
    def models3d_silueta(body: SiluetaIn):
        """Profil pro díl `telo`: z boku hřbet a břicho, shora šířka. Kontrolní obrázky ukážou obrys přes předlohu."""
        try:
            return measure(load(body.bok), body, load(body.shora) if body.shora else None)
        except SiluetaError as e:
            raise HTTPException(400, str(e)) from e
