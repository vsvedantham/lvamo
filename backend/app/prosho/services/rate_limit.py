"""Small in-memory rate limits for the endpoints anyone can call.

Fixed one-minute (or one-hour) windows kept per worker process: prod runs
two uvicorn workers, so the real ceiling is up to twice each number. That's
fine for stopping a runaway CI loop or a scraper; it isn't billing. Nothing
here is written to disk, and keys are dropped when their window ends.
"""
import hashlib
import time
from collections.abc import Callable

from fastapi import HTTPException, Request, status

_windows: dict[str, tuple[int, int]] = {}  # key -> (window start, count)
_last_sweep = 0.0


def client_ip(request: Request) -> str:
    """nginx overwrites X-Real-IP with the connecting address (api.* is not
    behind a CDN), so it can be trusted; without nginx (dev, tests) fall back
    to the socket."""
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


def _sweep(now: float) -> None:
    global _last_sweep
    if now - _last_sweep < 60:
        return
    _last_sweep = now
    for key in [k for k, (start, _) in _windows.items() if start + 3600 < now]:
        del _windows[key]


def hit(key: str, limit: int, per_seconds: int = 60) -> bool:
    """Counts one request; False once `key` is over `limit` in this window."""
    now = time.time()
    _sweep(now)
    window = int(now // per_seconds) * per_seconds
    start, count = _windows.get(key, (window, 0))
    if start != window:
        start, count = window, 0
    _windows[key] = (start, count + 1)
    return count < limit


def too_many(retry_after: int = 60) -> HTTPException:
    return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                         detail="Too many requests — slow down and try again in a minute",
                         headers={"Retry-After": str(retry_after)})


def per_ip(name: str, limit: int) -> Callable[[Request], None]:
    """A route dependency: `limit` requests a minute from one address."""
    def check(request: Request) -> None:
        if not hit(f"{name}:{client_ip(request)}", limit):
            raise too_many()
    return check


def token_key(token: str) -> str:
    # Never keep the bearer token itself in memory longer than the request.
    return hashlib.sha256(token.encode()).hexdigest()[:24]


def reset() -> None:
    """For tests."""
    _windows.clear()
