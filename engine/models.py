"""Request schema of POST /api/v2/images (contract: spec § 5)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

IMAGE_ROLES = ("subject", "geometry", "scene")
MAX_IMAGE_REFS = 10


class Ref(BaseModel):
    role: Literal["subject", "geometry", "scene", "style"] = "subject"
    b64: str | None = None
    path: str | None = None
    url: str | None = None
    ref_id: str | None = None       # an entry of the reference library (engine/reflib.py)
    # An image of the shared library: "<kind>/<slug>" (main image) or "<kind>/<slug>/<file>" (engine/api_knihovna.py)
    knihovna: str | None = None
    # Style refs: the words that describe the style. FLUX cannot transfer style
    # from an image (verified 2026-10-22), so a style ref is never sent as pixels.
    text: str | None = None
    license: str | None = None
    author: str | None = None
    source: str | None = None

    @model_validator(mode="after")
    def _one_source(self):
        # the API resolves ref_id / knihovna to the library file's path and keeps both (provenance)
        if self.ref_id and self.knihovna:
            raise ValueError("předloha je buď ref_id (schránka), nebo knihovna, ne obojí")
        given = [x for x in (self.b64, self.path or self.ref_id or self.knihovna, self.url) if x]
        if self.role != "style" and len(given) != 1:
            raise ValueError("obrazová předloha potřebuje právě jedno z b64 / path / url / ref_id / knihovna")
        if self.role == "style" and not (self.text or given):
            raise ValueError("stylová předloha potřebuje text (popis stylu) nebo obrázek")
        return self


def check_box(v: list[int] | None) -> list[int] | None:
    if v is None:
        return v
    if len(v) != 4 or not all(0 <= x <= 1000 for x in v):
        raise ValueError("bbox = [top, left, bottom, right] v rozsahu 0–1000")
    top, left, bottom, right = v
    if not (top < bottom and left < right):
        raise ValueError("bbox: top < bottom a left < right")
    return v


class LayoutItem(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_\-]+$")
    desc: str
    bbox: list[int] | None = None       # [top, left, bottom, right], 0–1000
    src_bbox: list[int] | None = None
    tgt_bbox: list[int] | None = None
    from_: str | None = Field(default=None, alias="from")

    model_config = {"populate_by_name": True}

    @field_validator("bbox", "src_bbox", "tgt_bbox")
    @classmethod
    def _box(cls, v):
        return check_box(v)


class EditSpec(BaseModel):
    """Edit of a region of the parent image. Outside the box(es) the parent is
    pasted back unchanged."""
    action: Literal["add", "remove", "move", "recolor"]
    bbox: list[int]                       # [top, left, bottom, right], 0–1000
    target_bbox: list[int] | None = None  # move only
    instruction: str = Field(min_length=1)

    @field_validator("bbox", "target_bbox")
    @classmethod
    def _box(cls, v):
        return check_box(v)

    @model_validator(mode="after")
    def _target(self):
        if (self.action == "move") != (self.target_bbox is not None):
            raise ValueError("target_bbox patří jen k akci move (a move ho potřebuje)")
        return self


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=1)
    backend: str = "flux-local"
    size: str = "1024x1024"
    n: int = Field(default=1, ge=1, le=4)
    seed: int | None = None
    steps: int | None = Field(default=None, ge=1, le=50)
    refs: list[Ref] = []
    layout: list[LayoutItem] = []
    # Free text, or the slug of a style card in the library (G4): the API swaps a slug for the card's words
    # and keeps the slug in style_id for the provenance.
    style: str | None = None
    style_id: str | None = None
    no_text: bool = True
    # Render at size × supersample (capped by the 8 GB ceiling) and downscale with
    # Lanczos — small figures deform less (verified 2026-10-22). flux-local only.
    supersample: float | None = Field(default=None, ge=1.0, le=4.0)
    # Lineage: "<job_id>/<n>" of the image this one was made from (variant or edit).
    parent: str | None = Field(default=None, pattern=r"^[\w\-]+/\d+$")
    edit: EditSpec | None = None
    # Czech text fields are translated to English for the target generator (engine/translate.py).
    translate: Literal["auto", "off"] = "auto"
    caller: str = "unknown"
    confirm_cost: bool = False

    @field_validator("size")
    @classmethod
    def _size(cls, v):
        try:
            w, h = (int(x) for x in v.lower().split("x"))
        except ValueError:
            raise ValueError("size ve tvaru ŠÍŘKAxVÝŠKA, např. 1024x1024") from None
        if w < 256 or h < 256 or w % 16 or h % 16:
            raise ValueError("šířka a výška: násobky 16, nejméně 256")
        return f"{w}x{h}"

    @model_validator(mode="after")
    def _edit_needs_parent(self):
        if self.edit and not self.parent:
            raise ValueError("úprava v rámečku potřebuje parent (obrázek, který se upravuje)")
        return self

    @model_validator(mode="after")
    def _ref_count(self):
        if sum(r.role in IMAGE_ROLES for r in self.refs) > MAX_IMAGE_REFS:
            raise ValueError(f"nejvýš {MAX_IMAGE_REFS} obrazových předloh")
        return self

    @property
    def width(self) -> int:
        return int(self.size.split("x")[0])

    @property
    def height(self) -> int:
        return int(self.size.split("x")[1])
