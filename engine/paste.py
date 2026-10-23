"""Paste-back for region edits: outside the edited box(es) the parent stays
pixel-identical (old GRAFIK lesson: generative edits drift globally, paste-back
is mandatory — docs/LEARNINGS.md)."""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter

from engine.models import EditSpec

MARGIN = 0.02     # of the image's longer side, added around each box
FEATHER_PX = 6


def edit_mask(size: tuple[int, int], edit: EditSpec) -> Image.Image:
    w, h = size
    m = round(MARGIN * max(w, h))
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for box in filter(None, (edit.bbox, edit.target_bbox)):
        top, left, bottom, right = box
        draw.rectangle([left * w / 1000 - m, top * h / 1000 - m, right * w / 1000 + m, bottom * h / 1000 + m],
                       fill=255)
    return mask.filter(ImageFilter.GaussianBlur(FEATHER_PX))


def paste_back(parent_png: bytes, result_png: bytes, edit: EditSpec) -> bytes:
    parent = Image.open(BytesIO(parent_png)).convert("RGB")
    result = Image.open(BytesIO(result_png)).convert("RGB")
    if result.size != parent.size:
        result = result.resize(parent.size, Image.LANCZOS)
    out = Image.composite(result, parent, edit_mask(parent.size, edit))
    buf = BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()
