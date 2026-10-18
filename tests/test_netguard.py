"""SSRF netguard: URL validation (pure, fake resolver) + safe_get (fake transport).
No network access in any test."""
from __future__ import annotations

import contextlib

import pytest

from bee.security import netguard as ng


# ---------------------------------------------------------------- validate
def _fake_resolver(mapping):
    def resolver(host):
        if host in mapping:
            return mapping[host]
        raise OSError(f"no such host: {host}")
    return resolver


@pytest.mark.parametrize("url,why", [
    ("http://127.0.0.1/x", "loopback v4"),
    ("http://127.8.9.10/x", "loopback v4 range"),
    ("http://[::1]/x", "loopback v6"),
    ("http://0.0.0.0/x", "unspecified"),
    ("http://10.0.0.5/x", "rfc1918 10/8"),
    ("http://172.16.0.1/x", "rfc1918 172.16/12"),
    ("http://172.31.255.255/x", "rfc1918 edge"),
    ("http://192.168.1.1/x", "rfc1918 192.168/16"),
    ("http://169.254.169.254/latest/meta-data/", "link-local cloud metadata"),
    ("http://[fe80::1]/x", "link-local v6"),
    ("http://100.64.0.1/x", "cgnat"),
    ("http://localhost/x", "localhost hostname"),
    ("http://LocalHost/x", "case-insensitive localhost"),
    ("http://foo.local/x", "mDNS suffix"),
    ("http://svc.internal/x", "internal suffix"),
    ("file:///etc/passwd", "non-http scheme"),
    ("ftp://example.com/x", "non-http scheme"),
    ("gopher://127.0.0.1/", "non-http scheme"),
    ("//127.0.0.1/x", "schemeless"),
])
def test_blocked_urls(url, why):
    reason = ng.validate_url(url, resolver=_fake_resolver({}))
    assert reason, f"{why}: expected blocked, got safe: {url}"


def test_public_ip_literal_allowed():
    assert ng.validate_url("https://93.184.216.34/x") == ""


def test_public_domain_allowed():
    r = _fake_resolver({"example.com": ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"]})
    assert ng.validate_url("https://example.com/page", resolver=r) == ""


def test_dns_rebinding_mixed_public_private_blocked():
    # one public + one private A record -> must block (any bad IP blocks)
    r = _fake_resolver({"evil.com": ["93.184.216.34", "192.168.0.10"]})
    reason = ng.validate_url("https://evil.com", resolver=r)
    assert reason and "private" in reason


def test_dns_rebinding_reloopback_blocked():
    r = _fake_resolver({"ok.com": ["127.0.0.1"]})
    assert "loopback" in ng.validate_url("https://ok.com", resolver=r)


def test_fetch_discards_response_on_mid_fetch_dns_flip():
    """TOCTOU: pre-fetch resolution public, post-fetch re-resolution
    private (record flipped between validate and connect) — the already
    received body must be discarded, never returned."""

    class FlipResolver:
        def __init__(self):
            self.calls = 0

        def __call__(self, host):
            self.calls += 1
            if self.calls == 1:
                return ["93.184.216.34"]
            return ["169.254.169.254"]

    c = FakeClient([FakeResp(200, {"content-type": "text/plain"}, b"stolen-metadata")])
    with pytest.raises(ng.NetGuardError, match="changed mid-fetch|discarding"):
        ng.safe_get("https://flip.example", transport=c, resolver=FlipResolver())


def test_fetch_stable_dns_passes_post_check():
    c = FakeClient([FakeResp(200, {"content-type": "text/plain"}, b"fine")])
    out = ng.safe_get("https://example.com", transport=c,
                      resolver=_fake_resolver({"example.com": ["93.184.216.34"]}))
    assert out.text == "fine"


def test_dns_failure_blocks():
    assert "dns failure" in ng.validate_url("https://nope.invalid", resolver=_fake_resolver({}))


# ---------------------------------------------------------------- safe_get
class FakeResp:
    def __init__(self, status=200, headers=None, body=b"", url="http://x.test/"):
        self.status_code = status
        self.headers = headers or {}
        self._body = body
        self.url = url
        self.encoding = "utf-8"

    @property
    def is_redirect(self):
        return 300 <= self.status_code < 400 and "location" in self.headers

    def iter_bytes(self):
        yield self._body


class FakeClient:
    """httpx.Client-shaped double. safe_get streams (`client.stream(...)` as
    a context manager) since the web_fetch streaming fix; the real-httpx
    regression pins live at the bottom of this file."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requested = []

    @contextlib.contextmanager
    def stream(self, method, url, headers=None, timeout=None):
        self.requested.append(url)
        r = self.responses.pop(0)
        yield r if isinstance(r, FakeResp) else r(self)  # callable hooks see client

    def close(self):
        pass


def test_fetch_ok():
    c = FakeClient([FakeResp(200, {"content-type": "text/html; charset=utf-8"}, b"<html>hi</html>")])
    out = ng.safe_get("https://example.com", transport=c)
    assert out.status == 200 and "hi" in out.text and out.content_type == "text/html"
    assert c.requested == ["https://example.com"]


def test_fetch_redirect_revalidated():
    # public -> loopback redirect must be blocked even though hop 1 passed
    hop1 = FakeResp(302, {"location": "http://127.0.0.1:8787/steal"}, url="https://example.com")
    c = FakeClient([hop1])
    with pytest.raises(ng.NetGuardError, match="loopback|blocked"):
        ng.safe_get("https://example.com", transport=c)
    assert c.requested == ["https://example.com"]  # never fetched the target


def test_fetch_redirect_chain_ok_and_capped():
    hop1 = FakeResp(302, {"location": "https://example.com/2"}, url="https://example.com/1")
    hop2 = FakeResp(200, {"content-type": "text/plain"}, b"ok")
    c = FakeClient([hop1, hop2])
    out = ng.safe_get("https://example.com/1", transport=c,
                      resolver=_fake_resolver({"example.com": ["93.184.216.34"]}))
    assert out.status == 200 and out.redirects == 1

    loop = [FakeResp(302, {"location": "https://example.com/1"}, url="https://example.com/x") for _ in range(10)]
    c2 = FakeClient(loop)
    with pytest.raises(ng.NetGuardError, match="too many redirects"):
        ng.safe_get("https://example.com/1", transport=c2, max_redirects=3,
                    resolver=_fake_resolver({"example.com": ["93.184.216.34"]}))


def test_fetch_size_limit():
    big = FakeResp(200, {"content-type": "text/plain"}, b"x" * 3000)
    c = FakeClient([big])
    with pytest.raises(ng.NetGuardError, match="size limit"):
        ng.safe_get("https://example.com", transport=c, max_bytes=1000)


def test_fetch_content_type_enforced():
    pdf = FakeResp(200, {"content-type": "application/pdf"}, b"%PDF-1.4")
    c = FakeClient([pdf])
    with pytest.raises(ng.NetGuardError, match="content-type"):
        ng.safe_get("https://example.com", transport=c)


def test_fetch_no_content_type_allowed():
    c = FakeClient([FakeResp(200, {}, b"plain bytes")])
    out = ng.safe_get("https://example.com", transport=c)
    assert out.bytes_read == len(b"plain bytes")


# ------------------------------------- REAL httpx machinery (P1-7 regression)
def _real_client(handler):
    """A real httpx.Client over MockTransport (still no network) — the fake
    transport above cannot distinguish 'streamed' from 'already consumed',
    which is exactly how the live bug hid."""
    import httpx
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


_REAL_RESOLVER = _fake_resolver({"example.com": ["93.184.216.34"]})


def test_safe_get_streams_a_real_httpx_response():
    """REGRESSION (found by the P1-7 live check, 2026-10-18): safe_get used
    client.get() (full body read + closed) and then resp.iter_raw() — real
    httpx raises StreamConsumed ('content has already been streamed') on
    EVERY fetch; the fake transports yielded happily, so the suite stayed
    green while live web_fetch returned only that error. This drives the
    REAL response objects via MockTransport; reverting to get()+iter_raw()
    fails here the same way live did."""
    import httpx

    def handler(req):
        return httpx.Response(200, headers={"content-type": "text/plain; charset=utf-8"},
                              content=b"hello real httpx")

    c = _real_client(handler)
    try:
        out = ng.safe_get("https://example.com", transport=c, resolver=_REAL_RESOLVER)
    finally:
        c.close()
    assert out.status == 200 and out.text == "hello real httpx"
    assert out.bytes_read == len(b"hello real httpx")


def test_safe_get_decodes_content_encoding_and_caps_decoded_bytes():
    """iter_bytes (not iter_raw) under the streaming fix: a gzip response
    comes back as decoded text, and the size cap counts decoded bytes — a
    small compressed body cannot smuggle an unbounded one past max_bytes."""
    import gzip
    import httpx

    plain = b"zip-decode-me" * 200
    body = gzip.compress(plain)

    def handler(req):
        return httpx.Response(200, headers={"content-type": "text/plain",
                                            "content-encoding": "gzip"},
                              content=body)

    c = _real_client(handler)
    try:
        out = ng.safe_get("https://example.com", transport=c, resolver=_REAL_RESOLVER)
        assert out.text == plain.decode("utf-8")
        with pytest.raises(ng.NetGuardError, match="size limit"):
            ng.safe_get("https://example.com", transport=c, resolver=_REAL_RESOLVER,
                        max_bytes=len(plain) // 2)
    finally:
        c.close()


def test_safe_get_streams_redirect_chain_under_real_httpx():
    import httpx

    def handler(req):
        if req.url.path == "/a":
            return httpx.Response(302, headers={"location": "https://example.com/b"})
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"end")

    c = _real_client(handler)
    try:
        out = ng.safe_get("https://example.com/a", transport=c, resolver=_REAL_RESOLVER)
    finally:
        c.close()
    assert out.status == 200 and out.text == "end"
    assert out.redirects == 1 and out.url == "https://example.com/b"
