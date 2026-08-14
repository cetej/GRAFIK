"""Provider registry: fal.ai endpoint capability map for GRAFIK.

Every entry's `verified_at` traces back to a raw-OpenAPI-schema sweep, not a
search-engine summary — see docs/capabilities/kling-versions.md and
docs/capabilities/model-landscape-2026-08.md (both dated 2026-08-14).

Video endpoints are prompt-based: no current fal.ai video model accepts a
structured mask/camera payload (docs/plans/2026-08-14-phase1-gate.md,
architecture amendment A). The sole exception is kling-15-pro's
`dynamic_masks` field, which validates but produced a weak effect in the
task 1.2 smoke test — kept here only as a documented legacy option, not for
sc-2 use.
"""

from __future__ import annotations

from dataclasses import dataclass

from grafik.providers.base import Capabilities, ProviderInfo
from grafik.providers.qwen_inpaint import QwenInpaintProvider

VERIFIED_AT = "2026-08-14"

_UNVERIFIED_PRICE = "unverified/secondary — not in fal.ai OpenAPI schema, not confirmed in this sweep"


@dataclass
class RegistryEntry:
    """One registry slot: static capability metadata plus an optional concrete implementation."""

    info: ProviderInfo
    impl: type | None = None


REGISTRY: dict[str, RegistryEntry] = {
    # --- image_edit -----------------------------------------------------
    "qwen-inpaint": RegistryEntry(
        info=ProviderInfo(
            id="qwen-inpaint",
            endpoint="fal-ai/qwen-image-edit/inpaint",
            kind="image_edit",
            capabilities=Capabilities(
                supports_mask=True,
                verified_at=VERIFIED_AT,
                notes=(
                    "Proven flow (scripts/smoke_inpaint.py, falsifier A1 PASS). "
                    "Paste-back with a feathered mask is mandatory — raw "
                    "endpoint output drifts globally outside the mask."
                ),
            ),
            price_note=_UNVERIFIED_PRICE,
        ),
        impl=QwenInpaintProvider,
    ),
    "flux-fill": RegistryEntry(
        info=ProviderInfo(
            id="flux-fill",
            endpoint="fal-ai/flux-pro/v1/fill",
            kind="image_edit",
            capabilities=Capabilities(
                supports_mask=True,
                verified_at=VERIFIED_AT,
                notes=(
                    "Dedicated FLUX.1 [pro] Fill inpaint endpoint — distinct "
                    "from fal-ai/flux-pro/kontext, which has no mask input."
                ),
            ),
            price_note=_UNVERIFIED_PRICE,
        ),
    ),
    "gpt-image-2-edit": RegistryEntry(
        info=ProviderInfo(
            id="gpt-image-2-edit",
            endpoint="fal-ai/gpt-image-2/edit",
            kind="image_edit",
            capabilities=Capabilities(
                supports_mask=True,
                verified_at=VERIFIED_AT,
                notes=(
                    "Mask param name is mask_url (gpt-image-1.5/edit uses "
                    "mask_image_url instead — schema drift between GPT-Image "
                    "versions). Takes image_urls (array), not a single "
                    "image_url."
                ),
            ),
            price_note=_UNVERIFIED_PRICE,
        ),
    ),
    # --- video (prompt-based; see module docstring) ----------------------
    "kling-26-pro": RegistryEntry(
        info=ProviderInfo(
            id="kling-26-pro",
            endpoint="fal-ai/kling-video/v2.6/pro/image-to-video",
            kind="video",
            capabilities=Capabilities(
                supports_camera_prompt=True,
                verified_at=VERIFIED_AT,
                notes=(
                    "Prompt-based per-element motion only — no dynamic_masks "
                    "or camera_control field exists on this endpoint. See "
                    "docs/plans/2026-08-14-phase1-gate.md."
                ),
            ),
            price_note=(
                "~$0.07/s without audio, ~$0.14/s with audio "
                "(unverified/secondary source, see docs/capabilities/kling-versions.md)"
            ),
        ),
    ),
    "seedance-25": RegistryEntry(
        info=ProviderInfo(
            id="seedance-25",
            endpoint="bytedance/seedance-2.5/image-to-video",
            kind="video",
            capabilities=Capabilities(
                supports_camera_prompt=True,
                verified_at=VERIFIED_AT,
                notes=(
                    "Prompt-based only, no mask/camera fields. Endpoint slug "
                    "is WITHOUT the fal-ai/ prefix."
                ),
            ),
            price_note=_UNVERIFIED_PRICE,
        ),
    ),
    "kling-15-pro": RegistryEntry(
        info=ProviderInfo(
            id="kling-15-pro",
            endpoint="fal-ai/kling-video/v1.5/pro/image-to-video",
            kind="video",
            capabilities=Capabilities(
                supports_dynamic_masks=True,
                supports_camera_prompt=True,
                verified_at=VERIFIED_AT,
                notes=(
                    "LEGACY: pole validní, efekt slabý — nepoužívat pro sc-2, "
                    "viz docs/plans/2026-08-14-phase1-gate.md."
                ),
            ),
            price_note=_UNVERIFIED_PRICE,
        ),
    ),
    # --- segment ----------------------------------------------------------
    "sam-3": RegistryEntry(
        info=ProviderInfo(
            id="sam-3",
            endpoint="fal-ai/sam-3/image",
            kind="segment",
            capabilities=Capabilities(
                verified_at=VERIFIED_AT,
                notes=(
                    "Segmentation via text/point/box prompts; returns masks "
                    "(+ scores, boxes)."
                ),
            ),
            price_note=_UNVERIFIED_PRICE,
        ),
    ),
}


def get_provider(id: str) -> RegistryEntry:
    """Look up a registered provider by its short id.

    Raises:
        KeyError: if id is not registered.
    """
    try:
        return REGISTRY[id]
    except KeyError:
        raise KeyError(f"Unknown provider id {id!r}. Known ids: {sorted(REGISTRY)}") from None


def list_providers(kind: str | None = None) -> list[RegistryEntry]:
    """List registered providers, optionally filtered by kind.

    Args:
        kind: "image_edit" | "video" | "segment" | None (no filter).
    """
    entries = list(REGISTRY.values())
    if kind is not None:
        entries = [e for e in entries if e.info.kind == kind]
    return entries
