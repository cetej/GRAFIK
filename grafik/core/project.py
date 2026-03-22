"""LayerProject — save/load .grafik directories."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from grafik.core.layer import Layer


class LayerProject(BaseModel):
    """A layered image project stored as a .grafik directory."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    canvas_width: int = 0
    canvas_height: int = 0
    layers: list[Layer] = Field(default_factory=list)
    source_image_url: str = ""
    metadata: dict = Field(default_factory=dict)

    @classmethod
    def new(cls, name: str, width: int = 0, height: int = 0) -> LayerProject:
        return cls(name=name, canvas_width=width, canvas_height=height)

    @classmethod
    def load(cls, path: Path) -> LayerProject:
        """Load from a .grafik directory."""
        manifest = path / "project.json"
        if not manifest.exists():
            raise FileNotFoundError(f"No project.json in {path}")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return cls.model_validate(data)

    def save(self, path: Path) -> Path:
        """Save to a .grafik directory. Returns the directory path."""
        if not str(path).endswith(".grafik"):
            path = path.with_suffix(".grafik")
        path.mkdir(parents=True, exist_ok=True)
        (path / "layers").mkdir(exist_ok=True)
        (path / "composites").mkdir(exist_ok=True)

        self.updated_at = datetime.now(timezone.utc).isoformat()
        manifest = path / "project.json"
        manifest.write_text(
            self.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return path

    def get_layer(self, layer_id: str) -> Layer | None:
        for layer in self.layers:
            if layer.id == layer_id:
                return layer
        return None

    def add_layer(self, layer: Layer) -> None:
        if not layer.z_order:
            layer.z_order = len(self.layers)
        self.layers.append(layer)
        self._sort_layers()

    def remove_layer(self, layer_id: str) -> Layer | None:
        for i, layer in enumerate(self.layers):
            if layer.id == layer_id:
                removed = self.layers.pop(i)
                self._reindex()
                return removed
        return None

    def reorder(self, layer_id: str, new_z: int) -> None:
        layer = self.get_layer(layer_id)
        if layer:
            layer.z_order = new_z
            self._sort_layers()
            self._reindex()

    def visible_layers(self) -> list[Layer]:
        """Layers sorted bottom-to-top, only visible ones."""
        return [l for l in self.layers if l.visible]

    def _sort_layers(self) -> None:
        self.layers.sort(key=lambda l: l.z_order)

    def _reindex(self) -> None:
        for i, layer in enumerate(self.layers):
            layer.z_order = i
