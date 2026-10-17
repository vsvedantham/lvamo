"""SSRF guard (BETA_PLAN §11/§13). DNS and HTTP are faked."""
import httpx
import pytest

from app.prosho.services import safe_fetch

PUBLIC_IP = "93.184.216.34"


@pytest.fixture
def dns(monkeypatch):
    table = {"public.example": [PUBLIC_IP], "internal.example": ["10.1.2.3"],
             "mixed.example": [PUBLIC_IP, "192.168.0.5"], "mapped.example": ["::ffff:127.0.0.1"]}

    async def resolve(host, port):
        if host in table:
            return table[host]
        try:
            import ipaddress
            return [str(ipaddress.ip_address(host))]
        except ValueError:
            import socket
            raise socket.gaierror("no such host")

    monkeypatch.setattr(safe_fetch, "resolve", resolve)
    return table


def transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://10.0.0.1/", "http://192.168.1.1/", "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/", "http://0.0.0.0/", "http://internal.example/", "http://mixed.example/", "http://mapped.example/",
])
async def test_private_targets_are_blocked(dns, url):
    called = []
    r = await safe_fetch.check_url(url, transport=transport(lambda req: called.append(req) or httpx.Response(200)))
    assert r.blocked and not r.ok and "private or reserved" in r.error
    assert called == []  # never connected


@pytest.mark.parametrize("url,msg", [
    ("file:///etc/passwd", "only http and https"), ("ftp://public.example/x", "only http and https"),
    ("gopher://public.example/", "only http and https"), ("http://user:pw@public.example/", "username or password"),
])
async def test_bad_schemes_and_credentials(dns, url, msg):
    r = await safe_fetch.check_url(url, transport=transport(lambda req: httpx.Response(200)))
    assert r.blocked and msg in r.error


async def test_connection_is_pinned_to_the_checked_ip(dns):
    seen = {}

    def handler(req):
        seen.update(host=req.url.host, header=req.headers["host"], sni=req.extensions.get("sni_hostname"))
        return httpx.Response(200, content=b"ok")

    r = await safe_fetch.check_url("https://public.example/data.csv", transport=transport(handler))
    assert r.ok and r.status_code == 200
    assert seen == {"host": PUBLIC_IP, "header": "public.example", "sni": "public.example"}


async def test_redirect_to_private_address_is_blocked(dns):
    def handler(req):
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
    r = await safe_fetch.check_url("http://public.example/", transport=transport(handler))
    assert r.blocked and not r.ok and r.final_url.startswith("http://169.254.169.254")


async def test_redirects_followed_then_capped(dns):
    hops = iter([httpx.Response(301, headers={"location": "/a"}), httpx.Response(302, headers={"location": "/b"}),
                 httpx.Response(200)])
    r = await safe_fetch.check_url("http://public.example/", transport=transport(lambda req: next(hops)))
    assert r.ok and r.final_url == "http://public.example/b"

    loop = await safe_fetch.check_url("http://public.example/", transport=transport(
        lambda req: httpx.Response(302, headers={"location": "/again"})))
    assert not loop.ok and "redirects" in loop.error


async def test_http_errors_and_dns_failure_are_not_ok(dns):
    r = await safe_fetch.check_url("http://public.example/", transport=transport(lambda req: httpx.Response(503)))
    assert not r.ok and r.status_code == 503 and r.error == "HTTP 503" and not r.blocked
    r = await safe_fetch.check_url("http://nowhere.example/", transport=transport(lambda req: httpx.Response(200)))
    assert not r.ok and not r.blocked and "doesn't resolve" in r.error


async def test_timeout(dns):
    def handler(req):
        raise httpx.ReadTimeout("slow", request=req)
    r = await safe_fetch.check_url("http://public.example/", transport=transport(handler))
    assert not r.ok and "no response" in r.error
