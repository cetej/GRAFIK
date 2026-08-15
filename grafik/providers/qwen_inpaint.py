"""QwenInpaintProvider — concrete ImageEditProvider for fal-ai/qwen-image-edit/inpaint.

Implements the proven flow from scripts/smoke_inpaint.py (falsifier A1,
docs/plans/2026-08-14-phase1-gate.md: PASS). Key finding reused here:
paste-back is mandatory — the raw endpoint result drifts globally, even
outside the requested mask, so the final image must be recomposited as
    final = input*(1-feathered_mask) + result*feathered_mask
using a dilated + feathered copy of the mask, not the raw API output.
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

        Returns:
            RGB image, same size as `image`, pasted back through a
            dilated+feathered copy of `mask`.
        """
        negative_prompt: str = kw.get("negative_prompt", "")
        enable_safety_checker: bool = kw.get("enable_safety_checker", True)

        input_rgb = image.convert("RGB")
        mask_l = mask.convert("L")
        api_mask = dilate_mask(mask_l)

        result_img = self._run_remote(
            input_rgb, api_mask, prompt, negative_prompt, enable_safety_checker
        )

        if result_img.size != input_rgb.size:
            result_img = result_img.resize(input_rgb.size, Image.LANCZOS)

        feathered = prepare_paste_mask(mask_l)
        return paste_back(input_rgb, result_img, feathered)

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
