"""Hero edit workflow — separate subject/background, swap, recompose."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from grafik.core.project import LayerProject
from grafik.ops.replace import replace_content
from grafik.workflows.base import WorkflowBase


class HeroEditWorkflow(WorkflowBase):
    """Workflow: decompose hero image → identify subject/background → swap → composite.

    Steps:
    1. decompose — split into layers
    2. identify_roles — tag subject vs background
    3. swap_background — replace background layer
    4. composite — flatten
    """

    name = "hero_edit"
    description = "Separate subject/background → swap background → composite"

    def setup(self) -> None:
        self.add_step("decompose", self._decompose)
        self.add_step("identify_roles", self._identify_roles)
        self.add_step("swap_content", self._swap_content)
        self.add_step("composite", self._composite)

    def _decompose(self, ctx: dict[str, Any]) -> dict:
        image_url = ctx.get("image_url")
        num_layers = ctx.get("num_layers", 3)
        if not image_url:
            raise ValueError("image_url is required")

        from grafik.fal.client import FalClient
        client = FalClient()
        layers = client.decompose(
            image_url, num_layers,
            project=self.project, project_dir=self.project_dir,
        )
        return {"decomposed_layers": [l.id for l in layers]}

    def _identify_roles(self, ctx: dict[str, Any]) -> dict:
        """Tag layers as 'subject' or 'background'.

        Uses hints from context or defaults: bottom layer = background, top = subject.
        """
        subject_id = ctx.get("subject_layer_id")
        background_id = ctx.get("background_layer_id")

        if not subject_id and not background_id and self.project.layers:
            sorted_layers = sorted(self.project.layers, key=lambda l: l.z_order)
            background_id = sorted_layers[0].id
            sorted_layers[0].tags = list(set(sorted_layers[0].tags + ["background"]))
            if len(sorted_layers) > 1:
                subject_id = sorted_layers[-1].id
                sorted_layers[-1].tags = list(set(sorted_layers[-1].tags + ["subject"]))

        return {"subject_layer_id": subject_id, "background_layer_id": background_id}

    def _swap_content(self, ctx: dict[str, Any]) -> dict:
        """Replace subject or background with provided images."""
        swapped = []

        for role in ("subject", "background"):
            layer_id = ctx.get(f"{role}_layer_id")
            new_image = ctx.get(f"new_{role}")  # Image or path
            if not layer_id or new_image is None:
                continue
            layer = self.project.get_layer(layer_id)
            if not layer:
                continue
            if isinstance(new_image, (str, Path)):
                new_image = Image.open(new_image).convert("RGBA")
            replace_content(layer, new_image, self.project_dir, fit="cover")
            swapped.append(role)

        return {"swapped": swapped}

    def _composite(self, ctx: dict[str, Any]) -> dict:
        from grafik.core.composer import compose_and_save
        output = self.project_dir / "composites" / "hero_edit.png"
        compose_and_save(self.project, self.project_dir, output)
        return {"output_path": str(output)}
