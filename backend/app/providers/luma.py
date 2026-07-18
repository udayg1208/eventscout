"""Lu.ma provider — India tech / AI community meetups.

Source: Lu.ma (now luma.com) city discovery pages embed the city's upcoming events
as Next.js __NEXT_DATA__ JSON (priority: embedded JSON, no auth, no private API):
    GET https://luma.com/<city-slug>
    -> props.pageProps.initialData.data.events[].event

Fetches a curated set of India city pages concurrently, extracts events from the
embedded JSON, tags each with the page's city (offline events), and dedups by URL.
Parsing is defensive: a city page with a different/empty shape contributes nothing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, date, datetime, timedelta

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

PROVIDER_NAME = "luma"
LUMA_BASE = "https://luma.com"
_CACHE_KEY = "luma:india-upcoming"
_DATA_TTL_SECONDS = 1800
_IST_OFFSET = timedelta(hours=5, minutes=30)
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)

# India city discovery slugs -> canonical city name. NOTE (Phase 3G P0.1): expanding to 9
# more cities + slug variants was measured to add 0 net events — these 11 already capture
# Lu.ma's India tech events. Kept lean; family closed for expansion.
CITY_SLUGS: dict[str, str] = {
    "bengaluru": "Bangalore",
    "mumbai": "Mumbai",
    "new-delhi": "Delhi",
    "hyderabad": "Hyderabad",
    "pune": "Pune",
    "chennai": "Chennai",
    "kolkata": "Kolkata",
    "gurugram": "Gurgaon",
    "goa": "Goa",
    "ahmedabad": "Ahmedabad",
    "jaipur": "Jaipur",
}


def _ist_date(iso: str) -> date:
    """Lu.ma start/end are UTC; return the India-local calendar date."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC) + _IST_OFFSET
    return dt.date()


def extract_events(html: str) -> list[dict]:
    """Return the event dicts embedded in a Lu.ma city page (or [] if the shape differs)."""
    match = _NEXT_DATA.search(html)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return []
    node = (((data.get("props") or {}).get("pageProps") or {}).get("initialData") or {}).get("data")
    wrappers = node.get("events") if isinstance(node, dict) else None
    if not isinstance(wrappers, list):
        return []
    return [
        w["event"] for w in wrappers if isinstance(w, dict) and isinstance(w.get("event"), dict)
    ]


def normalize_event(event: dict, city: str) -> Event | None:
    name = event.get("name")
    slug = event.get("url")
    start_raw = event.get("start_at")
    if not name or not slug or not start_raw:
        return None
    try:
        start = _ist_date(start_raw)
    except ValueError:
        return None

    end: date | None = None
    end_raw = event.get("end_at")
    if end_raw:
        try:
            candidate = _ist_date(end_raw)
            if candidate != start:
                end = candidate
        except ValueError:
            end = None

    is_online = event.get("location_type") in ("online", "virtual", "zoom")
    try:
        return Event(
            title=name,
            description=None,
            url=f"https://lu.ma/{slug}",
            city=None if is_online else normalize_city(city),
            location="Online" if is_online else city,
            is_online=is_online,
            start_date=start,
            end_date=end,
            category=category_from_title(name, default=EventCategory.MEETUP),
            is_free=None,
            price=None,
            provider=PROVIDER_NAME,
        )
    except ValidationError:
        return None


class LumaProvider(EventProvider):
    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        ttl_seconds: float = _DATA_TTL_SECONDS,
        transport: httpx.BaseTransport | None = None,
        base_url: str = LUMA_BASE,
        cities: dict[str, str] | None = None,
        today: date | None = None,
    ) -> None:
        self._cache: TTLCache[str, list[Event]] = TTLCache(ttl_seconds)
        self._transport = transport
        self._base = base_url
        self._cities = cities or CITY_SLUGS
        self._today = today

    async def search(self, query: SearchQuery) -> list[Event]:
        events = self._cache.get(_CACHE_KEY)
        if events is None:
            events = await self._load()
            if events:
                self._cache.set(_CACHE_KEY, events)
        return [event for event in events if matches(event, query)]

    async def _load(self) -> list[Event]:
        today = self._today or date.today()
        async with httpx.AsyncClient(
            transport=self._transport, timeout=15.0, follow_redirects=True
        ) as client:
            pages = await asyncio.gather(*(self._get(client, slug) for slug in self._cities))

        seen: set[str] = set()
        events: list[Event] = []
        for slug, html in pages:
            if not html:
                continue
            for raw in extract_events(html):
                event = normalize_event(raw, self._cities[slug])
                if event is None:
                    continue
                key = str(event.url)
                # dedup across city pages; keep only genuinely upcoming events
                if key not in seen and (event.end_date or event.start_date) >= today:
                    seen.add(key)
                    events.append(event)
        logger.info(
            "luma: loaded %d upcoming India events across %d cities",
            len(events),
            len(self._cities),
        )
        return events

    async def _get(self, client: httpx.AsyncClient, slug: str) -> tuple[str, str | None]:
        try:
            response = await client.get(
                f"{self._base}/{slug}", headers={"User-Agent": "Mozilla/5.0"}
            )
            if response.status_code == 200:
                return slug, response.text
        except httpx.HTTPError as exc:
            logger.warning("luma fetch failed for %s: %s", slug, exc)
        return slug, None
