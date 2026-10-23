"""Wikimedia Commons search and import (MediaWiki API, no key needed).

Search only bitmaps (`filetype:bitmap`): without it the File: namespace returns
scanned books (PDF/DjVu) first — seen 2026-10-23 for "roman warship model".
"""
from __future__ import annotations

import html
import re

import httpx

from engine.reflib import UA, RefLibError, RefLibrary, fetch

API = "https://commons.wikimedia.org/w/api.php"
META = "LicenseShortName|LicenseUrl|Artist|Credit|ImageDescription"


def _text(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", value))).strip() or None


def _call(params: dict) -> dict:
    try:
        r = httpx.get(API, params={"format": "json", **params}, headers=UA, timeout=30)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise RefLibError(f"Wikimedia Commons neodpovídá: {e}") from e
    return r.json()


def _item(page: dict) -> dict:
    ii = page["imageinfo"][0]
    md = ii.get("extmetadata", {})
    val = lambda k: (md.get(k) or {}).get("value")  # noqa: E731
    return {
        "title": page["title"].removeprefix("File:"),
        "file": page["title"],
        "thumb": ii.get("thumburl"),
        "url": ii.get("thumburl") if ii.get("thumbwidth", 0) > 400 else ii.get("url"),
        "page_url": ii.get("descriptionurl"),
        "author": _text(val("Artist")) or _text(val("Credit")),
        "license": _text(val("LicenseShortName")),
        "license_url": val("LicenseUrl"),
        "description": (_text(val("ImageDescription")) or "")[:300],
        "width": ii.get("width"), "height": ii.get("height"),
    }


def search(query: str, limit: int = 24) -> list[dict]:
    data = _call({
        "action": "query", "generator": "search", "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6,
        "gsrlimit": limit, "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": 320,
        "iiextmetadatafilter": META,
    })
    pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    return [_item(p) for p in pages if p.get("imageinfo")]


def import_file(lib: RefLibrary, file_title: str) -> dict:
    """Download a Commons file (scaled to at most 2048 px wide) into the library with author and licence."""
    title = file_title if file_title.startswith("File:") else f"File:{file_title}"
    data = _call({"action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url|extmetadata|size",
                  "iiurlwidth": 2048, "iiextmetadatafilter": META})
    pages = list((data.get("query") or {}).get("pages", {}).values())
    if not pages or not pages[0].get("imageinfo"):
        raise RefLibError(f"soubor {title} na Commons neexistuje")
    item = _item(pages[0])
    ii = pages[0]["imageinfo"][0]
    image_url = ii.get("thumburl") or ii["url"]
    return lib.add(fetch(image_url), origin="commons", title=item["title"], source_url=image_url,
                   page_url=item["page_url"], author=item["author"], license=item["license"],
                   license_url=item["license_url"])
