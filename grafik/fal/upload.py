"""Upload local files to fal CDN and download URLs."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import httpx
import fal_client
from PIL import Image


def upload_file(file_path: Path) -> str:
    """Upload a local file to fal.ai CDN and return the URL."""
    url = fal_client.upload_file(str(file_path))
    return url


def upload_image(img: Image.Image) -> str:
    """Upload a PIL Image to fal.ai CDN and return the URL."""
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    url = fal_client.upload(buf, content_type="image/png")
    return url


def download_url(url: str) -> Image.Image:
    """Download an image URL and return as PIL Image."""
    resp = httpx.get(url, timeout=60.0, follow_redirects=True)
    resp.raise_for_status()
    buf = BytesIO(resp.content)
    img = Image.open(buf)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img
