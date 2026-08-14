"""Base types for the fal.ai provider registry: capability flags, provider
metadata, and minimal abstract interfaces for image-edit / video / segment
providers.

See docs/capabilities/kling-versions.md and
docs/capabilities/model-landscape-2026-08.md for the verified (2026-08-14,
raw-OpenAPI-schema) capability data this package encodes, and
docs/plans/2026-08-14-phase1-gate.md for why video providers are
prompt-based rather than payload-based — no fal.ai video endpoint accepts a
structured mask/camera payload today.
"""

from __future__ import annotations

from typing import Any, Literal

from PIL import Image
from pydantic import BaseModel, Field

ProviderKind = Literal["image_edit", "video", "segment"]


class Capabilities(BaseModel):
    """Capability flags for one fal.ai provider endpoint.

    Every value must trace back to a verified capability doc, not a
    search-summary claim (kling-versions.md's methodology note: WebFetch/
    WebSearch summaries proved unreliable for this data). `verified_at` is
    the date the fields were checked against the raw OpenAPI schema.
    """

    supports_mask: bool = False
    supports_dynamic_masks: bool = False
    supports_camera_params: bool = False
    supports_camera_preset: bool = False
    supports_camera_prompt: bool = False
    verified_at: str = ""
    notes: str = ""


class ProviderInfo(BaseModel):
    """Registry entry metadata for one fal.ai provider endpoint."""

    id: str
    endpoint: str
    kind: ProviderKind
    capabilities: Capabilities
    price_note: str = Field(
        default="",
        description=(
            "Unverified/secondary-sourced pricing hint — fal.ai's OpenAPI "
            "schema carries no pricing data."
        ),
    )


class ImageEditProvider:
    """Mask+prompt image edit provider (inpaint/fill style, e.g. qwen-inpaint, flux-fill)."""

    def edit(self, image: Image.Image, mask: Image.Image, prompt: str, **kw: Any) -> Image.Image:
        raise NotImplementedError


class VideoProvider:
    """Prompt-based image-to-video provider.

    No current fal.ai video endpoint accepts a structured mask/camera
    payload (docs/plans/2026-08-14-phase1-gate.md) — per-element motion and
    camera control are compiled into `prompt` text and verified post-hoc,
    not passed as payload fields. `build_payload` only builds the fal
    arguments dict; actual submission happens in the jobs layer (task 1.7).
    """

    def build_payload(self, image_url: str, prompt: str, duration: str, **kw: Any) -> dict:
        raise NotImplementedError


class SegmentProvider:
    """Text/point/box-prompted segmentation provider (e.g. sam-3)."""

    def segment(self, image: Image.Image, text: str) -> list[Image.Image]:
        raise NotImplementedError
