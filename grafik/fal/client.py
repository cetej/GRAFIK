"""fal.ai client for Qwen-Image-Layered."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
import fal_client
from PIL import Image

load_dotenv()
load_dotenv("key.env")

from grafik.core.costs import record_paid_call
from grafik.core.layer import Layer
from grafik.core.project import LayerProject
from grafik.fal.upload import upload_file, download_url


def tracked_subscribe(
    endpoint: str,
    arguments: dict,
    *,
    kind: str,
    mp: float | None = None,
    seconds: float | None = None,
    calls: int = 1,
    note: str = "",
    project_dir: Path | None = None,
    with_logs: bool = False,
) -> dict:
    """The single fal.ai paid-call gateway (M4 cost tracking): every
    subscribe-style call routes through here so ledger recording lives in one
    place, not per-callsite. Recording happens only after a successful
    response (fal bills successful runs). Attribution: explicit `project_dir`
    wins, else the request-scoped context set by the API's _load_project
    (grafik.core.costs)."""
    result = fal_client.subscribe(endpoint, arguments=arguments, with_logs=with_logs)
    record_paid_call(
        endpoint, kind, mp=mp, seconds=seconds, calls=calls, note=note, project_dir=project_dir
    )
    return result


class FalClient:
    """Wrapper around fal.ai Qwen-Image-Layered API."""

    MODEL_I2L = "fal-ai/qwen-image-layered"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("FAL_API_KEY", "")
        if self.api_key:
            os.environ["FAL_KEY"] = self.api_key

    def decompose(
        self,
        image_url: str,
        num_layers: int = 4,
        *,
        project: LayerProject | None = None,
        project_dir: Path | None = None,
    ) -> list[Layer]:
        """Decompose an image into RGBA layers (I2L mode).

        Args:
            image_url: URL of the image to decompose.
            num_layers: Number of layers to extract (1-10).
            project: Optional LayerProject to add layers to.
            project_dir: Directory to save layer PNGs. Required if project given.

        Returns:
            List of Layer objects with PNGs saved to project_dir. Layer PNGs
            keep fal's native output resolution (~0.4 MP); when `project`
            already has a canvas, the layer layout (width/height) is
            stretched onto it and the composer resizes at compose time.
        """
        result = tracked_subscribe(
            self.MODEL_I2L,
            {
                "image_url": image_url,
                "num_layers": num_layers,
            },
            kind="decompose",
            note=f"i2l num_layers={num_layers}",
            project_dir=project_dir,
        )

        layers: list[Layer] = []
        layer_images = result.get("layers") or result.get("images") or []

        for i, layer_data in enumerate(layer_images):
            url = layer_data if isinstance(layer_data, str) else layer_data.get("url", "")
            if not url:
                continue

            layer = Layer(
                name=f"Layer {i}",
                z_order=i,
                source="fal:i2l",
                tags=["decomposed"],
            )

            # Download and save
            img = download_url(url)
            if project_dir:
                layer.save_image(img, project_dir)
                layer.width = img.width
                layer.height = img.height
            else:
                # Save to temp dir
                tmp = Path(tempfile.mkdtemp(prefix="grafik_"))
                layer.save_image(img, tmp)

            if project:
                project.add_layer(layer)
                if not project.canvas_width:
                    project.canvas_width = img.width
                if not project.canvas_height:
                    project.canvas_height = img.height
                # I2L returns layers at the model's native resolution
                # (~0.4 MP, e.g. 544x736 for a 3:4 input) regardless of the
                # input size. With a canvas pre-set from the source image
                # (decompose_file endpoint) the content would sit in the
                # top-left corner -- stretch the layout onto the canvas;
                # pixel data stays native, the composer resizes at compose
                # time (same boundary as QwenInpaintProvider's resize-back).
                layer.width = project.canvas_width
                layer.height = project.canvas_height

            layers.append(layer)

        return layers

    def decompose_file(
        self,
        file_path: Path,
        num_layers: int = 4,
        *,
        project: LayerProject | None = None,
        project_dir: Path | None = None,
    ) -> list[Layer]:
        """Decompose a local image file into layers."""
        url = upload_file(file_path)
        return self.decompose(
            url, num_layers, project=project, project_dir=project_dir
        )
