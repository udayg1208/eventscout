"""Feed + structured-data detection — the heart of D1.

Given a fetched response, deterministically classify what ingestible event data it exposes:
RSS, Atom, ICS, JSON Feed, XML/event sitemap, JSON-LD Event, Google Calendar, Microdata,
OpenGraph event. A single HTML page can yield several detections (e.g. JSON-LD + microdata).
Pure functions over the response text — no network.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.discovery.fetch import FetchResult
from app.discovery.models import FeedType

_LD_BLOCK = re.compile(
    r'<script[^>]+type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_MICRODATA_EVENT = re.compile(r'itemtype\s*=\s*["\']https?://schema\.org/Event["\']', re.IGNORECASE)
_OG_EVENT = re.compile(
    r'<meta[^>]+property\s*=\s*["\']og:type["\'][^>]+content\s*=\s*["\'][^"\']*event[^"\']*["\']',
    re.IGNORECASE,
)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_EVENTISH = re.compile(
    r"/(events?|e|meetup|conference|talks?|sessions?|webinars?|workshops?)/", re.IGNORECASE
)


@dataclass(frozen=True)
class FeedDetection:
    feed_type: FeedType
    url: str
    event_count: int = 0
    title: str | None = None


def _walk_ld_events(obj: object) -> tuple[int, str | None]:
    count, title, stack = 0, None, [obj]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            t = node.get("@type")
            if t == "Event" or (isinstance(t, list) and "Event" in t):
                count += 1
                if title is None and isinstance(node.get("name"), str):
                    title = node["name"]
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return count, title


def _jsonld_events(html: str) -> tuple[int, str | None]:
    total, title = 0, None
    for block in _LD_BLOCK.findall(html):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        count, node_title = _walk_ld_events(data)
        total += count
        title = title or node_title
    return total, title


def _page_title(html: str) -> str | None:
    m = _TITLE.search(html)
    return " ".join(m.group(1).split())[:200] if m else None


def detect_feeds(result: FetchResult) -> list[FeedDetection]:
    """All structured-event detections for one fetched response."""
    body = result.text
    ct = result.content_type
    host = (urlsplit(result.url).hostname or "").lower()
    detections: list[FeedDetection] = []

    # --- the response *is* a feed ---
    if ct == "text/calendar" or body.lstrip().startswith("BEGIN:VCALENDAR"):
        n = body.count("BEGIN:VEVENT")
        ftype = FeedType.GOOGLE_CALENDAR if "calendar.google.com" in host else FeedType.ICS
        return [FeedDetection(ftype, result.url, n)]

    stripped = body.lstrip()
    if ct in ("application/feed+json", "application/json") and stripped.startswith("{"):
        try:
            data = json.loads(body)
            if isinstance(data, dict) and "jsonfeed.org" in str(data.get("version", "")):
                items = data.get("items", [])
                return [
                    FeedDetection(
                        FeedType.JSON_FEED, result.url, len(items) if isinstance(items, list) else 0
                    )
                ]
        except ValueError:
            pass

    if "<sitemapindex" in body:
        return [FeedDetection(FeedType.XML_SITEMAP, result.url, body.count("<loc>"))]
    if "<urlset" in body:
        from app.discovery.links import extract_sitemap_locs

        locs = extract_sitemap_locs(body)
        eventish = sum(1 for u in locs if _EVENTISH.search(u))
        ftype = (
            FeedType.EVENT_SITEMAP
            if locs and eventish >= max(1, len(locs) // 4)
            else FeedType.XML_SITEMAP
        )
        return [FeedDetection(ftype, result.url, eventish or len(locs))]
    if re.search(r"<rss\b", body, re.IGNORECASE):
        return [FeedDetection(FeedType.RSS, result.url, body.count("<item"))]
    if re.search(r"<feed\b", body, re.IGNORECASE) and "www.w3.org/2005/atom" in body.lower():
        return [FeedDetection(FeedType.ATOM, result.url, body.count("<entry"))]

    # --- the response is an HTML page that *contains* structured event data ---
    ld_count, ld_title = _jsonld_events(body)
    if ld_count:
        detections.append(
            FeedDetection(
                FeedType.JSONLD_EVENT, result.url, ld_count, ld_title or _page_title(body)
            )
        )
    if _MICRODATA_EVENT.search(body):
        detections.append(
            FeedDetection(
                FeedType.MICRODATA_EVENT,
                result.url,
                len(_MICRODATA_EVENT.findall(body)),
                _page_title(body),
            )
        )
    if _OG_EVENT.search(body):
        detections.append(FeedDetection(FeedType.OPENGRAPH_EVENT, result.url, 1, _page_title(body)))
    return detections
