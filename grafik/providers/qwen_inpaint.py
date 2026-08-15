"""QwenInpaintProvider — concrete ImageEditProvider for fal-ai/qwen-image-edit/inpaint.

Implements the proven flow from scripts/smoke_inpaint.py (falsifier A1,
docs/plans/2026-08-14-phase1-gate.md: PASS). Key finding reused here:
paste-back is mandatory — the raw endpoint result drifts globally, even
outside the requested mask, so the final image must be recomposited as
    final = input*(1-feathered_mask) + result*feathered_mask
using a dilated + feathered copy of the mask, not the raw API output.

M5 crop-based inpaint: the endpoint's output empirically caps at ~1536px
regardless of the requested image_size (docs/LEARNINGS.md 2026-08-14 "Qwen
inpaint: empirický output cap ~1536 px"), so on canvases larger than that
cap the generated detail inside the mask gets upscaled and looks soft.
When the mask is small relative to a large canvas, `edit()` now sends the
endpoint only a crop around the mask at full native resolution and pastes
the (resize-back-guarded) result into a copy of the full image before the
existing mandatory paste-back runs. Controlled by the `crop_inpaint` kwarg
(default True) — see `compute_crop_box` for the decision + margin logic,
shared with FluxFillProvider.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from grafik.fal.upload import download_url, upload_image
from grafik.providers.base import ImageEditProvider

ENDPOINT = "fal-ai/qwen-image-edit/inpaint"

# scripts/smoke_inpaint.py build_masks(): dilate ~4px, feather ~2px.
DILATE_KERNEL = 9  # ImageFilter.MaxFilter kernel k -> radius (k-1)/2 = 4px
FEATHER_RADIUS = 2

# M5 crop-based inpaint thresholds — see compute_crop_box(). Shared with
# FluxFillProvider, which imports these rather than redefining them.
CROP_MAX_MASK_FRACTION = 0.25  # mask bbox >= this fraction of image area -> send whole image
CROP_MIN_LONG_EDGE = 1536  # image long edge <= this -> already within the endpoint's cap, no crop


def dilate_mask(mask: Image.Image, kernel: int = DILATE_KERNEL) -> Image.Image:
    """Dilate a mask ~4px (MaxFilter kernel=9 -> radius (k-1)/2). This is the
    hard mask sent to the API — see scripts/smoke_inpaint.py, which uploads
    the dilated-but-not-feathered mask, not the feathered one.
    """
    if mask.mode != "L":
        mask = mask.convert("L")
    return mask.filter(ImageFilter.MaxFilter(kernel))


def prepare_paste_mask(mask: Image.Image) -> Image.Image:
    """Dilate ~4px then Gaussian-feather ~2px -> soft mask for paste-back.

    Mirrors scripts/smoke_inpaint.py build_masks(): dilate = MaxFilter(9)
    (~4px radius), feather = GaussianBlur(2). Shared helper so other
    mask-based providers (e.g. flux-fill) reuse identical paste-back prep.
    """
    return dilate_mask(mask).filter(ImageFilter.GaussianBlur(FEATHER_RADIUS))


def compute_crop_box(
    mask: Image.Image, image_size: tuple[int, int]
) -> tuple[int, int, int, int] | None:
    """Decide the crop region around a small mask on a large canvas, or None.

    Canvas-space only: `mask` and `image_size` are expected in the same
    canvas space `edit()` already operates in (the composited canvas and a
    canvas-sized mask from the API layer). The LAYOUT quad rule
    (docs/LEARNINGS.md 2026-08-15 "Layout quad je jediný canvas-space rozměr
    vrstvy") is the caller's responsibility — grafik/api/app.py translates
    each layer's native PNG pixels into its layout quad before reaching this
    provider — so native per-layer PNG dimensions never reach this function.

    Returns (left, top, right, bottom), or None when cropping should be
    skipped:
      - the mask has no nonzero region after thresholding (nothing to inpaint)
      - the image's long edge is already <= CROP_MIN_LONG_EDGE (within the
        endpoint's native output resolution -- cropping buys nothing)
      - the mask's bounding box covers >= CROP_MAX_MASK_FRACTION of the
        image area (mask isn't "small" relative to the canvas)

    Otherwise the mask's bounding box (thresholded at >127) is expanded by a
    margin of max(64, 25% of the bbox's longer edge) on every side, then
    clamped to the image bounds.
    """
    width, height = image_size

    mask_l = mask if mask.mode == "L" else mask.convert("L")
    thresholded = mask_l.point(lambda p: 255 if p > 127 else 0)
    bbox = thresholded.getbbox()
    if bbox is None:
        return None

    if max(width, height) <= CROP_MIN_LONG_EDGE:
        return None

    left, top, right, bottom = bbox
    bbox_area = (right - left) * (bottom - top)
    if bbox_area >= CROP_MAX_MASK_FRACTION * (width * height):
        return None

    bbox_long_edge = max(right - left, bottom - top)
    margin = max(64, round(bbox_long_edge * 0.25))

    return (
        max(0, left - margin),
        max(0, top - margin),
        min(width, right + margin),
        min(height, bottom + margin),
    )


def paste_back(input_rgb: Image.Image, result_rgb: Image.Image, feathered_mask: Image.Image) -> Image.Image:
    """Composite result over input using a feathered mask.

    final = input*(1-feathered_mask) + result*feathered_mask

    Mandatory per the A1 smoke-test finding: the raw endpoint result drifts
    globally, so outside-mask pixels must come from the original input, not
    the API response.
    """
    input_arr = np.array(input_rgb.convert("RGB"), dtype=np.float64)
    result_arr = np.array(result_rgb.convert("RGB"), dtype=np.float64)
    feather_norm = (np.array(feathered_mask.convert("L"), dtype=np.float64) / 255.0)[..., None]
    final_arr = input_arr * (1 - feather_norm) + result_arr * feather_norm
    return Image.fromarray(np.clip(final_arr, 0, 255).astype(np.uint8), mode="RGB")


class QwenInpaintProvider(ImageEditProvider):
    """Concrete ImageEditProvider for fal-ai/qwen-image-edit/inpaint."""

    ENDPOINT = ENDPOINT

    def edit(self, image: Image.Image, mask: Image.Image, prompt: str, **kw: Any) -> Image.Image:
        """Inpaint `image` inside `mask` per `prompt`, with mandatory paste-back.

        Args:
            image: RGB(A) source image.
            mask: grayscale/alpha mask, white = edit region.
            prompt: edit instruction.
            negative_prompt: optional, default "".
            enable_safety_checker: optional, default True.
            crop_inpaint: optional, default True. When the mask is small
                relative to a large canvas (see compute_crop_box), send the
                endpoint only a crop around the mask at full native
                resolution instead of the whole (possibly downscaled-on-
                output) canvas. Set False to force the pre-M5 whole-image
                behavior.

        Returns:
            RGB image, same size as `image`, pasted back through a
            dilated+feathered copy of `mask`.
        """
        negative_prompt: str = kw.get("negative_prompt", "")
        enable_safety_checker: bool = kw.get("enable_safety_checker", True)
        crop_inpaint: bool = kw.get("crop_inpaint", True)

        input_rgb = image.convert("RGB")
        mask_l = mask.convert("L")
        api_mask = dilate_mask(mask_l)

        crop_box = compute_crop_box(mask_l, input_rgb.size) if crop_inpaint else None
        remote_image = input_rgb.crop(crop_box) if crop_box is not None else input_rgb
        remote_mask = api_mask.crop(crop_box) if crop_box is not None else api_mask

        result_img = self._run_remote(
            remote_image, remote_mask, prompt, negative_prompt, enable_safety_checker
        )

        # Resize-back guard against the size actually sent (the crop, when
        # cropping) -- not against the full canvas.
        if result_img.size != remote_image.size:
            result_img = result_img.resize(remote_image.size, Image.LANCZOS)

        if crop_box is not None:
            full_result = input_rgb.copy()
            full_result.paste(result_img, crop_box[:2])
        else:
            full_result = result_img

        feathered = prepare_paste_mask(mask_l)
        return paste_back(input_rgb, full_result, feathered)

    def _run_remote(
        self,
        image: Image.Image,
        mask: Image.Image,
        prompt: str,
        negative_prompt: str,
        enable_safety_checker: bool,
    ) -> Image.Image:
        """All network I/O for one inpaint call: upload image+mask, subscribe
        to the endpoint, download the result. Isolated in this one method so
        tests can monkeypatch it and exercise edit() fully offline.

        Receives whatever `edit()` decided to send -- the full canvas, or a
        crop when crop-based inpaint kicked in. `image_size`/`mp` (cost)
        below are derived from `image`'s own size, so a crop call reports
        (and is costed at) the crop's resolution, not the full canvas --
        this is intentional, not a bug to fix.
        """
        from grafik.fal.client import tracked_subscribe

        image_url = upload_image(image)
        mask_url = upload_image(mask)
        result = tracked_subscribe(
            self.ENDPOINT,
            {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "image_url": image_url,
                "mask_url": mask_url,
                "image_size": {"width": image.width, "height": image.height},
                "enable_safety_checker": enable_safety_checker,
                "output_format": "png",
            },
            kind="image_edit",
            mp=image.width * image.height / 1e6,
            with_logs=False,
        )
        img_info = result["images"][0]
        return download_url(img_info["url"]).convert("RGB")
