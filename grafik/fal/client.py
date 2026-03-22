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

from grafik.core.layer import Layer
from grafik.core.project import LayerProject
from grafik.fal.upload import upload_file, download_url


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
            List of Layer objects with PNGs saved to project_dir.
        """
        result = fal_client.subscribe(
            self.MODEL_I2L,
            arguments={
                "image_url": image_url,
                "num_layers": num_layers,
            },
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
