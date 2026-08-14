"""grafik.providers — fal.ai provider registry (capability map) for GRAFIK.

See docs/capabilities/kling-versions.md, docs/capabilities/model-landscape-2026-08.md,
and docs/plans/2026-08-14-phase1-gate.md for the verified capability data
this package encodes.
"""

from grafik.providers.base import (
    Capabilities,
    ImageEditProvider,
    ProviderInfo,
    SegmentProvider,
    VideoProvider,
)
from grafik.providers.qwen_inpaint import QwenInpaintProvider, prepare_paste_mask
from grafik.providers.registry import REGISTRY, RegistryEntry, get_provider, list_providers

__all__ = [
    "Capabilities",
    "ProviderInfo",
    "ImageEditProvider",
    "VideoProvider",
    "SegmentProvider",
    "QwenInpaintProvider",
    "prepare_paste_mask",
    "REGISTRY",
    "RegistryEntry",
    "get_provider",
    "list_providers",
]
