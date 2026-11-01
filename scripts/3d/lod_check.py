# One round of the render + measure loop for scripts/3d/lod_*.py (GRAFIK#71, free; steps: docs/3d-lod-postup.md):
#   python scripts/3d/lod_check.py OUT_DIR --lod scripts/3d/lod_tatra87.py [--ref silueta.png] [--tel 5] [--tol 5]
#   python scripts/3d/lod_check.py OUT_DIR --glb model.glb [--dim 4.74 1.67 1.50] [--ref silueta.png]
#   python scripts/3d/lod_check.py OUT_DIR --parts scripts/3d/dily/pantheon.json
# Builds the model (--lod), runs engine/blender/inspect_model.py under the heavy lock, writes OUT_DIR/kontrola.json
# (`problemy` = what to fix) and OUT_DIR/pohledy.png. Exit 0 = nothing to fix, 1 = see `problemy`.
# --ref: side outline of the real object (alpha, or anything on white), long axis across the frame; --zrcadlit when
# side.png faces the other way. --tel: bodies a cut through the lower half may have (mammoth: 4 legs + trunk = 5), more
# means an extra limb.
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
INSPECT = REPO / "engine" / "blender" / "inspect_model.py"
PARTS = REPO / "engine" / "blender" / "lod_parts.py"
TIMEOUT_S = 300
PROFILE_W = 1000


def dims_from_lod(path) -> list[float] | None:
    """[length, width, height] from the script's DIM table, None when it does not name all three."""
    for node in ast.parse(Path(path).read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "DIM":
            dim = ast.literal_eval(node.value)
            if all(k in dim for k in ("length", "width", "height")):
                return [float(dim[k]) for k in ("length", "width", "height")]
    return None


def mask_of(img: np.ndarray) -> np.ndarray:
    if img.ndim == 3 and img.shape[2] == 4 and img[:, :, 3].min() < 250:
        return (img[:, :, 3] > 127).astype(np.uint8)
    grey = img if img.ndim == 2 else cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
    return (grey < 245).astype(np.uint8)


def normalised(mask: np.ndarray) -> np.ndarray:
    """The object cut to its bbox and scaled uniformly to PROFILE_W, bottom on the last row."""
    ys, xs = np.where(mask > 0)
    if not len(xs):
        raise ValueError("prázdná silueta")
    crop = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    k = PROFILE_W / crop.shape[1]
    return cv2.resize(crop, (PROFILE_W, max(1, round(crop.shape[0] * k))), interpolation=cv2.INTER_NEAREST)


def top_line(mask: np.ndarray) -> np.ndarray:
    """Height of the outline above the bottom in every column, in thousandths of the length."""
    h = mask.shape[0]
    return np.where(mask.any(axis=0), h - mask.argmax(axis=0), 0).astype(np.float32)


def compare_outline(model_mask: np.ndarray, ref_mask: np.ndarray) -> dict:
    """Outlines at the same length, bottoms aligned; the thirds go left to right along the reference. The caller says
    which way the model faces (--zrcadlit): an overlap score picks the wrong mirror on a nearly symmetric outline
    (Tatra 87, measured 2026-10-31)."""
    ref, m = normalised(ref_mask), normalised(model_mask)
    h = max(m.shape[0], ref.shape[0])
    a, b = np.zeros((h, PROFILE_W), np.uint8), np.zeros((h, PROFILE_W), np.uint8)
    a[h - m.shape[0]:] = m
    b[h - ref.shape[0]:] = ref
    err = np.abs(top_line(m) - top_line(ref)) / 10
    third = PROFILE_W // 3
    return {"iou": round(float((a & b).sum() / max(1, (a | b).sum())), 3),
            "vyska_vs_delka_model": round(m.shape[0] / PROFILE_W, 3),
            "vyska_vs_delka_silueta": round(ref.shape[0] / PROFILE_W, 3),
            "obrys_odchylka_pct": {"zacatek": round(float(err[:third].mean()), 2),
                                   "stred": round(float(err[third:2 * third].mean()), 2),
                                   "konec": round(float(err[2 * third:].mean()), 2)},
            "overlay": np.dstack([a * 255, (a & b) * 255, b * 255])}


def problems(report: dict, dims: list[float] | None, tol_pct: float, bodies: int | None) -> list[str]:
    out = []
    if dims:
        length, width, height = dims
        for name, have, want in (("šířka/délka", report["sirka"] / report["delka"], width / length),
                                 ("výška/délka", report["vyska"] / report["delka"], height / length)):
            off = 100 * (have - want) / want
            if abs(off) > tol_pct:
                out.append(f"{name} {have:.3f}, cíl {want:.3f} ({off:+.1f} %, tolerance {tol_pct:g} %)")
    for part in report["casti"]["bez_kontaktu"]:
        out.append(f"díl bez kontaktu: střed {part['stred']}, rozměr {part['rozmer']}, mezera {part['mezera']}")
    if report["casti"]["fragmentu_navic"]:
        out.append(f"{report['casti']['fragmentu_navic']} dalších úlomků, nezkontrolováno")
    if bodies is not None:
        for cut, found in report["prurezy"].items():
            if float(cut) <= 0.5 and len(found) > bodies:
                out.append(f"průřez ve výšce {cut}: {len(found)} těl místo nejvýš {bodies}, středy {found}")
    return out


def sheet(out: Path, overlay: np.ndarray | None) -> None:
    tiles = []
    for name in ("side", "front", "top", "persp-a", "persp-b"):
        img = cv2.imread(str(out / f"{name}.png"), cv2.IMREAD_UNCHANGED)
        alpha = img[:, :, 3:] / 255
        tiles.append((img[:, :, :3] * alpha + 110 * (1 - alpha)).astype(np.uint8))
    if overlay is not None:
        k = tiles[0].shape[1] / overlay.shape[1]
        fit = cv2.resize(overlay, None, fx=k, fy=k, interpolation=cv2.INTER_NEAREST)
        pad = np.full(tiles[0].shape, 40, np.uint8)
        pad[-fit.shape[0]:] = fit[-pad.shape[0]:]
        tiles.append(pad)
    else:
        tiles.append(np.full(tiles[0].shape, 40, np.uint8))
    cv2.imwrite(str(out / "pohledy.png"), np.vstack([np.hstack(tiles[:3]), np.hstack(tiles[3:])]))


def main() -> int:
    from engine.config import find_blender
    from ngm_shared.heavy_lock import heavy

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--lod", type=Path)
    src.add_argument("--glb", type=Path)
    src.add_argument("--parts", type=Path, help="parts description (engine/parts_spec.py), built by engine/blender/lod_parts.py")
    ap.add_argument("--dim", type=float, nargs=3, metavar=("L", "W", "H"))
    ap.add_argument("--ref", type=Path)
    ap.add_argument("--zrcadlit", action="store_true", help="the model in side.png faces the other way than --ref")
    ap.add_argument("--tel", type=int)
    ap.add_argument("--tol", type=float, default=5.0)
    ap.add_argument("--tol-obrys", type=float, default=2.0)
    ap.add_argument("--size", type=int, default=1024)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    blender = find_blender()
    glb = a.glb or a.out / "model.glb"
    spec = None
    if a.parts:
        from engine.parts_spec import SpecError, validate
        try:
            spec = validate(json.loads(a.parts.read_text(encoding="utf-8")))
        except (SpecError, ValueError) as e:
            print(f"popis nejde postavit: {e}")
            return 2
        (a.out / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    command = [blender, "-b", "--factory-startup", "-P", str(a.lod), "--", str(glb)] if a.lod else (
        [blender, "-b", "--factory-startup", "-P", str(PARTS), "--", str(glb), str(a.out / "spec.json")] if a.parts else None)
    with heavy("blender", owner="grafik", caller="lod-check", wait_s=TIMEOUT_S):
        if command:
            built = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_S)
            if built.returncode or not glb.exists():
                print(built.stdout[-1500:], built.stderr[-1500:])
                return 2
        run = subprocess.run([blender, "-b", "--factory-startup", "-P", str(INSPECT), "--", str(glb), str(a.out),
                              "--size", str(a.size)], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=TIMEOUT_S)
    if run.returncode or not (a.out / "inspect.json").exists():
        print(run.stdout[-1500:], run.stderr[-1500:])
        return 2
    report = json.loads((a.out / "inspect.json").read_text(encoding="utf-8"))
    if a.parts:     # pieces inside a part are built to touch; what counts is contact between named parts
        loose = json.loads(Path(f"{glb}.dily.json").read_text(encoding="utf-8"))["bez_kontaktu"]
        report["casti"] = {**report["casti"], "bez_kontaktu": [{"stred": p["nazev"], "rozmer": "díl", "mezera": p["mezera"]} for p in loose], "fragmentu_navic": 0}
    dims = a.dim or (dims_from_lod(a.lod) if a.lod else [spec["dim"][k] for k in ("length", "width", "height")] if spec else None)
    result = {"pomery": {"sirka_delka": round(report["sirka"] / report["delka"], 3),
                         "vyska_delka": round(report["vyska"] / report["delka"], 3)},
              "bbox_m": [report["delka"], report["sirka"], report["vyska"]], "cil_m": dims,
              "problemy": problems(report, dims, a.tol, a.tel)}
    overlay = None
    if a.ref:
        side = cv2.imread(str(a.out / "side.png"), cv2.IMREAD_UNCHANGED)
        ref = cv2.imread(str(a.ref), cv2.IMREAD_UNCHANGED)
        outline = compare_outline(mask_of(side[:, ::-1] if a.zrcadlit else side), mask_of(ref))
        overlay = outline.pop("overlay")
        result["silueta"] = outline
        for third, off in outline["obrys_odchylka_pct"].items():
            if off > a.tol_obrys:
                result["problemy"].append(f"obrys proti siluetě, {third}: {off} % délky (tolerance {a.tol_obrys:g} %)")
    sheet(a.out, overlay)
    (a.out / "kontrola.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 1 if result["problemy"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
