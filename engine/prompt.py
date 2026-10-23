"""Request -> FLUX prompt text.

Format verified 2026-10-22 (models/flux3-klein/prompt_edit.txt): image refs are
addressed as <ref_image_N> in request order, layout objects as <id> tags in the
text plus a trailing JSON list with [top, left, bottom, right] boxes on a
0–1000 grid (the same order as NG-ROBOT's [y_min, x_min, y_max, x_max]).
"""
from __future__ import annotations

import json

from engine.models import IMAGE_ROLES, ImageRequest

NO_TEXT = "No text, no letters, no labels."


def style_words(req: ImageRequest, described: dict[int, str] | None = None) -> list[str]:
    """Every style source as words: the `style` field plus each style ref's text
    (or the description produced for an image-only style ref)."""
    out = [req.style.strip()] if req.style and req.style.strip() else []
    for i, r in enumerate(req.refs):
        if r.role == "style":
            text = r.text or (described or {}).get(i)
            if text:
                out.append(text.strip())
    return out


EDIT_TEMPLATES = {
    "remove": ("In <ref_image_0>, remove <edit_1> ({i}) and fill the area where it was with the surrounding "
               "background, so it looks as if it had never been there. Keep everything else exactly as it is."),
    "add": "In <ref_image_0>, add <edit_1>: {i}, inside the marked area. Keep everything else exactly as it is.",
    "move": ("In <ref_image_0>, move <edit_1> ({i}) from its current place to the target area, and fill the place "
             "where it stood with the surrounding background. Keep everything else exactly as it is."),
    "recolor": ("In <ref_image_0>, change <edit_1>: {i}. Keep its shape, position and lighting, and keep "
                "everything else exactly as it is."),
}


def edit_layout(req: ImageRequest) -> list[dict]:
    """Same JSON shape as the verified edit prompt (models/flux3-klein/prompt_edit.txt):
    src_bbox = where the object is in ref_image_0, tgt_bbox = where it should end up, null = gone."""
    e = req.edit
    src = {"remove": e.bbox, "add": None, "move": e.bbox, "recolor": e.bbox}[e.action]
    tgt = {"remove": None, "add": e.bbox, "move": e.target_bbox, "recolor": e.bbox}[e.action]
    return [{"id": "edit_1", "from": "ref_image_0", "src_bbox": src, "tgt_bbox": tgt, "desc": e.instruction}]


def build_prompt(req: ImageRequest, described: dict[int, str] | None = None) -> str:
    if req.edit:
        parts = [EDIT_TEMPLATES[req.edit.action].format(i=req.edit.instruction.strip().rstrip("."))]
    else:
        parts = [req.prompt.strip()]
    if parts[0] and parts[0][-1] not in ".!?":
        parts[0] += "."
    styles = style_words(req, described)
    if styles:
        parts.append("Style: " + " ".join(s.rstrip(".") + "." for s in styles))
    if req.no_text and "no text" not in req.prompt.lower():
        parts.append(NO_TEXT)
    text = " ".join(parts)
    if req.edit:
        text += " " + json.dumps(edit_layout(req), ensure_ascii=False)
    elif req.layout:
        items = []
        for item in req.layout:
            d = {"id": item.id}
            if item.from_:
                d["from"] = item.from_
            for key in ("bbox", "src_bbox", "tgt_bbox"):
                val = getattr(item, key)
                if val is not None:
                    d[key] = val
            d["desc"] = item.desc
            items.append(d)
        text += " " + json.dumps(items, ensure_ascii=False)
    return text


def image_ref_indices(req: ImageRequest) -> list[int]:
    """Positions in req.refs that go to FLUX as pixels (<ref_image_0>, ...)."""
    return [i for i, r in enumerate(req.refs) if r.role in IMAGE_ROLES]
