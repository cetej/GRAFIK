"""Smoke test: Kling per-element motion (dynamic_masks) via fal.ai.

Validates architecture falsifier A3 from docs/plans/2026-08-14-unified-editor.md:
"Kling 1.6 odmizne masky odvozene z alfa kanalu (format/hodnoty/rozmery) ->
zjisti smoke test task 1.2 prvni den."

Run #1 (v1.6/pro, request 019ffff2-0260-7812-b1b9-859f3946e5bb) proved v1.6/pro
silently IGNORES dynamic_masks (field absent from its schema entirely -- see
docs/capabilities/kling-versions.md). Plan doc was corrected to redirect task 1.2
to v1.5/pro, whose live OpenAPI schema DOES declare dynamic_masks + static_mask_url
(confirmed via read-only GET, $0). --endpoint selects which run to reproduce; the
default is left pointing at v1.6/pro to preserve the historical/reproducible path.

Pipeline:
  1. Composite the 4 layers of decompose-test.grafik bottom-to-top -> RGB PNG.
  2. Threshold Layer 3's alpha channel (the 11%-coverage compact object) ->
     binary black/white motion mask, same size as the input.
  3. Compute the mask centroid and build a short smooth trajectory from it.
  4. Upload input + mask to fal, submit <endpoint> with
     dynamic_masks=[{mask_url, trajectories}], poll until Completed, download
     the resulting mp4.

Source project (READ-ONLY, never modified):
  C:/Users/stock/Documents/000_NGM/GRAFIK/projects/decompose-test.grafik

Usage:
  python scripts/smoke_kling_motion.py --dry-run                    # build input/mask only, no API calls
  python scripts/smoke_kling_motion.py                               # full run on v1.6/pro (default, historical)
  python scripts/smoke_kling_motion.py --endpoint v1.5pro            # full run on v1.5/pro
  python scripts/smoke_kling_motion.py --endpoint v1.5pro --resume <id>  # skip submission, poll+fetch only
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import argparse
import json
import math
import os
import time
import urllib.request
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from PIL import Image

WORKTREE = Path(__file__).resolve().parents[1]
load_dotenv(WORKTREE / "key.env")
os.environ.setdefault("FAL_KEY", os.environ.get("FAL_API_KEY", ""))

import fal_client  # noqa: E402  (import after FAL_KEY is set)

from grafik.core.composer import compose  # noqa: E402
from grafik.core.project import LayerProject  # noqa: E402

SOURCE_PROJECT = Path("C:/Users/stock/Documents/000_NGM/GRAFIK/projects/decompose-test.grafik")
MOTION_LAYER_ID = "7d30fcc59fa3"  # "Layer 3", alpha coverage 11%, compact object

# endpoint key -> (fal endpoint id, output clip path). v1.6pro is kept as the
# default to preserve the historical/reproducible path from run #1 (FAIL --
# dynamic_masks silently ignored). v1.5pro is run #2 (schema confirmed to
# declare dynamic_masks + static_mask_url; see docs/capabilities/kling-versions.md).
SCRATCH = WORKTREE / "scratch" / "smoke"
ENDPOINTS = {
    "v1.6pro": {
        "id": "fal-ai/kling-video/v1.6/pro/image-to-video",
        "output": SCRATCH / "kling_motion.mp4",
    },
    "v1.5pro": {
        "id": "fal-ai/kling-video/v1.5/pro/image-to-video",
        "output": SCRATCH / "kling_motion_v15pro.mp4",
    },
}
ENDPOINT = ENDPOINTS["v1.6pro"]["id"]  # overwritten in main() from --endpoint
OUTPUT_MP4 = ENDPOINTS["v1.6pro"]["output"]  # overwritten in main() from --endpoint

INPUT_PNG = SCRATCH / "kling_input.png"
MASK_PNG = SCRATCH / "kling_mask.png"
REQUEST_ID_FILE = SCRATCH / "kling_request_id.txt"

# Filled in after visually inspecting kling_input.png / kling_mask.png (see docs/spikes report).
# Scene: a Czech-language historical infographic ("Anatomie spiknuti" -- the
# Ides of March), a 3D-rendered isometric diorama of the Roman Curia of Pompey.
# The masked region (Layer 3) covers the tight cluster of toga-clad senators
# gathered on the marble steps plus a few caption label boxes.
PROMPT = (
    "A tight group of people in white and burgundy togas, standing closely "
    "together on marble steps, shifts and sways gently as they lean toward "
    "the center of the group, their robes and cloaks stirring; the rest of "
    "the scene stays completely still."
)

DURATION = "5"
TRAJECTORY_POINTS = 7
TRAJECTORY_AMPLITUDE_PX = 100  # total horizontal excursion
TRAJECTORY_BOW_PX = 18  # vertical bow of the arc (rises mid-path)
ALPHA_THRESHOLD = 127
EDGE_MARGIN = 2  # keep trajectory points this many px inside canvas bounds


def build_inputs() -> tuple[Path, Path, tuple[int, int], tuple[int, int]]:
    """Composite layers -> RGB input PNG; threshold Layer 3 alpha -> B/W mask PNG.

    Returns (input_path, mask_path, centroid_xy, canvas_wh).
    """
    SCRATCH.mkdir(parents=True, exist_ok=True)

    project = LayerProject.load(SOURCE_PROJECT)
    composite = compose(project, SOURCE_PROJECT)  # RGBA, layers already bottom-to-top by z_order
    rgb = composite.convert("RGB")
    rgb.save(INPUT_PNG, "PNG")

    layer = project.get_layer(MOTION_LAYER_ID)
    if layer is None:
        raise SystemExit(f"Layer {MOTION_LAYER_ID} not found in project.json")
    layer_img = layer.load_image(SOURCE_PROJECT)  # RGBA
    alpha = np.array(layer_img.split()[-1])  # (H, W) uint8

    mask_bool = alpha > ALPHA_THRESHOLD
    mask_arr = np.where(mask_bool, 255, 0).astype(np.uint8)
    mask_img = Image.fromarray(mask_arr, mode="L").convert("RGB")
    mask_img.save(MASK_PNG, "PNG")

    ys, xs = np.nonzero(mask_bool)
    if len(xs) == 0:
        raise SystemExit("Mask is empty -- no pixels above alpha threshold")
    centroid = (int(round(xs.mean())), int(round(ys.mean())))
    coverage_pct = 100.0 * len(xs) / mask_bool.size
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))

    print(f"input composite: size={rgb.size} mode={rgb.mode} -> {INPUT_PNG}")
    print(
        f"mask from layer {MOTION_LAYER_ID}: size={mask_img.size} coverage={coverage_pct:.2f}% "
        f"bbox={bbox} centroid={centroid} -> {MASK_PNG}"
    )
    return INPUT_PNG, MASK_PNG, centroid, (project.canvas_width, project.canvas_height)


def build_trajectory(centroid: tuple[int, int], bounds: tuple[int, int]) -> list[dict]:
    """5-8 {x,y} int points starting AT the centroid, smooth horizontal arc."""
    w, h = bounds
    cx, cy = centroid
    points = []
    for i in range(TRAJECTORY_POINTS):
        t = i / (TRAJECTORY_POINTS - 1)
        dx = TRAJECTORY_AMPLITUDE_PX * t
        dy = -TRAJECTORY_BOW_PX * math.sin(math.pi * t)
        x = int(round(cx + dx))
        y = int(round(cy + dy))
        x = max(EDGE_MARGIN, min(w - EDGE_MARGIN, x))
        y = max(EDGE_MARGIN, min(h - EDGE_MARGIN, y))
        points.append({"x": x, "y": y})
    return points


def submit(prompt: str, image_url: str, mask_url: str, trajectory: list[dict]) -> str:
    arguments = {
        "prompt": prompt,
        "image_url": image_url,
        "duration": DURATION,
        "dynamic_masks": [{"mask_url": mask_url, "trajectories": trajectory}],
    }
    print("submitting with arguments:")
    print(json.dumps(arguments, indent=2))

    try:
        handle = fal_client.submit(ENDPOINT, arguments=arguments)
    except fal_client.FalClientHTTPError as exc:
        print(f"SUBMIT FAILED: HTTP {exc.status_code}: {exc.message}")
        raise

    request_id = handle.request_id
    print(f"request_id={request_id}")
    with open(REQUEST_ID_FILE, "a", encoding="utf-8") as f:
        f.write(request_id + "\n")
    return request_id


def poll_and_fetch(request_id: str) -> dict | None:
    print(f"polling request_id={request_id} every 20s ...")
    while True:
        status = fal_client.status(ENDPOINT, request_id, with_logs=True)
        ts = time.strftime("%H:%M:%S")
        if isinstance(status, fal_client.Queued):
            print(f"[{ts}] Queued position={status.position}")
        elif isinstance(status, fal_client.InProgress):
            print(f"[{ts}] InProgress")
            for log in status.logs or []:
                msg = log.get("message") if isinstance(log, dict) else log
                if msg:
                    print(f"    log: {msg}")
        elif isinstance(status, fal_client.Completed):
            print(f"[{ts}] Completed metrics={getattr(status, 'metrics', None)}")
            break
        else:
            print(f"[{ts}] status={status}")
        time.sleep(20)

    result = fal_client.result(ENDPOINT, request_id)
    print("result JSON:")
    print(json.dumps(result, indent=2))

    video = result.get("video") or {}
    video_url = video.get("url")
    if not video_url:
        print("NO video URL in result -- cannot download.")
        return result

    print(f"downloading {video_url} -> {OUTPUT_MP4}")
    urllib.request.urlretrieve(video_url, OUTPUT_MP4)
    size = OUTPUT_MP4.stat().st_size
    print(f"downloaded {OUTPUT_MP4} ({size} bytes)")
    return result


def main() -> None:
    global ENDPOINT, OUTPUT_MP4

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--endpoint",
        choices=sorted(ENDPOINTS),
        default="v1.6pro",
        help="Which Kling endpoint/run to reproduce (default: v1.6pro, the historical FAIL run)",
    )
    parser.add_argument("--resume", metavar="REQUEST_ID", help="Skip submission, poll+fetch only")
    parser.add_argument(
        "--dry-run", action="store_true", help="Build input/mask + trajectory, print, but do not call the API"
    )
    args = parser.parse_args()

    ENDPOINT = ENDPOINTS[args.endpoint]["id"]
    OUTPUT_MP4 = ENDPOINTS[args.endpoint]["output"]
    print(f"endpoint={ENDPOINT}")
    print(f"output_mp4={OUTPUT_MP4}")

    if args.resume:
        poll_and_fetch(args.resume)
        return

    input_path, mask_path, centroid, bounds = build_inputs()
    trajectory = build_trajectory(centroid, bounds)
    print(f"trajectory ({len(trajectory)} points):")
    for p in trajectory:
        print(f"  {p}")

    if args.dry_run:
        print("dry-run: stopping before upload/submit.")
        return

    print("uploading input image...")
    image_url = fal_client.upload_file(str(input_path))
    print(f"  image_url = {image_url}")

    print("uploading mask image...")
    mask_url = fal_client.upload_file(str(mask_path))
    print(f"  mask_url = {mask_url}")

    request_id = submit(PROMPT, image_url, mask_url, trajectory)
    poll_and_fetch(request_id)


if __name__ == "__main__":
    main()
