"""URL normalization, registrable-domain extraction, and crawl-scope checks.

Normalization gives a stable dedup key (so re-discovery updates, not duplicates) and keeps the
crawler from looping. Deterministic and pure.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

_TRACKING = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}
# Multi-label public suffixes we care about (India-first + a few common).
_MULTI_TLDS = {
    "co.in",
    "org.in",
    "net.in",
    "edu.in",
    "ac.in",
    "gov.in",
    "gen.in",
    "firm.in",
    "ind.in",
    "res.in",
    "co.uk",
    "org.uk",
    "com.au",
}


def _host_of(host_or_url: str) -> str:
    host = host_or_url.strip()
    if "//" in host or host.startswith("http"):
        host = urlsplit(host if "//" in host else f"//{host}").hostname or host
    host = (host or "").lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def normalize_url(url: str, base: str | None = None) -> str | None:
    """Canonical form for dedup: resolve relative→absolute, lowercase scheme+host, drop
    fragment + default port + tracking params, sort query, strip trailing slash. Returns None
    for non-http(s) or malformed URLs."""
    if base:
        url = urljoin(base, url)
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    host = (parts.hostname or "").lower()
    if not host:
        return None
    netloc = host
    port = parts.port
    if port and not (
        (parts.scheme == "http" and port == 80) or (parts.scheme == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING
    ]
    query_pairs.sort()
    return urlunsplit((parts.scheme, netloc, path, urlencode(query_pairs), ""))


def registrable_domain(host_or_url: str) -> str:
    """Best-effort registrable domain (handles co.in/edu.in/… multi-label suffixes)."""
    host = _host_of(host_or_url)
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    last2 = ".".join(labels[-2:])
    if last2 in _MULTI_TLDS and len(labels) >= 3:
        return ".".join(labels[-3:])
    return last2


def same_scope(url: str, allowed_domains: set[str]) -> bool:
    """True if the URL's host/registrable-domain is within the configured crawl scope."""
    host = _host_of(url)
    if not host:
        return False
    return host in allowed_domains or registrable_domain(host) in allowed_domains
