"""A Personio posting's description from its job page, for companies whose
XML feed leaves `jobDescriptions` empty: the page carries the posting as
schema.org JobPosting data."""
from __future__ import annotations

import html
import json
import re

import httpx

from app.applaut.discovery.base import JobListing

_LD = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)


def description_from_page(page: str) -> str | None:
    for m in _LD.finditer(page):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "JobPosting" and item.get("description"):
                return html.unescape(item["description"]).strip()
    return None


async def describe(client: httpx.AsyncClient, listing: JobListing) -> str | None:
    try:
        resp = await client.get(listing.application_url, params={"language": "en"}, follow_redirects=True)
    except httpx.HTTPError:
        return None
    return description_from_page(resp.text) if resp.status_code == 200 else None
