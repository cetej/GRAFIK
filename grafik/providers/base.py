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

ProviderKind = Literal["image_edit", "video", "segment", "image_gen", "decompose"]


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
    # M3 (video jobs): per-provider payload shape, consumed by
    # grafik.motion.compiler.build_video_payload. Only "video" kind entries
    # use these meaningfully today, but they live on the shared model rather
    # than a video-only subclass to keep the registry a single flat dict.
    image_field: str = "image_url"
    payload_defaults: dict = Field(default_factory=dict)
    duration_choices: list[str] = Field(default_factory=lambda: ["5", "10"])
    est_cost_usd_per_second: float | None = None
    # M4 (cost tracking): per-MP / per-call rate estimates for non-video
    # endpoints — same secondary-source trust level as price_note (fal model
    # pages / ai.google.dev, fetch dates in each entry's price_note).
    # grafik.core.costs.estimate_usd picks whichever field matches the units
    # the call site measured.
    est_cost_usd_per_mp: float | None = None
    est_cost_usd_per_call: float | None = None


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


class ImageGenProvider:
    """Text→image generation provider (e.g. nb-pro).

    Produces the INPUT image for a project (generate → decompose). Not a
    per-element editor — NB Pro accepts no pixel mask, only global/semantic
    instructions, and embeds a SynthID watermark (M4)."""

    def generate(self, prompt: str, **kw: Any) -> Image.Image:
        raise NotImplementedError
