"""FOSS United provider — India FOSS community events.

Source: FOSS United's Frappe REST API (no key, no auth):
    GET https://fossunited.org/api/resource/FOSS Chapter Event
        ?fields=[...]&filters=[["event_start_date",">=",today],["is_published","=",1]]

FOSS United is India-native, so every event is an India event (no country filter).
The source provides a real event type and a paid/free flag, so those normalize
honestly (not defaulted):
- event_type -> category (Meet Up/Workshop/Conference/Online...)
- is_paid_event -> is_free
- city recovered from event_location / chapter via detect_city (else None).
"""

from __future__ import annotations

import json
import logging
from datetime import date

import httpx
from pydantic import ValidationError

from app.cache import TTLCache
from app.city import detect_city
from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.base import EventProvider
from app.providers.filtering import matches

logger = logging.getLogger(__name__)

PROVIDER_NAME = "fossunited"
FOSS_URL = "https://fossunited.org/api/resource/FOSS Chapter Event"
_CACHE_KEY = "fossunited:upcoming"
_DATA_TTL_SECONDS = 1800
_PAGE_LIMIT = 100
_FIELDS = [
    "event_name",
    "event_type",
    "event_start_date",
    "event_end_date",
    "event_location",
    "event_bio",
    "chapter_name",
    "route",
    "is_paid_event",
]
_TYPE_TO_CATEGORY = {
    "meet up": EventCategory.MEETUP,
    "meetup": EventCategory.MEETUP,
    "talk": EventCategory.MEETUP,
    "workshop": EventCategory.WORKSHOP,
    "conference": EventCategory.CONFERENCE,
    "hackathon": EventCategory.HACKATHON,
    "online": EventCategory.WEBINAR,
    "webinar": EventCategory.WEBINAR,
}


def normalize_event(row: dict) -> Event | None:
    """Map one FOSS Chapter Event row into an Event, or None if unusable."""
    name = row.get("event_name")
    route = row.get("route")
    start_raw = row.get("event_start_date")
    if not name or not route or not start_raw:
        return None
    try:
        start = date.fromisoformat(start_raw[:10])
    except ValueError:
        return None

    end: date | None = None
    end_raw = row.get("event_end_date")
    if end_raw:
        try:
            candidate = date.fromisoformat(end_raw[:10])
            if candidate != start:
                end = candidate
        except ValueError:
            end = None

    event_type = (row.get("event_type") or "").strip().casefold()
    category = _TYPE_TO_CATEGORY.get(event_type, EventCategory.MEETUP)
    is_online = event_type in ("online", "webinar")

    location = row.get("event_location") or row.get("chapter_name") or None
    city = detect_city(row.get("event_location"), row.get("chapter_name"))

    paid = row.get("is_paid_event")
    is_free = (not bool(paid)) if paid is not None else None

    bio = row.get("event_bio")
    description = " ".join(bio.split())[:300] if bio else None

    try:
        return Event(
            title=name,
            description=description,
            url=f"https://fossunited.org/{route.lstrip('/')}",
            city=city,
            location=location,
            is_online=is_online,
            start_date=start,
            end_date=end,
            category=category,
            is_free=is_free,
            price=None,
            provider=PROVIDER_NAME,
        )
    except ValidationError:
        return None


class FOSSUnitedProvider(EventProvider):
    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        ttl_seconds: float = _DATA_TTL_SECONDS,
        transport: httpx.BaseTransport | None = None,
        url: str = FOSS_URL,
        page_limit: int = _PAGE_LIMIT,
        today: date | None = None,
    ) -> None:
        self._cache: TTLCache[str, list[Event]] = TTLCache(ttl_seconds)
        self._transport = transport
        self._url = url
        self._page_limit = page_limit
        self._today = today

    async def search(self, query: SearchQuery) -> list[Event]:
        events = self._cache.get(_CACHE_KEY)
        if events is None:
            events = await self._load()
            if events:
                self._cache.set(_CACHE_KEY, events)
        return [event for event in events if matches(event, query)]

    async def _load(self) -> list[Event]:
        raw = await self._fetch_upcoming()
        normalized = [event for row in raw if (event := normalize_event(row)) is not None]
        logger.info("fossunited: loaded %d upcoming events (%d raw)", len(normalized), len(raw))
        return normalized

    async def _fetch_upcoming(self) -> list[dict]:
        today = (self._today or date.today()).isoformat()
        params = {
            "fields": json.dumps(_FIELDS),
            "filters": json.dumps([["event_start_date", ">=", today], ["is_published", "=", 1]]),
            "order_by": "event_start_date asc",
            "limit_page_length": self._page_limit,
        }
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=15.0) as client:
                response = await client.get(
                    self._url, params=params, headers={"Accept": "application/json"}
                )
                if response.status_code == 200:
                    rows = response.json().get("data", [])
                    if isinstance(rows, list):
                        if len(rows) >= self._page_limit:
                            logger.warning(
                                "fossunited: hit page limit (%d); results may be incomplete",
                                self._page_limit,
                            )
                        return rows
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("fossunited fetch failed: %s", exc)
        return []
