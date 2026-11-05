"""Paste-back for region edits: outside the edited box(es) the parent stays
pixel-identical (old GRAFIK lesson: generative edits drift globally, paste-back
is mandatory — docs/LEARNINGS.md)."""
from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from engine.models import EditSpec

MARGIN = 0.01     # of the image's longer side, added around each box; 2 % cut into an infographic title
FEATHER_PX = 6
TONE_GRID = 48    # cells along the longer side of the edited area for the tone correction
TONE_ITER = 400
TONE_OUTLIER = 24  # levels off the median shift: content changed there, not tone
TONE_MAX = 40      # a larger median shift is a different picture, not drift (measured drift 12-24)


def edit_mask(size: tuple[int, int], edit: EditSpec) -> Image.Image:
    if edit.mask:       # tvar objektu, rozšířený a změkčený už při uložení (engine/objekty.py)
        return Image.open(edit.mask).convert("L").resize(size, Image.BILINEAR)
    w, h = size
    m = round(MARGIN * max(w, h))
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for box in filter(None, (edit.bbox, edit.target_bbox)):
        top, left, bottom, right = box
        draw.rectangle([left * w / 1000 - m, top * h / 1000 - m, right * w / 1000 + m, bottom * h / 1000 + m],
                       fill=255)
    return mask.filter(ImageFilter.GaussianBlur(FEATHER_PX))


def match_tone(parent: Image.Image, result: Image.Image, mask: Image.Image) -> Image.Image:
    """FLUX shifts the tone of the whole picture (a dark blue gradient came back flat and 12-24 levels off,
    a visible rectangle on the whale infographic 2026-11-05). The difference parent - result along the mask
    edge is spread smoothly over the inside (membrane, solved on a small grid), so the edit meets its
    surroundings without a seam and keeps its own detail."""
    p = np.asarray(parent, np.float32)
    r = np.asarray(result, np.float32)
    hard = np.asarray(mask) > 127
    ys, xs = np.nonzero(hard)
    if not len(ys):
        return result
    h, w = hard.shape
    step = max(1, round(max(np.ptp(ys), np.ptp(xs)) / TONE_GRID))
    # the mask's area and two cells of its surroundings, cut into cells of step x step px
    y0, x0 = max(ys.min() - 2 * step, 0), max(xs.min() - 2 * step, 0)
    y1, x1 = min(ys.max() + 1 + 2 * step, h), min(xs.max() + 1 + 2 * step, w)
    gh, gw = -(-(y1 - y0) // step), -(-(x1 - x0) // step)

    def cells(a: np.ndarray) -> np.ndarray:
        a = np.pad(a[y0:y1, x0:x1], [(0, gh * step - (y1 - y0)), (0, gw * step - (x1 - x0))]
                   + [(0, 0)] * (a.ndim - 2), mode="edge")
        return a.reshape(gh, step, gw, step, *a.shape[2:]).mean((1, 3))

    # inside = the whole cell is in the mask; every other cell keeps the measured difference (boundary)
    inside = cells(hard.astype(np.float32)) > 0.999
    if not inside.any() or inside.all():
        return result
    field = cells(p - r)
    # a boundary cell where FLUX drew different content (title letters redrawn) is no tone sample
    med = np.median(field[~inside], axis=0)
    if np.abs(med).max() > TONE_MAX:  # not the same picture with a drifted tone; leave the result alone
        return result
    inside |= np.abs(field - med).max(-1) > TONE_OUTLIER
    field[inside] = med  # the start; the new content inside must not leak into the correction
    for _ in range(TONE_ITER):  # Jacobi; the picture's own edge is a free border (edge padding)
        f = np.pad(field, [(1, 1), (1, 1), (0, 0)], mode="edge")
        avg = (f[:-2, 1:-1] + f[2:, 1:-1] + f[1:-1, :-2] + f[1:-1, 2:]) / 4
        field = np.where(inside[..., None], avg, field)
    size = (gw * step, gh * step)
    big = np.stack([np.asarray(Image.fromarray(field[..., c]).resize(size, Image.BILINEAR)) for c in range(3)], -1)
    out = r.copy()
    out[y0:y1, x0:x1] += big[:y1 - y0, :x1 - x0]
    return Image.fromarray(np.clip(out, 0, 255).round().astype(np.uint8))


def paste_back(parent_png: bytes, result_png: bytes, edit: EditSpec) -> bytes:
    parent = Image.open(BytesIO(parent_png)).convert("RGB")
    result = Image.open(BytesIO(result_png)).convert("RGB")
    if result.size != parent.size:
        result = result.resize(parent.size, Image.LANCZOS)
    mask = edit_mask(parent.size, edit)
    out = Image.composite(match_tone(parent, result, mask), parent, mask)
    buf = BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()
