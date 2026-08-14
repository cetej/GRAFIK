"""Tests for grafik.core.composer rotation parity with Konva (task M2 #6).

Konva rotates a layer clockwise (y-down canvas coords) around its own
(x, y) anchor point; PIL's Image.rotate(expand=True) instead re-centers the
rotated content in a new bounding box. compose() corrects the paste position
via _rotation_offset so the two agree -- persisted transforms from ui-web
assume the Konva semantics.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from grafik.core.composer import compose
from grafik.core.layer import Layer
from grafik.core.project import LayerProject


def _project_with_red_rect(
    tmp_path: Path, *, x: int, y: int, w: int, h: int, rotation: float, canvas=(200, 200)
) -> tuple[LayerProject, Path]:
    """A single opaque red RGBA rectangle layer on an otherwise empty canvas."""
    project = LayerProject.new("rotation-test", canvas[0], canvas[1])
    project_dir = tmp_path / "rotation-test.grafik"
    layer = Layer(x=x, y=y, rotation=rotation, name="rect")
    img = Image.new("RGBA", (w, h), (255, 0, 0, 255))
    layer.save_image(img, project_dir)
    project.add_layer(layer)
    project.save(project_dir)
    return project, project_dir


class TestRotationParity:
    def test_rotation_90_matches_corner_rotation_formula(self, tmp_path):
        """20x10 rect anchored at (50, 50), rotated 90 deg clockwise around
        that anchor -> should land roughly in box x in [40, 50], y in [50, 70]
        (see _rotation_offset derivation in grafik/core/composer.py).
        """
        project, project_dir = _project_with_red_rect(tmp_path, x=50, y=50, w=20, h=10, rotation=90)
        composite = compose(project, project_dir)
        arr = np.array(composite)  # (H, W, 4), RGBA

        red = (arr[:, :, 0] > 200) & (arr[:, :, 3] > 200)
        ys, xs = np.nonzero(red)
        assert xs.size > 0, "expected some red pixels after rotation"

        assert 38 <= xs.min() <= 42
        assert 48 <= xs.max() <= 52
        assert 48 <= ys.min() <= 52
        assert 68 <= ys.max() <= 72

    def test_rotation_zero_is_unchanged_regression(self, tmp_path):
        """rotation=0 must paste at exactly (x, y) with no offset -- regression
        for existing projects (none of which use rotation today).
        """
        project, project_dir = _project_with_red_rect(tmp_path, x=50, y=50, w=20, h=10, rotation=0)
        arr = np.array(compose(project, project_dir))

        box = arr[50:60, 50:70]  # y: 50..60 (h=10), x: 50..70 (w=20)
        assert np.all(box[:, :, 0] == 255)
        assert np.all(box[:, :, 3] == 255)

        outside = arr.copy()
        outside[50:60, 50:70] = 0
        assert not np.any((outside[:, :, 0] > 200) & (outside[:, :, 3] > 200))
