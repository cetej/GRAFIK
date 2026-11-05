from io import BytesIO

import numpy as np
from PIL import Image

from engine.models import EditSpec
from engine.paste import paste_back

BOX = [300, 300, 600, 600]


def png(a: np.ndarray) -> bytes:
    buf = BytesIO()
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(buf, "PNG")
    return buf.getvalue()


def gradient(h=600, w=400) -> np.ndarray:
    y = np.linspace(40, 160, h)[:, None, None]
    return np.broadcast_to(np.concatenate([y * 0.3, y * 0.8, y], -1), (h, w, 3)).astype(np.float32).copy()


def test_tone_shift_leaves_no_seam_and_keeps_the_edit():
    """FLUX returns the whole picture with a shifted tone; the edited box must meet its surroundings."""
    parent = gradient()
    result = parent + np.array([4.0, -6.0, -14.0])   # the generator's global tone shift
    result[230:310, 150:230] = [200, 60, 60]          # the new content inside the box
    out = np.asarray(Image.open(BytesIO(paste_back(png(parent), png(result),
                                                   EditSpec(action="add", bbox=BOX, instruction="a red square")))), float)
    h, w = parent.shape[:2]
    top, left, bottom, right = (v * s / 1000 for v, s in zip(BOX, (h, w, h, w)))
    m = round(0.01 * max(h, w))
    row = slice(int(top) + 20, int(bottom) - 20)
    inside = out[row, int(left) + 2:int(left) + 8].mean((0, 1))
    outside = out[row, int(left) - m - 14:int(left) - m - 8].mean((0, 1))
    assert np.abs(inside - outside).max() < 3            # was 14 without the tone correction
    assert np.abs(out[250:290, 170:210] - [200, 60, 60]).max() < 20   # the edit itself stays
    far = np.ones(out.shape[:2], bool)
    far[int(top) - m - 20:int(bottom) + m + 20, int(left) - m - 20:int(right) + m + 20] = False
    assert np.abs(out - parent.astype(np.uint8))[far].max() == 0  # outside the box the parent is untouched


def test_without_tone_shift_result_is_unchanged_inside():
    parent = gradient()
    result = parent.copy()
    result[230:310, 150:230] = [10, 200, 10]
    out = np.asarray(Image.open(BytesIO(paste_back(png(parent), png(result),
                                                   EditSpec(action="add", bbox=BOX, instruction="x")))), float)
    assert np.abs(out[200:340, 140:240] - result.astype(np.uint8)[200:340, 140:240]).max() <= 1
