"""Polite GETs for the job-board APIs: a retry with a pause when the API says
"too many requests" (HTTP 429) or has a passing error."""
from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)
RETRY_WAITS = (5, 15, 30)  # seconds


async def get_json(client: httpx.AsyncClient, url: str, **kwargs) -> dict | list | None:
    """The JSON body, or None when the API keeps failing (logged)."""
    for wait in (*RETRY_WAITS, None):
        try:
            resp = await client.get(url, **kwargs)
        except httpx.HTTPError as exc:
            status, detail = None, str(exc)
        else:
            if resp.status_code == 200:
                return resp.json()
            status, detail = resp.status_code, resp.text[:200]
            if status not in (429, 500, 502, 503, 504):
                logger.warning("Job API %s answered %s: %s", url, status, detail)
                return None
        if wait is None:
            logger.warning("Job API %s failed after retries (%s): %s", url, status, detail)
            return None
        await asyncio.sleep(wait)
    return None
