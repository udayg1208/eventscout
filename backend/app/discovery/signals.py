"""Deterministic confidence signals for a candidate (D1 collects signals, no final score).

Reuses the catalog's own tech taxonomy (5A) so "technology relevance" means the same thing
here as downstream. Every signal is a boolean or count derived purely from the fetched bytes.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.city import detect_city
from app.discovery.feeds import FeedDetection
from app.discovery.fetch import FetchResult
from app.discovery.models import ConfidenceSignals, FeedType
from app.enrichment.taxonomy import TECHNOLOGIES, TOPICS

_ORGANIZER = re.compile(
    r"\b(organi[sz]ed by|hosted by|community|chapter|user group|developer group|"
    r"meetup|gdg|society|foundation|\bclub\b)\b",
    re.IGNORECASE,
)
_REGISTER = re.compile(
    r"\b(register|registration|rsvp|tickets?|book now|sign ?up)\b|"
    r"eventbrite|lu\.ma|devfolio|konfhub|hopin|airmeet",
    re.IGNORECASE,
)
_INDIA = re.compile(r"\bindia\b|\bindian\b", re.IGNORECASE)
_EVENTISH_LINK = re.compile(r"/(events?|e|meetup)/", re.IGNORECASE)
_SCAN_LIMIT = 60_000


def _tech_keyword_count(text_lower: str) -> int:
    names: set[str] = set()
    for name, pattern in list(TOPICS) + list(TECHNOLOGIES):
        if pattern.search(text_lower):
            names.add(name)
    return len(names)


def collect_signals(
    result: FetchResult,
    detections: list[FeedDetection],
    page_links: list[str],
    analysis: object | None = None,
) -> ConfidenceSignals:
    body = result.text[:_SCAN_LIMIT]
    low = body.lower()
    types = {d.feed_type for d in detections}
    event_count = max((d.event_count for d in detections), default=0)
    host = (urlsplit(result.url).hostname or "").lower()

    india_refs = len(_INDIA.findall(low))
    if host.endswith(".in"):
        india_refs += 1
    if "₹" in body:
        india_refs += 1
    if detect_city(body):
        india_refs += 1

    eventish_links = sum(1 for u in page_links if _EVENTISH_LINK.search(u))
    d2 = getattr(analysis, "signals", {}) or {}
    embedded = getattr(analysis, "embedded_event_count", 0) or 0
    event_count = max(event_count, embedded)

    return ConfidenceSignals(
        has_jsonld_event=FeedType.JSONLD_EVENT in types,
        has_microdata_event=FeedType.MICRODATA_EVENT in types,
        has_opengraph_event=FeedType.OPENGRAPH_EVENT in types,
        has_rss=FeedType.RSS in types,
        has_atom=FeedType.ATOM in types,
        has_ics=FeedType.ICS in types or FeedType.GOOGLE_CALENDAR in types,
        has_json_feed=FeedType.JSON_FEED in types,
        has_sitemap=FeedType.XML_SITEMAP in types or FeedType.EVENT_SITEMAP in types,
        has_google_calendar=FeedType.GOOGLE_CALENDAR in types,
        tech_keyword_count=_tech_keyword_count(low),
        india_reference_count=min(india_refs, 10),
        has_organizer=bool(_ORGANIZER.search(low)),
        has_registration_link=bool(_REGISTER.search(low)),
        has_recurring=event_count > 1 or eventish_links > 1,
        event_count=event_count,
        has_framework=d2.get("has_framework", False),
        has_nextjs=d2.get("has_nextjs", False),
        has_hydration=d2.get("has_hydration", False),
        has_embedded_events=d2.get("has_embedded_events", False),
        has_json_array=d2.get("has_json_array", False),
        has_calendar_schema=d2.get("has_calendar_schema", False),
        has_api_endpoint=d2.get("has_api_endpoint", False),
        has_graphql_endpoint=d2.get("has_graphql_endpoint", False),
    )
