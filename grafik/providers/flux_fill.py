"""FluxFillProvider — concrete ImageEditProvider for fal-ai/flux-pro/v1/fill.

Same proven flow as QwenInpaintProvider (falsifier A1): dilated hard mask to
the API, mandatory paste-back through a dilated+feathered copy of the mask,
resize-back guard when the endpoint returns a different size than the input.
The mask/paste helpers are imported from qwen_inpaint so both mask-based
providers share identical prep math.

Payload shape verified against the raw fal OpenAPI schema (fetch
2026-08-15): required prompt + image_url + mask_url; mask "needs to match
the dimensions of the input image" (our canvas-size mask always does);
output_format defaults to "jpeg" so we send "png" explicitly;
safety_tolerance defaults to "2". There is no image_size field — output size
follows the input, with the resize-back guard as the safety net.

M5 crop-based inpaint: shares the same empirical-cap rationale and
`compute_crop_box`/threshold constants as QwenInpaintProvider (see that
module's docstring) rather than redefining them — both mask-based
providers get soft/upscaled detail on large canvases when the endpoint's
native output resolution is smaller than the canvas. Controlled by the same
`crop_inpaint` kwarg (default True).
"""

from __future__ import annotations

from typing import Any

from PIL import Image

from grafik.fal.upload import download_url, upload_image
from grafik.providers.base import ImageEditProvider
from grafik.providers.qwen_inpaint import (
    compute_crop_box,
    dilate_mask,
    paste_back,
    prepare_paste_mask,
)

ENDPOINT = "fal-ai/flux-pro/v1/fill"


class FluxFillProvider(ImageEditProvider):
    """Concrete ImageEditProvider for fal-ai/flux-pro/v1/fill."""

    ENDPOINT = ENDPOINT

    def edit(self, image: Image.Image, mask: Image.Image, prompt: str, **kw: Any) -> Image.Image:
        """Fill `image` inside `mask` per `prompt`, with mandatory paste-back.

        Args:
            image: RGB(A) source image.
            mask: grayscale/alpha mask, white = edit region.
            prompt: edit instruction.
            safety_tolerance: optional, default "2" (schema default).
            crop_inpaint: optional, default True. When the mask is small
                relative to a large canvas (see compute_crop_box in
                qwen_inpaint.py), send the endpoint only a crop around the
                mask at full native resolution instead of the whole canvas.
                Set False to force the pre-M5 whole-image behavior.

        Returns:
            RGB image, same size as `image`, pasted back through a
            dilated+feathered copy of `mask`.
        """
        safety_tolerance: str = kw.get("safety_tolerance", "2")
        crop_inpaint: bool = kw.get("crop_inpaint", True)

        input_rgb = image.convert("RGB")
        mask_l = mask.convert("L")
        api_mask = dilate_mask(mask_l)

        crop_box = compute_crop_box(mask_l, input_rgb.size) if crop_inpaint else None
        remote_image = input_rgb.crop(crop_box) if crop_box is not None else input_rgb
        remote_mask = api_mask.crop(crop_box) if crop_box is not None else api_mask

        result_img = self._run_remote(remote_image, remote_mask, prompt, safety_tolerance)

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
        safety_tolerance: str,
    ) -> Image.Image:
        """All network I/O for one fill call — isolated for monkeypatching,
        mirrors QwenInpaintProvider._run_remote.

        Receives whatever `edit()` decided to send -- the full canvas, or a
        crop when crop-based inpaint kicked in; `mp` (cost) below follows
        `image`'s own size, so a crop call is costed at the crop's
        resolution, not the full canvas.
        """
        from grafik.fal.client import tracked_subscribe

        image_url = upload_image(image)
        mask_url = upload_image(mask)
        result = tracked_subscribe(
            self.ENDPOINT,
            {
                "prompt": prompt,
                "image_url": image_url,
                "mask_url": mask_url,
                "output_format": "png",
                "safety_tolerance": safety_tolerance,
            },
            kind="image_edit",
            mp=image.width * image.height / 1e6,
            with_logs=False,
        )
        img_info = result["images"][0]
        return download_url(img_info["url"]).convert("RGB")
