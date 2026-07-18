"""Link extraction from HTML/XML (regex-based — no JS execution, no external parser dep).

Extracts: crawlable page links (<a href>), feed-autodiscovery links (<link rel=alternate>),
and sitemap entries (<loc>). Deterministic and pure.
"""

from __future__ import annotations

import re

from app.discovery.models import FeedType
from app.discovery.urls import normalize_url

_A_HREF = re.compile(r'<a\b[^>]*?\bhref\s*=\s*["\']([^"\'#]+)["\']', re.IGNORECASE)
_LINK_TAG = re.compile(r"<link\b[^>]*?>", re.IGNORECASE)
_ATTR = {
    name: re.compile(rf'\b{name}\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
    for name in ("rel", "type", "href")
}
_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)

_FEED_MIME = {
    "application/rss+xml": FeedType.RSS,
    "application/atom+xml": FeedType.ATOM,
    "application/feed+json": FeedType.JSON_FEED,
    "application/json+feed": FeedType.JSON_FEED,
    "text/calendar": FeedType.ICS,
}


def extract_page_links(html: str, base: str) -> list[str]:
    """Normalized absolute <a href> links (deduped, order-preserving)."""
    seen: set[str] = set()
    out: list[str] = []
    for href in _A_HREF.findall(html):
        norm = normalize_url(href, base)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def extract_feed_links(html: str, base: str) -> list[tuple[str, FeedType]]:
    """Feed-autodiscovery links: <link rel="alternate" type="application/rss+xml" href=…>."""
    out: list[tuple[str, FeedType]] = []
    for tag in _LINK_TAG.findall(html):
        rel = (
            (_ATTR["rel"].search(tag) or [None, ""])[1].lower() if _ATTR["rel"].search(tag) else ""
        )
        type_ = (
            (_ATTR["type"].search(tag) or [None, ""])[1].lower()
            if _ATTR["type"].search(tag)
            else ""
        )
        href_m = _ATTR["href"].search(tag)
        if not href_m or "alternate" not in rel:
            continue
        feed_type = _FEED_MIME.get(type_)
        if feed_type:
            norm = normalize_url(href_m.group(1), base)
            if norm:
                out.append((norm, feed_type))
    return out


def extract_sitemap_locs(xml: str, base: str | None = None) -> list[str]:
    """<loc> URLs from a sitemap or sitemap index."""
    seen: set[str] = set()
    out: list[str] = []
    for loc in _LOC.findall(xml):
        norm = normalize_url(loc.strip(), base)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out
