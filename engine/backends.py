"""Image backends. flux-local is the default and costs 0 USD; every other
backend is paid and runs only when the caller names it explicitly and confirms
the estimate (operator decision 2026-10-22). No backend ever falls back to
another one."""
from __future__ import annotations

import base64
import random
from dataclasses import dataclass

import httpx

from engine.config import Settings
from engine.keys import get_key
from engine.models import ImageRequest
from engine.sdserver import SdServer


class BackendError(RuntimeError):
    pass


@dataclass
class Generated:
    images: list[bytes]
    seeds: list[int | None]
    model: str
    params: dict


class FluxLocal:
    name = "flux-local"
    model = "flux-3-image-klein-q4 (sd.cpp a77d362)"
    usd_per_image = 0.0

    def __init__(self, settings: Settings, server: SdServer):
        self.s = settings
        self.server = server

    def validate(self, req: ImageRequest) -> None:
        if req.width * req.height > self.s.max_pixels:
            raise BackendError(
                f"{req.size} je nad strop lokálního FLUX na 8 GB (nejvýš {self.s.max_pixels} px, např. 1920x1088)."
            )

    def payload(self, req: ImageRequest, prompt: str, ref_pngs: list[bytes], seed: int) -> dict:
        p = {
            "prompt": prompt, "width": req.width, "height": req.height, "seed": seed,
            "sample_params": {"sample_steps": req.steps or self.s.steps},
        }
        if ref_pngs:
            p["ref_images"] = [base64.b64encode(b).decode() for b in ref_pngs]
        if req.width * req.height > self.s.vae_tiling_above_pixels:
            p["vae_tiling_params"] = {"enabled": True}
        return p

    def run(self, req: ImageRequest, prompt: str, ref_pngs: list[bytes]) -> Generated:
        self.validate(req)
        base_seed = req.seed if req.seed is not None else random.randint(0, 2**31 - 1)
        images, seeds = [], []
        for i in range(req.n):
            seed = base_seed + i
            images.extend(self.server.generate(self.payload(req, prompt, ref_pngs, seed))[:1])
            seeds.append(seed)
        return Generated(images, seeds, self.model,
                         {"steps": req.steps or self.s.steps, "cfg_scale": self.s.cfg_scale,
                          "sampler": self.s.sampler, "size": req.size})


# Gemini nano-banana-pro-preview, price per image 1K–2K from ai.google.dev (fetched 2026-08-15,
# old GRAFIK registry). The REST call mirrors grafik/providers/nbpro.py.
NB_MODEL = "nano-banana-pro-preview"
NB_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{NB_MODEL}:generateContent"
NB_RATIOS = {"1:1": 1.0, "3:4": 0.75, "4:3": 4 / 3, "16:9": 16 / 9, "9:16": 9 / 16}
NB_MAX_REFS = 3


class NanoBananaPro:
    name = "nb-pro"
    model = f"google/{NB_MODEL}"
    usd_per_image = 0.134

    def validate(self, req: ImageRequest) -> None:
        if sum(r.role != "style" for r in req.refs) > NB_MAX_REFS:
            raise BackendError(f"nb-pro: nejvýš {NB_MAX_REFS} obrazové předlohy")

    def run(self, req: ImageRequest, prompt: str, ref_pngs: list[bytes]) -> Generated:
        self.validate(req)
        key = get_key("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GEMINI_API_KEY")
        if not key:
            raise BackendError("nb-pro: chybí Gemini klíč (GEMINI_API_KEY / GOOGLE_GEMINI_API_KEY)")
        ratio = min(NB_RATIOS, key=lambda r: abs(NB_RATIOS[r] - req.width / req.height))
        image_size = "1K" if max(req.width, req.height) <= 1024 else "2K"
        parts = [{"text": prompt}] + [
            {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(b).decode()}} for b in ref_pngs
        ]
        images = []
        for _ in range(req.n):
            images.append(self._call(key, parts, ratio, image_size))
        return Generated(images, [None] * req.n, self.model, {"aspect_ratio": ratio, "image_size": image_size})

    def _call(self, key: str, parts: list[dict], ratio: str, image_size: str) -> bytes:
        try:
            r = httpx.post(
                NB_URL, headers={"x-goog-api-key": key},
                json={"contents": [{"parts": parts}],
                      "generationConfig": {"responseModalities": ["TEXT", "IMAGE"],
                                           "imageConfig": {"aspectRatio": ratio, "imageSize": image_size}}},
                timeout=300,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise BackendError(f"nb-pro: volání selhalo: {e}") from e
        body = r.json()
        for cand in body.get("candidates") or []:
            for part in (cand.get("content") or {}).get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    return base64.b64decode(inline["data"])
        raise BackendError(f"nb-pro: odpověď bez obrázku: {str(body)[:300]}")


# Image-only style refs are turned into words by Claude Haiku (paid, opt-in like
# any paid step). Estimate: one image (~1.6k input tokens) + ~250 output tokens.
STYLE_MODEL = "claude-haiku-5-5"
STYLE_DESCRIBE_USD = 0.01
STYLE_INSTRUCTION = (
    "Describe only the visual STYLE of this image so an image generator can reproduce it on a different "
    "subject: medium, technique, colour palette, lighting, line quality, texture, rendering, composition "
    "habits. Do not describe the subject or content. One English paragraph, at most 80 words."
)


def describe_style(png: bytes) -> str:
    key = get_key("ANTHROPIC_API_KEY")
    if not key:
        raise BackendError("popis stylu: chybí ANTHROPIC_API_KEY")
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            json={"model": STYLE_MODEL, "max_tokens": 300, "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": base64.b64encode(png).decode()}},
                {"type": "text", "text": STYLE_INSTRUCTION}]}]},
            timeout=120,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise BackendError(f"popis stylu selhal: {e}") from e
    return "".join(b.get("text", "") for b in r.json().get("content", [])).strip()


def make_backends(settings: Settings, server: SdServer) -> dict:
    return {"flux-local": FluxLocal(settings, server), "nb-pro": NanoBananaPro()}


def estimate_usd(req: ImageRequest, backend) -> dict:
    """Cost estimate shown before anything paid runs."""
    items = []
    if backend.usd_per_image:
        items.append({"what": f"{backend.name} × {req.n}", "usd": round(backend.usd_per_image * req.n, 4)})
    describe = sum(1 for r in req.refs if r.role == "style" and not r.text)
    if describe:
        items.append({"what": f"popis stylu slovy (Claude Haiku) × {describe}",
                      "usd": round(STYLE_DESCRIBE_USD * describe, 4)})
    return {"total_usd": round(sum(i["usd"] for i in items), 4), "items": items}
