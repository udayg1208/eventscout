"""Meetup provider — India tech community events from the public Meetup find page.

Source: Meetup's public search page embeds its results as Next.js `__NEXT_DATA__` JSON (the exact
same "read the embedded JSON of a public page" technique the Lu.ma provider already uses — no auth,
no API key, no private endpoint):
    GET https://www.meetup.com/find/?keywords=<kw>&location=in--<City>&source=EVENTS
    -> props … __typename == "Event"  (title, eventUrl, dateTime[IST], venue, feeSettings)

Meetup hosts thousands of India tech groups that publish only on Meetup, so a keyword × city sweep
surfaces a large, otherwise-unreachable slice of the ecosystem. We fetch a curated keyword/city
matrix concurrently, extract the embedded events, keep upcoming ones, and dedup by event URL.
Normalization is honest: title/URL/date come straight from the page, online/offline from the venue,
price/description stay None (never fabricated). A polite concurrency cap bounds the request rate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date

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

PROVIDER_NAME = "meetup"
FIND_URL = "https://www.meetup.com/find/"
_CACHE_KEY = "meetup:india-find"
_DATA_TTL_SECONDS = 3600
_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)

# Keyword × city sweep. Broad tech keywords across metros + Tier-2/3 hubs; Meetup's location
# search covers a regional radius, so a handful of anchor cities reaches surrounding ecosystems.
KEYWORDS = (
    "technology",
    "artificial intelligence",
    "generative ai",
    "machine learning",
    "deep learning",
    "llm",
    "data science",
    "data analytics",
    "python",
    "javascript",
    "react",
    "nodejs",
    "java",
    "golang",
    "rust",
    "flutter",
    "android",
    "web development",
    "backend",
    "devops",
    "docker",
    "kubernetes",
    "linux",
    "cloud computing",
    "aws",
    "azure",
    "cybersecurity",
    "blockchain",
    "web3",
    "iot",
    "robotics",
    "virtual reality",
    "game development",
    "ui ux",
    "product management",
    "startup",
    "hackathon",
    "open source",
    "tensorflow",
    "langchain",
    "ai agents",
    "pydata",
)
CITIES: dict[str, str] = {
    "in--Bangalore": "Bangalore",
    "in--Delhi": "Delhi",
    "in--Mumbai": "Mumbai",
    "in--Pune": "Pune",
    "in--Hyderabad": "Hyderabad",
    "in--Chennai": "Chennai",
    "in--Kolkata": "Kolkata",
    "in--Ahmedabad": "Ahmedabad",
    "in--Noida": "Noida",
    "in--Gurgaon": "Gurgaon",
    "in--Jaipur": "Jaipur",
    "in--Indore": "Indore",
    "in--Coimbatore": "Coimbatore",
    "in--Chandigarh": "Chandigarh",
    "in--Lucknow": "Lucknow",
    "in--Bhubaneswar": "Bhubaneswar",
    "in--Nagpur": "Nagpur",
    "in--Kochi": "Kochi",
    "in--Thiruvananthapuram": "Thiruvananthapuram",
    "in--Visakhapatnam": "Visakhapatnam",
}
_CONCURRENCY = 8


def _extract_events(html: str) -> list[dict]:
    """Return the Event dicts embedded in a Meetup find page (or [] if the shape differs)."""
    match = _NEXT_DATA.search(html)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return []
    out: list[dict] = []
    stack: list = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("__typename") == "Event" and node.get("title") and node.get("eventUrl"):
                out.append(node)
            stack.extend(v for v in node.values() if isinstance(v, dict | list))
        elif isinstance(node, list):
            stack.extend(node)
    return out


def normalize_event(ev: dict, search_city: str) -> Event | None:
    """Map one embedded Meetup event into an Event, or None if unusable (never fabricates)."""
    title = ev.get("title")
    url = ev.get("eventUrl")
    dt = ev.get("dateTime")
    if not title or not url or not dt:
        return None
    try:
        start = date.fromisoformat(dt[:10])  # dateTime carries the IST offset; date part is local
    except ValueError:
        return None

    venue = ev.get("venue") or {}
    vname = (venue.get("name") or "").strip().lower()
    vcity = (venue.get("city") or "").strip()
    is_online = vname == "online event" or (not venue.get("address") and not vcity)
    city = None if is_online else (vcity or search_city)

    try:
        return Event(
            title=title,
            description=None,
            url=url,
            city=None if is_online else normalize_city(city),
            location="Online" if is_online else (venue.get("name") or city),
            is_online=is_online,
            start_date=start,
            end_date=None,
            category=category_from_title(title, default=EventCategory.MEETUP),
            is_free=None,
            price=None,
            provider=PROVIDER_NAME,
        )
    except ValidationError:
        return None


class MeetupProvider(EventProvider):
    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        ttl_seconds: float = _DATA_TTL_SECONDS,
        transport: httpx.BaseTransport | None = None,
        base_url: str = FIND_URL,
        keywords: tuple[str, ...] = KEYWORDS,
        cities: dict[str, str] | None = None,
        today: date | None = None,
        concurrency: int = _CONCURRENCY,
    ) -> None:
        self._cache: TTLCache[str, list[Event]] = TTLCache(ttl_seconds)
        self._transport = transport
        self._base = base_url
        self._keywords = keywords
        self._cities = cities or CITIES
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
        combos = [(kw, loc) for kw in self._keywords for loc in self._cities]
        async with httpx.AsyncClient(
            transport=self._transport, timeout=20.0, follow_redirects=True
        ) as client:
            pages = await asyncio.gather(*(self._get(client, kw, loc) for kw, loc in combos))

        seen: set[str] = set()
        events: list[Event] = []
        for (_, loc), html in zip(combos, pages, strict=True):
            if not html:
                continue
            for raw in _extract_events(html):
                event = normalize_event(raw, self._cities[loc])
                if event is None:
                    continue
                key = str(event.url)
                if key in seen or (event.end_date or event.start_date) < today:
                    continue
                seen.add(key)
                events.append(event)
        logger.info(
            "meetup: loaded %d upcoming events across %d searches", len(events), len(combos)
        )
        return events

    async def _get(self, client: httpx.AsyncClient, keyword: str, location: str) -> str | None:
        params = {"keywords": keyword, "location": location, "source": "EVENTS"}
        async with self._sem:
            try:
                response = await client.get(
                    self._base, params=params, headers={"User-Agent": _UA}
                )
                if response.status_code == 200:
                    return response.text
            except httpx.HTTPError as exc:
                logger.warning("meetup fetch failed (%s/%s): %s", keyword, location, exc)
        return None
