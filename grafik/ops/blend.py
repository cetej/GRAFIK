"""Blend mode implementations for compositing two RGBA images."""

from __future__ import annotations

import numpy as np
from PIL import Image


def _to_float(img: Image.Image) -> np.ndarray:
    """Convert RGBA image to float32 array (0-1)."""
    return np.array(img, dtype=np.float32) / 255.0


def _to_image(arr: np.ndarray) -> Image.Image:
    """Convert float32 array (0-1) back to RGBA image."""
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGBA")


def multiply(base: Image.Image, top: Image.Image) -> Image.Image:
    """Multiply blend: darkens by multiplying channels."""
    b, t = _to_float(base), _to_float(top)
    rgb = b[:, :, :3] * t[:, :, :3]
    return _compose_with_alpha(b, t, rgb)


def screen(base: Image.Image, top: Image.Image) -> Image.Image:
    """Screen blend: lightens — inverse of multiply."""
    b, t = _to_float(base), _to_float(top)
    rgb = 1 - (1 - b[:, :, :3]) * (1 - t[:, :, :3])
    return _compose_with_alpha(b, t, rgb)


def overlay(base: Image.Image, top: Image.Image) -> Image.Image:
    """Overlay blend: multiply dark areas, screen light areas."""
    b, t = _to_float(base), _to_float(top)
    base_rgb = b[:, :, :3]
    top_rgb = t[:, :, :3]
    mask = base_rgb < 0.5
    rgb = np.where(mask, 2 * base_rgb * top_rgb, 1 - 2 * (1 - base_rgb) * (1 - top_rgb))
    return _compose_with_alpha(b, t, rgb)


def soft_light(base: Image.Image, top: Image.Image) -> Image.Image:
    """Soft light blend: gentle contrast adjustment."""
    b, t = _to_float(base), _to_float(top)
    base_rgb = b[:, :, :3]
    top_rgb = t[:, :, :3]
    mask = top_rgb < 0.5
    rgb = np.where(
        mask,
        base_rgb - (1 - 2 * top_rgb) * base_rgb * (1 - base_rgb),
        base_rgb + (2 * top_rgb - 1) * (np.sqrt(base_rgb) - base_rgb),
    )
    return _compose_with_alpha(b, t, rgb)


def _compose_with_alpha(
    base: np.ndarray, top: np.ndarray, blended_rgb: np.ndarray
) -> Image.Image:
    """Combine blended RGB with proper alpha compositing."""
    base_a = base[:, :, 3:4]
    top_a = top[:, :, 3:4]
    out_a = top_a + base_a * (1 - top_a)
    safe_a = np.where(out_a > 0, out_a, 1)
    out_rgb = (blended_rgb * top_a + base[:, :, :3] * base_a * (1 - top_a)) / safe_a
    out = np.concatenate([out_rgb, out_a], axis=2)
    return _to_image(out)


BLEND_FUNCTIONS = {
    "multiply": multiply,
    "screen": screen,
    "overlay": overlay,
    "soft_light": soft_light,
}
