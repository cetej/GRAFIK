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
"""

from __future__ import annotations

from typing import Any

from PIL import Image

from grafik.fal.upload import download_url, upload_image
from grafik.providers.base import ImageEditProvider
from grafik.providers.qwen_inpaint import dilate_mask, paste_back, prepare_paste_mask

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

        Returns:
            RGB image, same size as `image`, pasted back through a
            dilated+feathered copy of `mask`.
        """
        safety_tolerance: str = kw.get("safety_tolerance", "2")

        input_rgb = image.convert("RGB")
        mask_l = mask.convert("L")
        api_mask = dilate_mask(mask_l)

        result_img = self._run_remote(input_rgb, api_mask, prompt, safety_tolerance)

        if result_img.size != input_rgb.size:
            result_img = result_img.resize(input_rgb.size, Image.LANCZOS)

        feathered = prepare_paste_mask(mask_l)
        return paste_back(input_rgb, result_img, feathered)

    def _run_remote(
        self,
        image: Image.Image,
        mask: Image.Image,
        prompt: str,
        safety_tolerance: str,
    ) -> Image.Image:
        """All network I/O for one fill call — isolated for monkeypatching,
        mirrors QwenInpaintProvider._run_remote."""
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
