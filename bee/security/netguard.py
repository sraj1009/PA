"""SSRF-hardened HTTP fetching for model-driven web tools.

The `web_fetch` tool receives URLs from the LLM (i.e. from the user's task
and from web content — both untrusted input). Without protection that is a
full SSRF primitive: it can read localhost services, RFC1918 hosts, and
cloud metadata endpoints (169.254.169.254).

Rules (fail closed):
  - only http/https schemes
  - no localhost-class hostnames (localhost, *.local, *.internal, metadata)
  - IP literals and ALL resolved addresses must be public:
      reject loopback (127.0.0.0/8, ::1), RFC1918 (10/8, 172.16/12,
      192.168/16, fc00::/7), link-local (169.254.0.0/16, fe80::/10),
      unspecified (0.0.0.0, ::), multicast, CGNAT (100.64.0.0/10)
  - EVERY redirect hop is re-validated (open redirect bypass protection)
  - connect + read timeouts enforced
  - response size cap enforced while streaming
  - content-type allow-list enforced
  - transport is injectable for hermetic tests

`validate_url` is a pure function (resolver injectable) — the rest of the
app can call it anywhere a URL crosses a trust boundary.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class NetGuardError(Exception):
    """Raised when a URL or its fetch violates the SSRF policy."""


# hostnames that are blocked even when DNS is not consulted
BLOCKED_HOSTNAMES = {
    "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback",
    "metadata", "metadata.google.internal", "broadcast", "this",
}
_BLOCKED_SUFFIXES = (".local", ".internal", ".localhost", ".home.arpa")

_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_IETF = ipaddress.ip_network("192.0.0.0/24")
# 198.18-19/15 (benchmarking) is not private per is_private on py<3.11 edges —
# block it explicitly.
_BENCH = [ipaddress.ip_network("198.18.0.0/15")]

ALLOWED_CONTENT_TYPES = (
    "text/html", "text/plain", "text/xml", "application/xml",
    "application/json", "text/css", "application/xhtml+xml", "text/csv",
    "application/javascript", "application/x-ndjson",
)


def _ip_class(ip: str) -> str | None:
    """Return a blocking class name for a non-public IP, else None."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return "unparseable address"
    if a.is_loopback:
        return "loopback"
    if a.is_private:
        return "private/rfc1918"
    if a.is_link_local:
        return "link-local"
    if a.is_unspecified:
        return "unspecified"
    if a.is_multicast:
        return "multicast"
    if a in _CGNAT:
        return "cgnat (100.64/10)"
    if any(a in n for n in _BENCH):
        return "reserved benchmarking"
    return None


def resolve_all(host: str) -> list[str]:
    """Resolve a hostname to ALL of its addresses (A + AAAA)."""
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return sorted({i[4][0].split("%")[0] for i in infos})


def validate_url(url: str, *, resolver=resolve_all) -> str:
    """Pure SSRF check. Returns "" if the URL is safe, else a reason.

    `resolver` is injectable (tests pass a fake — no network needed).
    """
    try:
        p = urlparse(str(url).strip())
    except Exception:
        return "unparseable url"
    if p.scheme not in ("http", "https"):
        return f"scheme {p.scheme!r} not allowed (http/https only)"
    host = (p.hostname or "").lower()
    if not host:
        return "missing host"
    if host in BLOCKED_HOSTNAMES:
        return f"blocked hostname {host!r}"
    if host.endswith(_BLOCKED_SUFFIXES):
        return f"blocked hostname suffix ({host!r})"
    # IP literal — classify directly; non-IP hostnames fall through to DNS
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        reason = _ip_class(host)
        return f"IP {host} is {reason}" if reason else ""
    try:
        ips = resolver(host)
    except Exception as e:
        return f"dns failure for {host}: {str(e)[:120]}"
    if not ips:
        return f"dns returned no addresses for {host}"
    for ip in ips:
        reason = _ip_class(ip)
        if reason:
            return f"host {host} resolves to a {reason} address ({ip})"
    return ""


@dataclass
class FetchResult:
    text: str
    url: str            # final URL after redirects
    status: int
    content_type: str
    bytes_read: int
    redirects: int = 0
    truncated: bool = False


def safe_get(url: str, *,
             connect_timeout: float = 6.0,
             read_timeout: float = 20.0,
             max_bytes: int = 1_500_000,
             max_redirects: int = 5,
             allowed_content_types: tuple[str, ...] = ALLOWED_CONTENT_TYPES,
             headers: dict | None = None,
             resolver=resolve_all,
             transport=None) -> FetchResult:
    """Fetch a URL under the full SSRF policy. Raises NetGuardError on any
    violation. `transport` is an injectable httpx.Client-compatible object
    (tests pass a fake); when omitted a client is created + closed here."""
    import httpx

    hdrs = {"User-Agent": UA, "Accept": "text/html,application/json,text/plain,*/*"}
    if headers:
        hdrs.update(headers)
    client = transport if transport is not None else httpx.Client(follow_redirects=False)
    owned = transport is None
    current = str(url)
    try:
        redirects = 0
        while True:
            reason = validate_url(current, resolver=resolver)
            if reason:
                raise NetGuardError(f"blocked: {reason}")
            resp = client.get(current, headers=hdrs,
                               timeout=httpx.Timeout(read_timeout, connect=connect_timeout))
            if resp.is_redirect and "location" in resp.headers:
                redirects += 1
                if redirects > max_redirects:
                    raise NetGuardError(f"too many redirects (>{max_redirects})")
                current = urljoin(str(resp.url), resp.headers["location"])
                continue
            ct = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            ct_base = ct.split("+", 1)[0]
            if ct and ct not in allowed_content_types and ct_base not in allowed_content_types:
                raise NetGuardError(f"content-type {ct!r} not allowed "
                                    f"(allowed: {', '.join(allowed_content_types[:4])}, ...)")
            buf = bytearray()
            for chunk in resp.iter_raw():
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise NetGuardError(f"response exceeds size limit ({max_bytes} bytes)")
            text = buf.decode(resp.encoding or "utf-8", errors="replace")
            return FetchResult(text=text, url=str(resp.url), status=resp.status_code,
                               content_type=ct, bytes_read=len(buf), redirects=redirects)
    finally:
        if owned:
            try:
                client.close()
            except Exception:
                pass
