"""GRAFIK — Modular layered image editor."""

from grafik.core.layer import Layer, BlendMode
from grafik.core.project import LayerProject
from grafik.core.composer import compose

__all__ = ["Layer", "BlendMode", "LayerProject", "compose"]
__version__ = "0.1.0"
