"""Pixel-diff two PNGs over RGB. Reusable for M2 export/preview parity and M3 clip verification.

Usage:
    python scripts/pixel_diff.py a.png b.png [--resize-to-first]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
from PIL import Image

MAX_RESIZE_DELTA_PX = 4


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument(
        "--resize-to-first",
        action="store_true",
        help=f"if sizes differ by <= {MAX_RESIZE_DELTA_PX}px, LANCZOS-resize b onto a's size instead of erroring",
    )
    args = ap.parse_args()

    img_a = Image.open(args.a).convert("RGB")
    img_b = Image.open(args.b).convert("RGB")
    size_a, size_b = img_a.size, img_b.size
    resized = False

    if size_a != size_b:
        dw, dh = abs(size_a[0] - size_b[0]), abs(size_a[1] - size_b[1])
        if args.resize_to_first and dw <= MAX_RESIZE_DELTA_PX and dh <= MAX_RESIZE_DELTA_PX:
            img_b = img_b.resize(size_a, Image.LANCZOS)
            resized = True
        else:
            print(json.dumps({
                "error": f"size mismatch {size_a} vs {size_b} (--resize-to-first requires diff <= {MAX_RESIZE_DELTA_PX}px)",
            }))
            return 1

    diff = np.abs(np.asarray(img_a, dtype=np.int16) - np.asarray(img_b, dtype=np.int16))
    per_pixel = diff.max(axis=-1)  # worst channel per pixel

    print(json.dumps({
        "size_a": list(size_a),
        "size_b": list(size_b),
        "resized": resized,
        "mean_abs_diff": float(diff.mean()),
        "max_abs_diff": int(diff.max()),
        "pct_pixels_gt8": float((per_pixel > 8).mean() * 100),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
