"""NanoBananaProProvider — text→image generation via the Google Gemini API.

Nano Banana Pro (gemini-3-pro-image) generates a project's INPUT image
(generate → decompose). It accepts NO pixel mask — only global/semantic
instructions — and embeds a SynthID watermark, so its role is input
generation, never per-element edit (M4 contract).

Call shape mirrors the empirically working pattern in NG-ROBOT
image_generator.py (read-only vzor, 2026-08-15): stable model alias
"nano-banana-pro-preview" (versioned names drift, the alias doesn't),
response_modalities TEXT+IMAGE, ImageConfig(aspect_ratio, image_size). This
module speaks the REST API directly via httpx (camelCase field names) so
GRAFIK needs no google-genai dependency.

API key resolution (in order): GEMINI_API_KEY, GOOGLE_API_KEY,
GOOGLE_GEMINI_API_KEY from the environment (GRAFIK's .env/key.env are
already loaded by the app), then a read-only fallback to NG-ROBOT's .env —
values are read with dotenv_values, never written anywhere.

Reference images (M5): `generate()` accepts up to MAX_REFERENCE_IMAGES PIL
images for style/subject/character consistency across generations. Each
becomes one extra `inlineData` part (camelCase, same field names as the
response parsing below) appended after the text part in
`contents[0].parts`. Shape per ai.google.dev/gemini-api/docs/image-generation
(fetch 2026-08-15) — gemini-3-pro-image documents up to 6 object / 5
character / 3 style references; GRAFIK caps at 3 as a single UI contract.
Payload shape confirmed empirically by a paid E2E call, done by the
orchestrator, not this module.
"""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Any
import os

import httpx
from dotenv import dotenv_values
from PIL import Image

from grafik.providers.base import ImageGenProvider

MODEL = "nano-banana-pro-preview"
# Pseudo-endpoint id for the registry + cost ledger (not a fal slug).
ENDPOINT = f"google/{MODEL}"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

KEY_ENV_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GEMINI_API_KEY")
NG_ROBOT_ENV_PATH = Path("C:/Users/stock/Documents/000_NGM/NG-ROBOT/.env")

# ImageConfig-supported aspect ratios (google.genai docs; NG-ROBOT vzor).
ASPECT_RATIOS = ("1:1", "3:4", "4:3", "16:9", "9:16")
IMAGE_SIZES = ("1K", "2K", "4K")

# M5: reference images for style/subject/character consistency. GRAFIK's own
# UI contract (below the documented per-type gemini-3-pro-image limits).
MAX_REFERENCE_IMAGES = 3
# Server-side downscale guard -- the client already downscales before
# upload, but the provider does not trust it.
MAX_REFERENCE_EDGE_PX = 1536


class GeminiKeyMissing(RuntimeError):
    """No usable Gemini API key anywhere — the route turns this into a 503."""


def resolve_api_key() -> str | None:
    """First key found in env vars, else in NG-ROBOT's .env (read-only)."""
    for name in KEY_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    if NG_ROBOT_ENV_PATH.exists():
        values = dotenv_values(NG_ROBOT_ENV_PATH)
        for name in KEY_ENV_VARS:
            value = (values.get(name) or "").strip()
            if value:
                return value
    return None


def _encode_reference_image(image: Image.Image) -> dict[str, Any]:
    """Downscale one reference image to a long edge of at most
    MAX_REFERENCE_EDGE_PX (Image.LANCZOS; smaller images are left alone),
    then PNG+base64-encode it into a Gemini `inlineData` part."""
    long_edge = max(image.size)
    if long_edge > MAX_REFERENCE_EDGE_PX:
        scale = MAX_REFERENCE_EDGE_PX / long_edge
        new_size = (round(image.width * scale), round(image.height * scale))
        image = image.resize(new_size, Image.LANCZOS)
    buf = BytesIO()
    image.save(buf, format="PNG")
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    return {"inlineData": {"mimeType": "image/png", "data": data}}


class NanoBananaProProvider(ImageGenProvider):
    """Concrete ImageGenProvider for Nano Banana Pro over the Gemini REST API."""

    ENDPOINT = ENDPOINT

    def generate(self, prompt: str, **kw: Any) -> Image.Image:
        """Generate one image from `prompt`.

        Args:
            aspect_ratio: one of ASPECT_RATIOS, default "1:1".
            image_size: one of IMAGE_SIZES, default "2K" ($0.134 covers 1K/2K).
            reference_images: optional list of up to MAX_REFERENCE_IMAGES
                PIL images, for style/subject/character consistency across
                generations. Each is downscaled server-side and sent as an
                extra `inlineData` part after the text prompt (M5).

        Raises:
            ValueError: aspect_ratio/image_size not recognized, or more than
                MAX_REFERENCE_IMAGES reference images given.
            GeminiKeyMissing: no API key found anywhere.
            RuntimeError: the API answered without an image (moderation etc.)
                — the reason is kept readable in the message.
        """
        aspect_ratio: str = kw.get("aspect_ratio", "1:1")
        image_size: str = kw.get("image_size", "2K")
        reference_images: list[Image.Image] | None = kw.get("reference_images")
        if aspect_ratio not in ASPECT_RATIOS:
            raise ValueError(f"aspect_ratio {aspect_ratio!r} not in {ASPECT_RATIOS}")
        if image_size not in IMAGE_SIZES:
            raise ValueError(f"image_size {image_size!r} not in {IMAGE_SIZES}")
        if reference_images and len(reference_images) > MAX_REFERENCE_IMAGES:
            raise ValueError(
                f"Příliš mnoho referenčních obrázků ({len(reference_images)}), "
                f"nejvýš {MAX_REFERENCE_IMAGES}."
            )

        key = resolve_api_key()
        if not key:
            raise GeminiKeyMissing(
                "Chybí GEMINI_API_KEY / GOOGLE_API_KEY / GOOGLE_GEMINI_API_KEY "
                "(v env, .env, key.env ani v NG-ROBOT .env). Klíč získáte na "
                "https://aistudio.google.com/apikey."
            )

        if reference_images:
            reference_parts = [_encode_reference_image(img) for img in reference_images]
            data = self._run_remote(
                key, prompt, aspect_ratio, image_size, reference_parts=reference_parts
            )
        else:
            data = self._run_remote(key, prompt, aspect_ratio, image_size)
        img = Image.open(BytesIO(data))
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        return img

    def _run_remote(
        self,
        key: str,
        prompt: str,
        aspect_ratio: str,
        image_size: str,
        reference_parts: list[dict] | None = None,
    ) -> bytes:
        """All network I/O for one generation call — isolated for
        monkeypatching, mirrors QwenInpaintProvider._run_remote.

        `reference_parts` (M5, default None): pre-encoded `inlineData` parts
        for reference images, appended after the text part -- kept as a
        trailing defaulted parameter so pre-M5 monkeypatch fakes with the
        original 4-positional-argument shape keep working unchanged."""
        parts: list[dict] = [{"text": prompt}]
        if reference_parts:
            parts.extend(reference_parts)
        resp = httpx.post(
            API_URL,
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "responseModalities": ["TEXT", "IMAGE"],
                    "imageConfig": {"aspectRatio": aspect_ratio, "imageSize": image_size},
                },
            },
            timeout=300.0,
        )
        resp.raise_for_status()
        body = resp.json()

        candidates = body.get("candidates") or []
        if not candidates:
            raise RuntimeError(f"Gemini nevrátil žádné kandidáty: {body.get('promptFeedback', body)}")
        content = candidates[0].get("content") or {}
        text_parts: list[str] = []
        for part in content.get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
            if part.get("text"):
                text_parts.append(part["text"])
        finish = candidates[0].get("finishReason", "unknown")
        detail = f" Text odpovědi: {' '.join(text_parts)[:300]}" if text_parts else ""
        raise RuntimeError(f"Gemini nevrátil obrázek (finishReason={finish}).{detail}")
