"""Eventbrite provider — India tech events from public Eventbrite discovery pages.

Source: Eventbrite's public discovery pages embed their search results as a `window.__SERVER_DATA__`
JSON blob (no auth, no API key — the same public-page-JSON technique as the Lu.ma/Meetup providers):
    GET https://www.eventbrite.com/d/<scope>/  (e.g. india/technology--events, online/technology)
    -> search_data.events.results[]  (name, url, start_date, is_online_event, primary_venue.address)

Eventbrite organizers post directly (a primary source, so little overlap with the community
platforms already indexed). We read a curated set of India tech scopes + Tier-2/3 city scopes,
extract the embedded events, keep upcoming ones, and dedup by URL. Honest normalization: title/URL/
date from the page, online/offline from the venue, price/description None (never fabricated).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from app.cache import TTLCache
from app.city import normalize_city
from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.base import EventProvider
from app.providers.categorize import category_from_title
from app.providers.filtering import matches

logger = logging.getLogger(__name__)

PROVIDER_NAME = "eventbrite"
BASE = "https://www.eventbrite.com/d"
_CACHE_KEY = "eventbrite:india-tech"
_DATA_TTL_SECONDS = 3600
_MARKER = "window.__SERVER_DATA__"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120"

# Discovery is scoped by <location>/<keyword>--events. We sweep many tech keywords across India +
# online + Tier-2/3 city scopes, so each keyword surfaces a different slice of the catalogue.
KEYWORDS: tuple[str, ...] = (
    "technology",
    "software",
    "developer",
    "artificial-intelligence",
    "machine-learning",
    "data-science",
    "hackathon",
    "conference",
    "engineering",
    "startup",
    "innovation",
    "cloud-computing",
    "web-development",
    "cybersecurity",
    "blockchain",
    "devops",
    "iot",
    "robotics",
    "product",
    "networking",
    "python",
    "developer-tools",
)
LOCATIONS: tuple[str, ...] = (
    "india",
    "online",
    "india--bangalore",
    "india--delhi",
    "india--mumbai",
    "india--pune",
    "india--hyderabad",
    "india--chennai",
    "india--kolkata",
    "india--ahmedabad",
    "india--noida",
    "india--gurgaon",
    "india--jaipur",
    "india--indore",
    "india--coimbatore",
    "india--chandigarh",
)
_PAGES = 2  # logged-out discovery exposes only the first couple of pages
_CONCURRENCY = 8
_ALLOWED_HOST = "eventbrite.com"  # India events live on the .com domain; drop foreign-country ones


def _extract_json_object(text: str, start: int) -> str | None:
    """Return the balanced `{...}` starting at `start`, respecting strings/escapes."""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _events_from(html: str) -> list[dict]:
    idx = html.find(_MARKER)
    if idx < 0:
        return []
    brace = html.find("{", idx)
    if brace < 0:
        return []
    raw = _extract_json_object(html, brace)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    results = (((data.get("search_data") or {}).get("events") or {}).get("results")) or []
    return results if isinstance(results, list) else []


def normalize_event(ev: dict) -> Event | None:
    """Map one Eventbrite search result into an Event, or None if unusable (never fabricates)."""
    name = ev.get("name")
    if isinstance(name, dict):
        name = name.get("text")
    url = ev.get("url")
    start_raw = ev.get("start_date")
    if not name or not url or not start_raw:
        return None
    try:
        start = date.fromisoformat(str(start_raw)[:10])
    except ValueError:
        return None

    is_online = bool(ev.get("is_online_event"))
    venue = ev.get("primary_venue") or {}
    address = venue.get("address") or {}
    city = address.get("city") or None

    try:
        return Event(
            title=name,
            description=None,
            url=str(url).split("?")[0],
            city=None if is_online else (normalize_city(city) if city else None),
            location="Online" if is_online else (address.get("localized_address_display") or city),
            is_online=is_online,
            start_date=start,
            end_date=None,
            category=category_from_title(name, default=EventCategory.CONFERENCE),
            is_free=None,
            price=None,
            provider=PROVIDER_NAME,
        )
    except ValidationError:
        return None


class EventbriteProvider(EventProvider):
    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        ttl_seconds: float = _DATA_TTL_SECONDS,
        transport: httpx.BaseTransport | None = None,
        base_url: str = BASE,
        keywords: tuple[str, ...] = KEYWORDS,
        locations: tuple[str, ...] = LOCATIONS,
        pages: int = _PAGES,
        today: date | None = None,
        concurrency: int = _CONCURRENCY,
    ) -> None:
        self._cache: TTLCache[str, list[Event]] = TTLCache(ttl_seconds)
        self._transport = transport
        self._base = base_url
        self._keywords = keywords
        self._locations = locations
        self._pages = pages
        self._today = today
        self._sem = asyncio.Semaphore(concurrency)

    async def search(self, query: SearchQuery) -> list[Event]:
        events = self._cache.get(_CACHE_KEY)
        if events is None:
            events = await self._load()
            if events:
                self._cache.set(_CACHE_KEY, events)
        return [event for event in events if matches(event, query)]

    async def _load(self) -> list[Event]:
        today = self._today or date.today()
        urls = [
            f"{self._base}/{loc}/{kw}--events/?page={p}"
            for loc in self._locations
            for kw in self._keywords
            for p in range(1, self._pages + 1)
        ]
        async with httpx.AsyncClient(
            transport=self._transport, timeout=20.0, follow_redirects=True
        ) as client:
            pages = await asyncio.gather(*(self._get(client, url) for url in urls))

        seen: set[str] = set()
        events: list[Event] = []
        for html in pages:
            if not html:
                continue
            for raw in _events_from(html):
                event = normalize_event(raw)
                if event is None:
                    continue
                key = str(event.url)
                # India events are on eventbrite.com; drop foreign-country domains that leak in
                if urlsplit(key).netloc.replace("www.", "") != _ALLOWED_HOST:
                    continue
                if key in seen or (event.end_date or event.start_date) < today:
                    continue
                seen.add(key)
                events.append(event)
        logger.info("eventbrite: loaded %d upcoming India tech events", len(events))
        return events

    async def _get(self, client: httpx.AsyncClient, url: str) -> str | None:
        async with self._sem:
            try:
                response = await client.get(url, headers={"User-Agent": _UA})
                if response.status_code == 200:
                    return response.text
            except httpx.HTTPError as exc:
                logger.warning("eventbrite fetch failed for %s: %s", url, exc)
        return None
