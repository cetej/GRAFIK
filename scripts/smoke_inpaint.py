"""Smoke test (Task 1.3): per-element inpainting via fal-ai/qwen-image-edit/inpaint.

Validates architecture falsifier A1 (docs/plans/2026-08-14-unified-editor.md):
    "upscale masky (bilinear + threshold/feather) produkuje viditelne svy na
    hranicich editu -> nutny SAM 3 refine masky v plnem rozliseni."

Pipeline:
    1. Composite the 4 source layers bottom-to-top -> RGB canvas.
    2. Simulate the production mask path: take Layer 3 (compact object) alpha,
       downscale to 50%, upscale back (bilinear) -> threshold -> dilate -> feather.
    3. Upload image + hard binary mask, call the inpaint endpoint.
    4. Paste raw result back into the canvas using the feathered mask.
    5. Compute outside-mask diff (raw + final) and a boundary-ring gradient
       ratio as a seam heuristic.

Usage:
    python scripts/smoke_inpaint.py            # real API call
    python scripts/smoke_inpaint.py --dry-run   # skip network call, exercise pipeline only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
from PIL import Image, ImageFilter
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "key.env")
os.environ.setdefault("FAL_KEY", os.environ.get("FAL_API_KEY", ""))

import fal_client  # noqa: E402  (import after FAL_KEY is set)

from grafik.fal.upload import upload_file, download_url  # noqa: E402

SRC_PROJECT = Path(
    "C:/Users/stock/Documents/000_NGM/GRAFIK/projects/decompose-test.grafik"
)
LAYERS_DIR = SRC_PROJECT / "layers"
OUT_DIR = ROOT / "scratch" / "smoke"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# z_order bottom -> top, per project.json
LAYER_ORDER = [
    "5588a9f356b6",  # Layer 0 - background (opaque)
    "53602ec6840f",  # Layer 1 - near-invisible ghost text (1% alpha)
    "e64e0a36cfa9",  # Layer 2 - Roman senate steps illustration (62% alpha)
    "7d30fcc59fa3",  # Layer 3 - compact object: senators/Caesar cluster + labels (11% alpha)
]
TARGET_LAYER = "7d30fcc59fa3"

CANVAS_W, CANVAS_H = 544, 736

ENDPOINT = "fal-ai/qwen-image-edit/inpaint"

PROMPT = (
    "Replace this area with a large bronze Roman eagle standard (aquila) mounted "
    "on a tall marble pedestal, dramatic warm side lighting, detailed painterly "
    "illustration style matching a historical Roman infographic, no text, no people"
)
NEGATIVE_PROMPT = "text, watermark, blurry, low quality, cartoon, modern objects, people"


def composite_layers() -> Image.Image:
    """Alpha-composite the 4 source layers bottom-to-top -> RGBA canvas."""
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    for layer_id in LAYER_ORDER:
        img = Image.open(LAYERS_DIR / f"{layer_id}.png").convert("RGBA")
        if img.size != (CANVAS_W, CANVAS_H):
            img = img.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
        canvas.alpha_composite(img)
    return canvas


def flatten_to_rgb(rgba: Image.Image) -> Image.Image:
    """Flatten RGBA onto a white background -> RGB."""
    bg = Image.new("RGB", rgba.size, (255, 255, 255))
    bg.paste(rgba, mask=rgba.split()[3])
    return bg


def build_masks() -> tuple[Image.Image, Image.Image, Image.Image, list[int] | None]:
    """Simulate the production mask path for Layer 3.

    Returns (binary_pre_dilate, dilated_hard_binary, feathered_soft, alpha_bbox).
    """
    layer_img = Image.open(LAYERS_DIR / f"{TARGET_LAYER}.png").convert("RGBA")
    alpha = layer_img.split()[3]
    assert alpha.size == (CANVAS_W, CANVAS_H), f"unexpected layer size {alpha.size}"

    alpha_arr = np.array(alpha)
    ys, xs = np.where(alpha_arr > 12)
    bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None

    # Production-path simulation: downscale 50% then upscale back, bilinear both ways
    small = alpha.resize((CANVAS_W // 2, CANVAS_H // 2), Image.BILINEAR)
    up = small.resize((CANVAS_W, CANVAS_H), Image.BILINEAR)

    # Threshold -> hard binary (kept as a copy per spec)
    binary = up.point(lambda x: 255 if x >= 128 else 0)

    # Dilate ~4px (MaxFilter kernel k gives radius (k-1)/2)
    dilated = binary.filter(ImageFilter.MaxFilter(9))

    # Feather ~2px for paste-back
    feathered = dilated.filter(ImageFilter.GaussianBlur(2))

    return binary, dilated, feathered, bbox


def grad_magnitude(rgb_img: Image.Image) -> np.ndarray:
    gray = np.array(rgb_img.convert("L"), dtype=np.float64)
    gy, gx = np.gradient(gray)
    return np.sqrt(gx**2 + gy**2)


def call_inpaint(image_url: str, mask_url: str, enable_safety_checker: bool) -> dict:
    return fal_client.subscribe(
        ENDPOINT,
        arguments={
            "prompt": PROMPT,
            "negative_prompt": NEGATIVE_PROMPT,
            "image_url": image_url,
            "mask_url": mask_url,
            "image_size": {"width": CANVAS_W, "height": CANVAS_H},
            "enable_safety_checker": enable_safety_checker,
            "output_format": "png",
        },
        with_logs=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="skip the network call")
    args = parser.parse_args()

    # 1. Composite input
    composite_rgba = composite_layers()
    input_rgb = flatten_to_rgb(composite_rgba)
    input_path = OUT_DIR / "inpaint_input.png"
    input_rgb.save(input_path, "PNG")

    # 2. Masks
    binary, dilated, feathered, bbox = build_masks()
    mask_path = OUT_DIR / "inpaint_mask.png"
    dilated.convert("RGB").save(mask_path, "PNG")  # hard binary version sent to API

    mask_stats = {
        "target_layer_alpha_bbox_xyxy": bbox,
        "binary_pct_edit": float((np.array(binary) > 127).mean() * 100),
        "dilated_pct_edit": float((np.array(dilated) > 127).mean() * 100),
    }

    call_log: list[str] = []

    if args.dry_run:
        result_img = input_rgb.copy()
        result_size = list(result_img.size)
        resized_note = False
        api_seed = None
        api_has_nsfw = None
        api_timings = None
        call_log.append("DRY RUN - no network call, result = copy of input")
    else:
        image_url = upload_file(input_path)
        mask_url = upload_file(mask_path)
        call_log.append(f"uploaded image_url={image_url}")
        call_log.append(f"uploaded mask_url={mask_url}")

        result = None
        try:
            result = call_inpaint(image_url, mask_url, enable_safety_checker=True)
            call_log.append("call 1: enable_safety_checker=True -> OK")
            if any(result.get("has_nsfw_concepts") or []):
                call_log.append(
                    "call 1 flagged has_nsfw_concepts=True -> retrying with enable_safety_checker=False"
                )
                result = call_inpaint(image_url, mask_url, enable_safety_checker=False)
                call_log.append("call 2: enable_safety_checker=False -> OK")
        except Exception as exc:  # noqa: BLE001
            call_log.append(f"call 1 raised: {exc!r} -> retrying with enable_safety_checker=False")
            result = call_inpaint(image_url, mask_url, enable_safety_checker=False)
            call_log.append("call 2: enable_safety_checker=False -> OK")

        img_info = result["images"][0]
        api_seed = result.get("seed")
        api_has_nsfw = result.get("has_nsfw_concepts")
        api_timings = result.get("timings")

        result_img_raw = download_url(img_info["url"]).convert("RGB")
        result_size = [img_info.get("width"), img_info.get("height")]
        resized_note = False
        if result_img_raw.size != (CANVAS_W, CANVAS_H):
            result_img = result_img_raw.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
            resized_note = True
            call_log.append(
                f"result size {result_img_raw.size} != canvas {(CANVAS_W, CANVAS_H)} -> resized back"
            )
        else:
            result_img = result_img_raw

    result_path = OUT_DIR / "inpaint_result_raw.png"
    result_img.save(result_path, "PNG")

    # 3. Metrics — raw diff outside mask
    input_arr = np.array(input_rgb, dtype=np.int16)
    result_arr = np.array(result_img, dtype=np.int16)
    diff_raw = np.abs(result_arr - input_arr)  # HxWx3
    diff_raw_px = diff_raw.mean(axis=2)  # HxW

    dilated_bool = np.array(dilated) > 127
    outside = ~dilated_bool

    outside_raw = {
        "mean_abs_diff": float(diff_raw_px[outside].mean()),
        "max_abs_diff": float(diff_raw[outside].max()),
        "pct_pixels_diff_gt8": float((diff_raw_px[outside] > 8).mean() * 100),
    }

    # 4. Paste-back
    feather_norm = (np.array(feathered, dtype=np.float64) / 255.0)[..., None]
    final_arr_f = input_arr.astype(np.float64) * (1 - feather_norm) + result_arr.astype(
        np.float64
    ) * feather_norm
    final_img = Image.fromarray(np.clip(final_arr_f, 0, 255).astype(np.uint8), mode="RGB")
    final_path = OUT_DIR / "inpaint_final.png"
    final_img.save(final_path, "PNG")

    final_arr = np.array(final_img, dtype=np.int16)
    diff_final = np.abs(final_arr - input_arr)
    diff_final_px = diff_final.mean(axis=2)
    outside_final = {
        "mean_abs_diff": float(diff_final_px[outside].mean()),
        "max_abs_diff": float(diff_final[outside].max()),
        "pct_pixels_diff_gt8": float((diff_final_px[outside] > 8).mean() * 100),
    }

    # Diff heatmap (raw result vs input, amplified x4)
    heat = np.clip(diff_raw.astype(np.float64) * 4, 0, 255).astype(np.uint8)
    heat_img = Image.fromarray(heat, mode="RGB")
    heatmap_path = OUT_DIR / "inpaint_diff_heatmap.png"
    heat_img.save(heatmap_path, "PNG")

    # 5. Seam check: boundary ring = dilate(dilated,+4px) AND NOT erode(dilated,-4px)
    outer = np.array(dilated.filter(ImageFilter.MaxFilter(9))) > 127
    inner = np.array(dilated.filter(ImageFilter.MinFilter(9))) > 127
    ring = outer & (~inner)

    grad_final = grad_magnitude(final_img)
    grad_input = grad_magnitude(input_rgb)
    ring_final_mean = float(grad_final[ring].mean())
    ring_input_mean = float(grad_input[ring].mean())
    boundary_ratio = ring_final_mean / ring_input_mean if ring_input_mean > 1e-6 else float("inf")

    metrics = {
        "endpoint": ENDPOINT,
        "dry_run": args.dry_run,
        "prompt": PROMPT,
        "negative_prompt": NEGATIVE_PROMPT,
        "call_log": call_log,
        "api_seed": api_seed,
        "api_has_nsfw_concepts": api_has_nsfw,
        "api_timings": api_timings,
        "result_size_reported": result_size,
        "result_resized_to_canvas": resized_note,
        "mask_stats": mask_stats,
        "outside_mask_diff_raw": outside_raw,
        "outside_mask_diff_final_pasteback": outside_final,
        "boundary_ring": {
            "ring_pixel_count": int(ring.sum()),
            "final_grad_mean": ring_final_mean,
            "input_grad_mean": ring_input_mean,
            "ratio_final_over_input": boundary_ratio,
        },
        "output_paths": {
            "input": str(input_path),
            "mask": str(mask_path),
            "result_raw": str(result_path),
            "final_pasteback": str(final_path),
            "diff_heatmap": str(heatmap_path),
        },
    }

    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
