"""Tests for M5 reference-image support in NanoBananaProProvider.generate().

Fully offline -- httpx.post is monkeypatched, same seam
test_nbpro_parses_inline_data_and_errors_readably (test_api_m4.py) uses.
No network/paid calls.
"""

from __future__ import annotations

import base64
from io import BytesIO

import pytest
from PIL import Image

from grafik.providers import nbpro


def _tiny_png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (4, 4), (1, 2, 3)).save(buf, "PNG")
    return buf.getvalue()


def _gemini_response_body(png_bytes: bytes) -> dict:
    """A minimal well-formed Gemini response carrying one inlineData image."""
    data_b64 = base64.b64encode(png_bytes).decode("ascii")
    return {"candidates": [{"content": {"parts": [{"inlineData": {"data": data_b64}}]}}]}


class _FakeResp:
    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._body


def _capture_post(captured: dict):
    """httpx.post fake: records the call, answers with a valid tiny PNG so
    generate() completes its Image.open(...) step too."""

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _FakeResp(_gemini_response_body(_tiny_png_bytes()))

    return fake_post


@pytest.fixture(autouse=True)
def _fake_key(monkeypatch):
    monkeypatch.setattr(nbpro, "resolve_api_key", lambda: "test-key")


def test_generate_with_two_references_sends_text_then_two_inline_parts(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(nbpro.httpx, "post", _capture_post(captured))

    provider = nbpro.NanoBananaProProvider()
    ref_a = Image.new("RGB", (10, 10), (255, 0, 0))
    ref_b = Image.new("RGB", (20, 20), (0, 255, 0))

    provider.generate("kočka na plotě", reference_images=[ref_a, ref_b])

    parts = captured["json"]["contents"][0]["parts"]
    assert len(parts) == 3
    assert parts[0] == {"text": "kočka na plotě"}
    sizes = []
    for part in parts[1:]:
        inline = part["inlineData"]
        assert inline["mimeType"] == "image/png"
        decoded = base64.b64decode(inline["data"])
        img = Image.open(BytesIO(decoded))
        assert img.format == "PNG"
        sizes.append(img.size)
    # both refs are well under the 1536 cap -> left at original size
    assert sizes == [(10, 10), (20, 20)]


def test_reference_image_downscaled_to_1536_long_edge(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(nbpro.httpx, "post", _capture_post(captured))

    provider = nbpro.NanoBananaProProvider()
    big_ref = Image.new("RGB", (4000, 2000), (10, 20, 30))

    provider.generate("prompt", reference_images=[big_ref])

    parts = captured["json"]["contents"][0]["parts"]
    inline = parts[1]["inlineData"]
    decoded = base64.b64decode(inline["data"])
    img = Image.open(BytesIO(decoded))
    assert img.size == (1536, 768)  # long edge clamped, aspect ratio kept


def test_generate_with_four_references_raises_value_error(monkeypatch):
    def fail_post(*a, **kw):
        raise AssertionError("httpx.post must not be called when reference validation fails")

    monkeypatch.setattr(nbpro.httpx, "post", fail_post)

    provider = nbpro.NanoBananaProProvider()
    refs = [Image.new("RGB", (8, 8)) for _ in range(4)]
    with pytest.raises(ValueError, match="Příliš mnoho"):
        provider.generate("prompt", reference_images=refs)


def test_generate_without_references_payload_unchanged(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(nbpro.httpx, "post", _capture_post(captured))

    provider = nbpro.NanoBananaProProvider()
    provider.generate("no refs here")

    parts = captured["json"]["contents"][0]["parts"]
    assert parts == [{"text": "no refs here"}]
