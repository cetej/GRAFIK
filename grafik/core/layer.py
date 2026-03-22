"""Layer data model."""

from __future__ import annotations

import uuid
from enum import Enum
from pathlib import Path

from PIL import Image
from pydantic import BaseModel, Field


class BlendMode(str, Enum):
    NORMAL = "normal"
    MULTIPLY = "multiply"
    SCREEN = "screen"
    OVERLAY = "overlay"
    SOFT_LIGHT = "soft_light"


class Layer(BaseModel):
    """Single RGBA layer in a project."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    z_order: int = 0
    visible: bool = True
    opacity: float = 1.0
    blend_mode: BlendMode = BlendMode.NORMAL
    x: int = 0
    y: int = 0
    width: int | None = None
    height: int | None = None
    rotation: float = 0.0
    source: str = ""
    tags: list[str] = Field(default_factory=list)
    png_path: str = ""

    def load_image(self, project_dir: Path) -> Image.Image:
        """Load the RGBA PNG from disk."""
        path = project_dir / self.png_path
        img = Image.open(path)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        return img

    def save_image(self, img: Image.Image, project_dir: Path) -> None:
        """Save an RGBA image to disk and update png_path."""
        if not self.png_path:
            self.png_path = f"layers/{self.id}.png"
        path = project_dir / self.png_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        img.save(path, "PNG")
        if self.width is None:
            self.width = img.width
        if self.height is None:
            self.height = img.height
