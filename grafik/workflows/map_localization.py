"""Map localization workflow — decompose map, swap text layers, recompose."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from grafik.core.project import LayerProject
from grafik.ops.replace import replace_content
from grafik.workflows.base import WorkflowBase

from PIL import Image


class MapLocalizationWorkflow(WorkflowBase):
    """Workflow: decompose a map image → identify text layers → replace with localized versions.

    Steps:
    1. decompose — split map into layers via fal.ai
    2. identify_text_layers — tag layers containing text
    3. replace_text_layers — swap tagged layers with localized versions
    4. composite — flatten to final image
    """

    name = "map_localization"
    description = "Decompose map → swap text layers → composite CZ version"

    def setup(self) -> None:
        self.add_step("decompose", self._decompose)
        self.add_step("identify_text_layers", self._identify_text)
        self.add_step("replace_text_layers", self._replace_text)
        self.add_step("composite", self._composite)

    def _decompose(self, ctx: dict[str, Any]) -> dict:
        """Decompose source image into layers."""
        image_url = ctx.get("image_url")
        num_layers = ctx.get("num_layers", 6)
        if not image_url:
            raise ValueError("image_url is required")

        from grafik.fal.client import FalClient
        client = FalClient()
        layers = client.decompose(
            image_url, num_layers,
            project=self.project, project_dir=self.project_dir,
        )
        return {"decomposed_layers": [l.id for l in layers]}

    def _identify_text(self, ctx: dict[str, Any]) -> dict:
        """Tag layers that likely contain text (by name/tags or user hint)."""
        text_layer_ids = ctx.get("text_layer_ids", [])
        text_layer_names = ctx.get("text_layer_names", [])

        if not text_layer_ids and not text_layer_names:
            # Auto-detect: tag layers with "text" in name or small relative area
            for layer in self.project.layers:
                name_lower = (layer.name or "").lower()
                if any(kw in name_lower for kw in ("text", "label", "title", "caption", "popis")):
                    text_layer_ids.append(layer.id)
                    layer.tags = list(set(layer.tags + ["text"]))
        else:
            for layer in self.project.layers:
                if layer.id in text_layer_ids or layer.name in text_layer_names:
                    text_layer_ids.append(layer.id)
                    layer.tags = list(set(layer.tags + ["text"]))

        return {"text_layer_ids": list(set(text_layer_ids))}

    def _replace_text(self, ctx: dict[str, Any]) -> dict:
        """Replace text layers with provided localized images."""
        text_layer_ids = ctx.get("text_layer_ids", [])
        replacements = ctx.get("replacements", {})  # {layer_id: Image or path}

        replaced = []
        for lid in text_layer_ids:
            layer = self.project.get_layer(lid)
            if not layer:
                continue
            replacement = replacements.get(lid)
            if replacement is None:
                continue
            if isinstance(replacement, (str, Path)):
                replacement = Image.open(replacement).convert("RGBA")
            replace_content(layer, replacement, self.project_dir, fit="stretch")
            replaced.append(lid)

        return {"replaced_layers": replaced}

    def _composite(self, ctx: dict[str, Any]) -> dict:
        """Compose final image."""
        from grafik.core.composer import compose_and_save
        output = self.project_dir / "composites" / "localized.png"
        compose_and_save(self.project, self.project_dir, output)
        return {"output_path": str(output)}
