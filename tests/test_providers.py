"""Tests for grafik.providers — registry integrity, capability truths, and
paste-back math. No network calls: QwenInpaintProvider's one network method
(_run_remote) is monkeypatched in every test that exercises edit().
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from grafik.providers import (
    REGISTRY,
    Capabilities,
    ProviderInfo,
    QwenInpaintProvider,
    get_provider,
    list_providers,
    prepare_paste_mask,
)
from grafik.providers.qwen_inpaint import dilate_mask, paste_back

EXPECTED_IDS = {
    "qwen-inpaint",
    "flux-fill",
    "gpt-image-2-edit",
    "kling-26-pro",
    "wan-26",
    "seedance-25",
    "kling-15-pro",
    "sam-3",
}

EXPECTED_KIND = {
    "qwen-inpaint": "image_edit",
    "flux-fill": "image_edit",
    "gpt-image-2-edit": "image_edit",
    "kling-26-pro": "video",
    "wan-26": "video",
    "seedance-25": "video",
    "kling-15-pro": "video",
    "sam-3": "segment",
}


# --------------------------------------------------------------------------
# Registry integrity
# --------------------------------------------------------------------------


class TestRegistryIntegrity:
    def test_expected_ids_present(self):
        assert set(REGISTRY.keys()) == EXPECTED_IDS

    def test_all_entries_validate(self):
        for entry in REGISTRY.values():
            assert isinstance(entry.info, ProviderInfo)
            assert isinstance(entry.info.capabilities, Capabilities)
            # round-trip through the pydantic validator
            ProviderInfo.model_validate(entry.info.model_dump())

    def test_id_matches_registry_key(self):
        for pid, entry in REGISTRY.items():
            assert entry.info.id == pid

    def test_kinds_correct(self):
        for pid, entry in REGISTRY.items():
            assert entry.info.kind == EXPECTED_KIND[pid]

    def test_kind_is_restricted_to_known_values(self):
        for entry in REGISTRY.values():
            assert entry.info.kind in {"image_edit", "video", "segment"}

    def test_verified_at_set(self):
        for pid, entry in REGISTRY.items():
            assert entry.info.capabilities.verified_at, f"{pid} missing verified_at"
            assert entry.info.capabilities.verified_at == "2026-08-14"

    def test_endpoints_nonempty(self):
        for pid, entry in REGISTRY.items():
            assert entry.info.endpoint, f"{pid} missing endpoint"

    def test_seedance_endpoint_has_no_fal_ai_prefix(self):
        # docs/capabilities/model-landscape-2026-08.md: slug WITHOUT fal-ai/ prefix
        entry = get_provider("seedance-25")
        assert entry.info.endpoint == "bytedance/seedance-2.5/image-to-video"
        assert not entry.info.endpoint.startswith("fal-ai/")

    def test_qwen_inpaint_has_concrete_impl(self):
        entry = get_provider("qwen-inpaint")
        assert entry.impl is QwenInpaintProvider

    def test_other_entries_have_no_impl_yet(self):
        for pid in EXPECTED_IDS - {"qwen-inpaint"}:
            assert get_provider(pid).impl is None


# --------------------------------------------------------------------------
# Capability truths (per docs/plans/2026-08-14-phase1-gate.md)
# --------------------------------------------------------------------------


class TestCapabilityTruths:
    def test_only_kling_15_pro_has_dynamic_masks(self):
        for pid, entry in REGISTRY.items():
            if entry.info.kind != "video":
                continue
            expected = pid == "kling-15-pro"
            assert entry.info.capabilities.supports_dynamic_masks is expected, pid

    def test_all_video_providers_support_camera_prompt(self):
        for pid, entry in REGISTRY.items():
            if entry.info.kind != "video":
                continue
            assert entry.info.capabilities.supports_camera_prompt is True, pid

    def test_no_video_provider_has_camera_params(self):
        # image+camera control combo does not exist on any fal.ai I2V endpoint today
        for pid, entry in REGISTRY.items():
            if entry.info.kind != "video":
                continue
            assert entry.info.capabilities.supports_camera_params is False, pid

    def test_image_edit_providers_support_mask(self):
        for pid in ("qwen-inpaint", "flux-fill", "gpt-image-2-edit"):
            assert get_provider(pid).info.capabilities.supports_mask is True

    def test_sam3_has_no_mask_or_camera_capability(self):
        caps = get_provider("sam-3").info.capabilities
        assert caps.supports_mask is False
        assert caps.supports_dynamic_masks is False
        assert caps.supports_camera_params is False
        assert caps.supports_camera_preset is False
        assert caps.supports_camera_prompt is False

    def test_kling_15_pro_legacy_note_present(self):
        notes = get_provider("kling-15-pro").info.capabilities.notes
        assert "nepoužívat pro sc-2" in notes
        assert "2026-08-14-phase1-gate.md" in notes


# --------------------------------------------------------------------------
# Video payload fields (M3: build_video_payload consumes these per-provider)
# --------------------------------------------------------------------------


class TestVideoPayloadFields:
    def test_kling_26_pro_payload_fields(self):
        info = get_provider("kling-26-pro").info
        assert info.image_field == "start_image_url"
        assert info.payload_defaults == {"generate_audio": False}
        assert info.duration_choices == ["5", "10"]
        assert info.est_cost_usd_per_second == pytest.approx(0.07)

    def test_wan_26_payload_fields(self):
        info = get_provider("wan-26").info
        assert info.endpoint == "wan/v2.6/image-to-video"
        assert not info.endpoint.startswith("fal-ai/")
        assert info.image_field == "image_url"
        assert info.payload_defaults == {"resolution": "720p", "enable_prompt_expansion": False}
        assert info.duration_choices == ["5", "10", "15"]
        assert info.est_cost_usd_per_second == pytest.approx(0.10)

    def test_seedance_25_payload_fields(self):
        info = get_provider("seedance-25").info
        assert info.image_field == "image_url"  # default -- not overridden
        assert info.payload_defaults == {"generate_audio": False, "resolution": "720p"}
        assert info.duration_choices == ["auto", "4", "5", "6", "8", "10"]
        assert info.est_cost_usd_per_second is None

    def test_kling_15_pro_uses_defaults(self):
        """Legacy entry -- contract says "beze zmeny" (unchanged): every M3
        field just keeps the ProviderInfo model default."""
        info = get_provider("kling-15-pro").info
        assert info.image_field == "image_url"
        assert info.payload_defaults == {}
        assert info.duration_choices == ["5", "10"]
        assert info.est_cost_usd_per_second is None


# --------------------------------------------------------------------------
# get_provider / list_providers
# --------------------------------------------------------------------------


class TestRegistryLookup:
    def test_list_all_matches_registry_size(self):
        assert len(list_providers()) == len(REGISTRY)

    def test_filter_by_kind_video(self):
        video = list_providers(kind="video")
        assert {e.info.id for e in video} == {"kling-26-pro", "wan-26", "seedance-25", "kling-15-pro"}

    def test_filter_by_kind_image_edit(self):
        image_edit = list_providers(kind="image_edit")
        assert {e.info.id for e in image_edit} == {"qwen-inpaint", "flux-fill", "gpt-image-2-edit"}

    def test_filter_by_kind_segment(self):
        segment = list_providers(kind="segment")
        assert {e.info.id for e in segment} == {"sam-3"}

    def test_get_known_provider(self):
        entry = get_provider("qwen-inpaint")
        assert entry.info.endpoint == "fal-ai/qwen-image-edit/inpaint"

    def test_get_unknown_raises_keyerror(self):
        with pytest.raises(KeyError):
            get_provider("does-not-exist")


# --------------------------------------------------------------------------
# Paste-back math (synthetic 64x64 images, no network)
# --------------------------------------------------------------------------


class TestPasteBackMath:
    def _hard_mask(self, size=(64, 64), box=(16, 16, 48, 48)) -> Image.Image:
        arr = np.zeros(size[::-1], dtype=np.uint8)
        x0, y0, x1, y1 = box
        arr[y0:y1, x0:x1] = 255
        return Image.fromarray(arr, mode="L")

    def test_outside_mask_unchanged_where_feather_is_zero(self):
        size = (64, 64)
        input_img = Image.new("RGB", size, (10, 20, 30))
        result_img = Image.new("RGB", size, (200, 150, 100))
        mask = self._hard_mask(size)
        mask_arr = np.array(mask)

        final = paste_back(input_img, result_img, mask)
        final_arr = np.array(final)
        input_arr = np.array(input_img)
        result_arr = np.array(result_img)

        outside = mask_arr == 0
        inside = mask_arr == 255

        assert np.array_equal(final_arr[outside], input_arr[outside])
        assert np.array_equal(final_arr[inside], result_arr[inside])

    def test_paste_back_matches_reference_formula(self):
        size = (8, 8)
        rng = np.random.default_rng(0)
        input_arr = rng.integers(0, 256, size=(8, 8, 3), dtype=np.uint8)
        result_arr = rng.integers(0, 256, size=(8, 8, 3), dtype=np.uint8)
        feather_arr = rng.integers(0, 256, size=(8, 8), dtype=np.uint8)

        input_img = Image.fromarray(input_arr, mode="RGB")
        result_img = Image.fromarray(result_arr, mode="RGB")
        feather_img = Image.fromarray(feather_arr, mode="L")

        final = np.array(paste_back(input_img, result_img, feather_img))

        feather_norm = (feather_arr.astype(np.float64) / 255.0)[..., None]
        expected = np.clip(
            input_arr.astype(np.float64) * (1 - feather_norm)
            + result_arr.astype(np.float64) * feather_norm,
            0,
            255,
        ).astype(np.uint8)

        assert np.array_equal(final, expected)

    def test_dilate_mask_grows_region(self):
        mask = self._hard_mask((64, 64), box=(28, 28, 36, 36))
        dilated = dilate_mask(mask)
        assert (np.array(dilated) > 0).sum() > (np.array(mask) > 0).sum()

    def test_prepare_paste_mask_dilates_and_feathers(self):
        mask = self._hard_mask((64, 64), box=(30, 30, 34, 34))
        mask_arr = np.array(mask)

        feathered = prepare_paste_mask(mask)
        feathered_arr = np.array(feathered)

        # dilation must grow the nonzero region
        assert (feathered_arr > 0).sum() > (mask_arr > 0).sum()
        # feathering must introduce intermediate (non 0/255) values
        assert ((feathered_arr > 0) & (feathered_arr < 255)).any()


# --------------------------------------------------------------------------
# QwenInpaintProvider.edit — offline (network monkeypatched)
# --------------------------------------------------------------------------


class TestQwenInpaintProviderOffline:
    def _mask(self, size=(64, 64), box=(16, 16, 48, 48)) -> Image.Image:
        arr = np.zeros(size[::-1], dtype=np.uint8)
        x0, y0, x1, y1 = box
        arr[y0:y1, x0:x1] = 255
        return Image.fromarray(arr, mode="L")

    def test_edit_returns_paste_backed_image(self, monkeypatch):
        provider = QwenInpaintProvider()
        size = (64, 64)
        image = Image.new("RGB", size, (10, 20, 30))
        mask = self._mask(size)
        fake_result = Image.new("RGB", size, (200, 150, 100))

        calls: dict = {}

        def fake_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
            calls["called"] = True
            calls["prompt"] = prompt
            calls["negative_prompt"] = negative_prompt
            calls["enable_safety_checker"] = enable_safety_checker
            calls["image_size"] = image.size
            return fake_result

        monkeypatch.setattr(QwenInpaintProvider, "_run_remote", fake_run_remote)

        out = provider.edit(image, mask, "add a hat", negative_prompt="blurry")

        assert calls == {
            "called": True,
            "prompt": "add a hat",
            "negative_prompt": "blurry",
            "enable_safety_checker": True,
            "image_size": size,
        }
        assert out.size == size
        assert out.mode == "RGB"

        out_arr = np.array(out)
        input_arr = np.array(image)
        result_arr = np.array(fake_result)

        # far outside even the dilated+feathered mask -> input unchanged
        assert np.array_equal(out_arr[0:4, 0:4], input_arr[0:4, 0:4])
        # deep inside the mask -> the (monkeypatched) remote result
        assert np.array_equal(out_arr[28:36, 28:36], result_arr[28:36, 28:36])

    def test_edit_resizes_mismatched_remote_result(self, monkeypatch):
        provider = QwenInpaintProvider()
        image = Image.new("RGB", (64, 64), (5, 5, 5))
        mask = Image.new("L", (64, 64), 255)

        def fake_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
            return Image.new("RGB", (32, 32), (250, 250, 250))  # wrong size

        monkeypatch.setattr(QwenInpaintProvider, "_run_remote", fake_run_remote)

        out = provider.edit(image, mask, "prompt")
        assert out.size == (64, 64)

    def test_edit_never_touches_network(self, monkeypatch):
        """Guard: if _run_remote is NOT monkeypatched, edit() must not be called
        in this test suite in a way that reaches real network code. This test
        instead asserts the isolation contract: replacing _run_remote alone is
        sufficient to fully stub the provider (no other network hook needed).
        """
        provider = QwenInpaintProvider()
        image = Image.new("RGB", (16, 16), (1, 2, 3))
        mask = Image.new("L", (16, 16), 0)  # empty mask -> no edit region

        def fake_run_remote(self, image, mask, prompt, negative_prompt, enable_safety_checker):
            return image  # identity result

        monkeypatch.setattr(QwenInpaintProvider, "_run_remote", fake_run_remote)

        out = provider.edit(image, mask, "noop")
        assert np.array_equal(np.array(out), np.array(image))
