"""Fetching student-supplied URLs without SSRF (BETA_PLAN §11).

Rules: http/https only; no credentials in the URL; the host must resolve
only to public addresses (no private, loopback, link-local, multicast or
reserved ranges, IPv4-mapped IPv6 included); the connection goes to the
address that was checked (pinned — no second DNS lookup to rebind); at most
3 redirects, each re-checked the same way; 10 s timeout; at most 64 KB read.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlsplit

import httpx

USER_AGENT = "LVAMO-ProSho-SourceCheck/1.0 (+https://www.lvamo.com/prosho)"
DEFAULT_PORTS = {"http": 80, "https": 443}


class BlockedURL(Exception):
    """Refused for safety (scheme, credentials, private address)."""


class UnresolvableHost(Exception):
    """DNS has no answer — the source is down, not dangerous."""


@dataclass
class FetchResult:
    ok: bool
    status_code: Optional[int]
    final_url: str
    elapsed_ms: int
    error: Optional[str] = None
    blocked: bool = False


def ip_allowed(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


async def resolve(host: str, port: int) -> list[str]:
    """Every address the host resolves to. Module-level so tests can fake DNS."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


async def _pin(url: str) -> tuple[str, dict[str, str], dict]:
    parts = urlsplit(url)
    if parts.scheme not in DEFAULT_PORTS:
        raise BlockedURL("only http and https URLs can be checked")
    if parts.username or parts.password:
        raise BlockedURL("URLs with a username or password can't be checked")
    host = parts.hostname
    if not host:
        raise BlockedURL("the URL has no host")
    port = parts.port or DEFAULT_PORTS[parts.scheme]
    try:
        ips = await resolve(host, port)
    except socket.gaierror:
        raise UnresolvableHost(f"{host} doesn't resolve (DNS)")
    if not ips or not all(ip_allowed(ip) for ip in ips):
        raise BlockedURL(f"{host} points to a private or reserved address")
    ip = ips[0]
    netloc = (f"[{ip}]" if ":" in ip else ip) + (f":{parts.port}" if parts.port else "")
    pinned = parts._replace(netloc=netloc).geturl()
    host_header = host + (f":{parts.port}" if parts.port else "")
    extensions = {"sni_hostname": host} if parts.scheme == "https" else {}
    return pinned, {"Host": host_header, "User-Agent": USER_AGENT, "Accept": "*/*"}, extensions


async def check_url(url: str, *, timeout: float = 10.0, max_redirects: int = 3, max_bytes: int = 64 * 1024,
                    transport: Optional[httpx.AsyncBaseTransport] = None) -> FetchResult:
    started = time.monotonic()
    ms = lambda: int((time.monotonic() - started) * 1000)  # noqa: E731
    current = url
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, transport=transport) as client:
            for _ in range(max_redirects + 1):
                pinned, headers, extensions = await _pin(current)
                request = client.build_request("GET", pinned, headers=headers, extensions=extensions)
                resp = await client.send(request, stream=True)
                try:
                    read = 0
                    async for chunk in resp.aiter_bytes():
                        read += len(chunk)
                        if read >= max_bytes:
                            break
                finally:
                    await resp.aclose()
                location = resp.headers.get("location")
                if 300 <= resp.status_code < 400 and location:
                    current = urljoin(current, location)
                    continue
                ok = resp.status_code < 400
                return FetchResult(ok=ok, status_code=resp.status_code, final_url=current, elapsed_ms=ms(),
                                   error=None if ok else f"HTTP {resp.status_code}")
            return FetchResult(ok=False, status_code=None, final_url=current, elapsed_ms=ms(),
                               error=f"more than {max_redirects} redirects")
    except BlockedURL as e:
        return FetchResult(ok=False, status_code=None, final_url=current, elapsed_ms=ms(), error=str(e), blocked=True)
    except UnresolvableHost as e:
        return FetchResult(ok=False, status_code=None, final_url=current, elapsed_ms=ms(), error=str(e))
    except httpx.TimeoutException:
        return FetchResult(ok=False, status_code=None, final_url=current, elapsed_ms=ms(), error=f"no response within {timeout:.0f} s")
    except httpx.HTTPError as e:
        reason = "invalid HTTPS certificate" if "CERTIFICATE" in str(e).upper() else f"couldn't connect ({type(e).__name__})"
        return FetchResult(ok=False, status_code=None, final_url=current, elapsed_ms=ms(), error=reason)
