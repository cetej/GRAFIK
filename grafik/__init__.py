"""GRAFIK — Modular layered image editor."""

from grafik.core.layer import Layer, BlendMode
from grafik.core.project import LayerProject
from grafik.core.composer import compose
from grafik.core.history import History

__all__ = ["Layer", "BlendMode", "LayerProject", "compose", "History"]
__version__ = "0.2.0"
