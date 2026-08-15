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
from grafik.providers.flux_fill import FluxFillProvider
from grafik.providers.nbpro import ENDPOINT as NBPRO_ENDPOINT
from grafik.providers.nbpro import NanoBananaProProvider
from grafik.providers.qwen_inpaint import QwenInpaintProvider

VERIFIED_AT = "2026-08-14"
# M4 sweep: flux-fill raw OpenAPI + ceny z fal model pages / ai.google.dev.
VERIFIED_M4 = "2026-08-15"

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
            price_note='"$0.03 per megapixel" (fal model page, fetch 2026-08-15 — sekundární zdroj)',
            est_cost_usd_per_mp=0.03,
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
                verified_at=VERIFIED_M4,
                notes=(
                    "Dedicated FLUX.1 [pro] Fill inpaint endpoint — distinct "
                    "from fal-ai/flux-pro/kontext, which has no mask input. "
                    "Raw OpenAPI (2026-08-15): required prompt + image_url + "
                    "mask_url; mask must match input dimensions; output_format "
                    'default jpeg (impl sends png); safety_tolerance default "2"; '
                    "no image_size field — output follows input, resize-back "
                    "guard in impl."
                ),
            ),
            price_note='"$0.05 per megapixel" (fal model page, fetch 2026-08-15 — sekundární zdroj)',
            est_cost_usd_per_mp=0.05,
        ),
        impl=FluxFillProvider,
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
            image_field="start_image_url",
            payload_defaults={"generate_audio": False},
            duration_choices=["5", "10"],
            est_cost_usd_per_second=0.07,
        ),
    ),
    "wan-26": RegistryEntry(
        info=ProviderInfo(
            id="wan-26",
            endpoint="wan/v2.6/image-to-video",
            kind="video",
            capabilities=Capabilities(
                supports_camera_prompt=True,
                verified_at=VERIFIED_AT,
                notes=(
                    "Prompt-based only, no mask/camera fields. Endpoint slug "
                    "is WITHOUT the fal-ai/ prefix (unlike most other fal "
                    "entries here) — see docs/capabilities/model-landscape-2026-08.md."
                ),
            ),
            price_note=(
                "720p $0.10/s, 1080p $0.15/s (fal.ai model page, fetch "
                "2026-08-14 — secondary source, not in the OpenAPI schema)"
            ),
            image_field="image_url",
            payload_defaults={"resolution": "720p", "enable_prompt_expansion": False},
            duration_choices=["5", "10", "15"],
            est_cost_usd_per_second=0.10,
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
            payload_defaults={"generate_audio": False, "resolution": "720p"},
            duration_choices=["auto", "4", "5", "6", "8", "10"],
            est_cost_usd_per_second=None,
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
            price_note='"$0.005 per request" (fal model page, fetch 2026-08-15 — sekundární zdroj)',
            est_cost_usd_per_call=0.005,
        ),
    ),
    # --- decompose (I2L) — capability + cost metadata for FalClient ---------
    "qwen-i2l": RegistryEntry(
        info=ProviderInfo(
            id="qwen-i2l",
            endpoint="fal-ai/qwen-image-layered",
            kind="decompose",
            capabilities=Capabilities(
                verified_at=VERIFIED_M4,
                notes=(
                    "Image→RGBA layers (I2L). Vrstvy chodí v nativním rozlišení "
                    "~0.4 MP — layout se škáluje na canvas ve FalClient.decompose "
                    "(fix 2026-08-15). Entry existuje kvůli capability mapě a "
                    "cost ledgeru; volá se přes FalClient, ne přes impl třídu."
                ),
            ),
            price_note='"$0.05 per image" (fal model page, fetch 2026-08-15 — sekundární zdroj)',
            est_cost_usd_per_call=0.05,
        ),
    ),
    # --- image_gen --------------------------------------------------------
    "nb-pro": RegistryEntry(
        info=ProviderInfo(
            id="nb-pro",
            endpoint=NBPRO_ENDPOINT,  # google/nano-banana-pro-preview — Gemini API, ne fal
            kind="image_gen",
            capabilities=Capabilities(
                verified_at=VERIFIED_M4,
                notes=(
                    "Nano Banana Pro (gemini-3-pro-image) přes Google Gemini API — "
                    "generace VSTUPNÍHO obrázku (generate→decompose). NEBERE pixel "
                    "masku (jen globální/sémantické edity) a vkládá SynthID "
                    "watermark → role: vstup, ne per-prvek edit. Klíč: "
                    "GEMINI_API_KEY/GOOGLE_API_KEY/GOOGLE_GEMINI_API_KEY, "
                    "read-only fallback na NG-ROBOT .env."
                ),
            ),
            price_note='"$0.134 per 1K/2K image", "$0.24 per 4K image" (ai.google.dev/gemini-api/docs/pricing, fetch 2026-08-15)',
            est_cost_usd_per_call=0.134,
        ),
        impl=NanoBananaProProvider,
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
