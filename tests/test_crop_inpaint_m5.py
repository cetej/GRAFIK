"""Tests for M5 crop-based inpaint (grafik/providers/qwen_inpaint.py,
grafik/providers/flux_fill.py). No network calls: each provider's one
network method (_run_remote) is monkeypatched, matching the pattern in
tests/test_providers.py.

Covers: compute_crop_box's own decision/margin/clamp logic in isolation,
then edit()-level integration for both mask-based providers (crop actually
sent to the remote at full native resolution, crop_inpaint=False escape
hatch, below-cap canvases and oversized masks skipping crop, and the
regression criterion that paste-back still zeroes out any drift outside the
mask even though the crop covers a wider area than the mask itself).
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from grafik.providers.flux_fill import FluxFillProvider
from grafik.providers.qwen_inpaint import (
    CROP_MAX_MASK_FRACTION,
    CROP_MIN_LONG_EDGE,
    QwenInpaintProvider,
    compute_crop_box,
)


def _box_mask(size: tuple[int, int], box: tuple[int, int, int, int]) -> Image.Image:
    """Sharp binary mask: `size` is (W, H); `box` is (left, top, right, bottom)."""
    arr = np.zeros(size[::-1], dtype=np.uint8)
    left, top, right, bottom = box
    arr[top:bottom, left:right] = 255
    return Image.fromarray(arr, mode="L")


def _center_box(canvas_size: tuple[int, int], box_size: int) -> tuple[int, int, int, int]:
    w, h = canvas_size
    cx, cy = w // 2, h // 2
    half = box_size // 2
    return (cx - half, cy - half, cx + half, cy + half)


# --------------------------------------------------------------------------
# Item 6: compute_crop_box in isolation -- decision logic, margin, clamp
# --------------------------------------------------------------------------


class TestCropConstants:
    def test_constants_match_spec(self):
        # Locks the M5 spec's thresholds -- changing these changes cost/
        # quality tradeoffs and should be a deliberate, visible diff.
        assert CROP_MAX_MASK_FRACTION == 0.25
        assert CROP_MIN_LONG_EDGE == 1536


class TestComputeCropBox:
    def test_empty_mask_returns_none(self):
        size = (2048, 2048)
        mask = Image.new("L", size, 0)
        assert compute_crop_box(mask, size) is None

    def test_canvas_at_cap_returns_none(self):
        # max(w, h) <= CROP_MIN_LONG_EDGE -> "<=" per spec, so exactly-at-cap
        # also skips cropping.
        size = (CROP_MIN_LONG_EDGE, CROP_MIN_LONG_EDGE)
        mask = _box_mask(size, (700, 700, 800, 800))
        assert compute_crop_box(mask, size) is None

    def test_canvas_just_above_cap_with_small_mask_crops(self):
        size = (CROP_MIN_LONG_EDGE + 1, CROP_MIN_LONG_EDGE + 1)
        mask = _box_mask(size, (700, 700, 800, 800))
        assert compute_crop_box(mask, size) is not None

    def test_large_mask_fraction_returns_none(self):
        size = (2048, 2048)
        # 1200x1200 box ~= 34% of the 2048x2048 canvas -> >= 25% threshold.
        mask = _box_mask(size, (0, 0, 1200, 1200))
        assert compute_crop_box(mask, size) is None

    def test_mask_fraction_just_under_threshold_crops(self):
        size = (2048, 2048)
        # 1000x1000 box ~= 23.8% of the canvas -> under the 25% threshold.
        box = _center_box(size, 1000)
        mask = _box_mask(size, box)
        assert compute_crop_box(mask, size) is not None

    def test_margin_and_clamp_center(self):
        size = (2048, 2048)
        box = (924, 924, 1124, 1124)  # 200x200, centered, far from any edge
        mask = _box_mask(size, box)

        crop = compute_crop_box(mask, size)

        # margin = max(64, round(0.25 * 200)) = max(64, 50) = 64
        assert crop == (924 - 64, 924 - 64, 1124 + 64, 1124 + 64)

    def test_margin_uses_bbox_longer_edge(self):
        size = (2048, 2048)
        box = (900, 800, 1100, 1200)  # 200 wide x 400 tall
        mask = _box_mask(size, box)

        crop = compute_crop_box(mask, size)

        # margin = max(64, round(0.25 * 400)) = max(64, 100) = 100
        assert crop == (900 - 100, 800 - 100, 1100 + 100, 1200 + 100)

    def test_margin_and_clamp_top_left_corner(self):
        size = (2048, 2048)
        box = (0, 0, 200, 200)  # touches the top-left corner
        mask = _box_mask(size, box)

        crop = compute_crop_box(mask, size)

        assert crop == (0, 0, 200 + 64, 200 + 64)

    def test_margin_and_clamp_bottom_right_corner(self):
        size = (2048, 2048)
        box = (1848, 1848, 2048, 2048)  # touches the bottom-right corner
        mask = _box_mask(size, box)

        crop = compute_crop_box(mask, size)

        assert crop == (1848 - 64, 1848 - 64, 2048, 2048)


# --------------------------------------------------------------------------
# Items 1-5: QwenInpaintProvider.edit() -- offline (network monkeypatched)
# --------------------------------------------------------------------------


class TestQwenCropInpaintOffline:
    def test_crop_sends_only_crop_region_to_remote(self, monkeypatch):
        """Item 1: fake _run_remote must receive an image the exact size of
        compute_crop_box's own crop box, not the full 2048x2048 canvas."""
        provider = QwenInpaintProvider()
        size = (2048, 2048)
        image = Image.new("RGB", size, (10, 20, 30))
        box = _center_box(size, 200)
        mask = _box_mask(size, box)

        expected_crop = compute_crop_box(mask, size)
        assert expected_crop is not None
        expected_size = (
            expected_crop[2] - expected_crop[0],
            expected_crop[3] - expected_crop[1],
        )

        calls: dict = {}

        def fake_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
            calls["image_size"] = image.size
            calls["mask_size"] = mask.size
            return Image.new("RGB", image.size, (200, 150, 100))

        monkeypatch.setattr(QwenInpaintProvider, "_run_remote", fake_run_remote)

        out = provider.edit(image, mask, "recolor")

        assert calls["image_size"] == expected_size
        assert calls["image_size"] != size
        assert calls["mask_size"] == calls["image_size"]
        assert out.size == size

    def test_crop_result_matches_outside_and_inside(self, monkeypatch):
        """Item 2: outside the dilated+feathered mask zone, the output must
        equal the input exactly (paste-back stays load-bearing even though
        the crop itself covers a much wider area than the mask); deep inside
        the hard mask, the output must equal the fake remote's color."""
        provider = QwenInpaintProvider()
        size = (2048, 2048)
        input_color = (10, 20, 30)
        fake_color = (200, 150, 100)
        image = Image.new("RGB", size, input_color)
        box = (924, 924, 1124, 1124)  # 200x200 centered
        mask = _box_mask(size, box)

        def fake_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
            return Image.new("RGB", image.size, fake_color)

        monkeypatch.setattr(QwenInpaintProvider, "_run_remote", fake_run_remote)

        out = provider.edit(image, mask, "recolor")
        out_arr = np.array(out)
        input_arr = np.array(image)

        # Deep inside the hard mask (50px clear of its edge -- well beyond
        # the ~10-15px dilate+feather falloff) -> fake remote's color.
        inner = out_arr[974:1074, 974:1074]
        assert np.array_equal(inner, np.broadcast_to(np.array(fake_color, dtype=np.uint8), inner.shape))

        # Everywhere at least 50px clear of the mask edge (874:1174 pad) is
        # outside the feather falloff, whether or not it's still inside the
        # crop rectangle (crop extends to 860:1188) -> unchanged input.
        outside = np.ones(size[::-1], dtype=bool)
        outside[874:1174, 874:1174] = False
        assert np.array_equal(out_arr[outside], input_arr[outside])

    def test_crop_inpaint_false_sends_full_canvas(self, monkeypatch):
        """Item 3: the same mask/canvas that triggers cropping in item 1
        must send the full canvas when crop_inpaint=False."""
        provider = QwenInpaintProvider()
        size = (2048, 2048)
        image = Image.new("RGB", size, (10, 20, 30))
        box = _center_box(size, 200)
        mask = _box_mask(size, box)

        calls: dict = {}

        def fake_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
            calls["image_size"] = image.size
            return Image.new("RGB", image.size, (200, 150, 100))

        monkeypatch.setattr(QwenInpaintProvider, "_run_remote", fake_run_remote)

        out = provider.edit(image, mask, "recolor", crop_inpaint=False)

        assert calls["image_size"] == size
        assert out.size == size

    def test_canvas_under_cap_skips_crop(self, monkeypatch):
        """Item 4: a 1024x1024 canvas is under CROP_MIN_LONG_EDGE -> the
        full canvas is sent even with crop_inpaint's default True."""
        provider = QwenInpaintProvider()
        size = (1024, 1024)
        image = Image.new("RGB", size, (10, 20, 30))
        box = _center_box(size, 100)
        mask = _box_mask(size, box)

        calls: dict = {}

        def fake_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
            calls["image_size"] = image.size
            return Image.new("RGB", image.size, (200, 150, 100))

        monkeypatch.setattr(QwenInpaintProvider, "_run_remote", fake_run_remote)

        provider.edit(image, mask, "recolor")

        assert calls["image_size"] == size

    def test_large_mask_fraction_skips_crop(self, monkeypatch):
        """Item 5: a mask covering >= 25% of a 2048x2048 canvas sends the
        full canvas -- the mask isn't "small" relative to the canvas."""
        provider = QwenInpaintProvider()
        size = (2048, 2048)
        image = Image.new("RGB", size, (10, 20, 30))
        box = (0, 0, 1200, 1200)  # ~34% of the canvas
        mask = _box_mask(size, box)

        calls: dict = {}

        def fake_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
            calls["image_size"] = image.size
            return Image.new("RGB", image.size, (200, 150, 100))

        monkeypatch.setattr(QwenInpaintProvider, "_run_remote", fake_run_remote)

        provider.edit(image, mask, "recolor")

        assert calls["image_size"] == size


# --------------------------------------------------------------------------
# Item 7: FluxFillProvider -- same crop wiring, smoke-tested (items 1 + 3)
# --------------------------------------------------------------------------


class TestFluxFillCropInpaintOffline:
    def test_crop_sends_only_crop_region_to_remote(self, monkeypatch):
        provider = FluxFillProvider()
        size = (2048, 2048)
        image = Image.new("RGB", size, (10, 20, 30))
        box = _center_box(size, 200)
        mask = _box_mask(size, box)

        expected_crop = compute_crop_box(mask, size)
        assert expected_crop is not None
        expected_size = (
            expected_crop[2] - expected_crop[0],
            expected_crop[3] - expected_crop[1],
        )

        calls: dict = {}

        def fake_run_remote(self, image, mask, prompt, safety_tolerance):
            calls["image_size"] = image.size
            calls["mask_size"] = mask.size
            return Image.new("RGB", image.size, (200, 150, 100))

        monkeypatch.setattr(FluxFillProvider, "_run_remote", fake_run_remote)

        out = provider.edit(image, mask, "fill the hole with grass")

        assert calls["image_size"] == expected_size
        assert calls["image_size"] != size
        assert calls["mask_size"] == calls["image_size"]
        assert out.size == size

    def test_crop_inpaint_false_sends_full_canvas(self, monkeypatch):
        provider = FluxFillProvider()
        size = (2048, 2048)
        image = Image.new("RGB", size, (10, 20, 30))
        box = _center_box(size, 200)
        mask = _box_mask(size, box)

        calls: dict = {}

        def fake_run_remote(self, image, mask, prompt, safety_tolerance):
            calls["image_size"] = image.size
            return Image.new("RGB", image.size, (200, 150, 100))

        monkeypatch.setattr(FluxFillProvider, "_run_remote", fake_run_remote)

        out = provider.edit(image, mask, "fill the hole with grass", crop_inpaint=False)

        assert calls["image_size"] == size
        assert out.size == size
