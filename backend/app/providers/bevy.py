"""Shared base for Bevy-platform community event sources (GDG, CNCF, ...).

These sites expose an identical JSON API with no server-side country/date filter:
    GET <base>/api/event/?status=Published&order_by=-start_date&per_page=N&page=P

So we page in descending start_date order, keep India + upcoming events, and stop
once a page's oldest event is already past (every later page is older). A hard page
cap bounds the work and is logged if hit (no silent truncation).

Subclasses set `name`, `base_url`, `cache_key`, and `category`. All other behavior —
fetch, paginate, normalize, filter, cache — is shared here (no duplication).
"""

from __future__ import annotations

import logging
from datetime import date

import httpx
from pydantic import ValidationError

from app.cache import TTLCache
from app.city import normalize_city
from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.base import EventProvider
from app.providers.filtering import matches

logger = logging.getLogger(__name__)

_DATA_TTL_SECONDS = 3600
_MAX_PAGES = 5
_PAGE_SIZE = 500


def normalize_bevy_event(
    entry: dict, *, provider_name: str, category: EventCategory
) -> Event | None:
    """Map one Bevy event record into an Event, or None if unusable.

    The list API exposes no description, price, or online flag, so those stay
    None / False (never inferred). Location comes from the event's `chapter`.
    """
    title = entry.get("title")
    url = entry.get("url")
    start_raw = entry.get("start_date")
    if not title or not url or not start_raw:
        return None
    try:
        # The ISO string carries the event's local offset; its date portion is the
        # local calendar date — take it directly to avoid timezone drift.
        start = date.fromisoformat(start_raw[:10])
    except ValueError:
        return None

    end: date | None = None
    end_raw = entry.get("end_date")
    if end_raw:
        try:
            candidate = date.fromisoformat(end_raw[:10])
            if candidate != start:
                end = candidate
        except ValueError:
            end = None

    chapter = entry.get("chapter") or {}
    country_name = chapter.get("country_name") or "India"
    location = (
        chapter.get("chapter_location")
        or ", ".join(p for p in (chapter.get("city"), country_name) if p)
        or None
    )

    try:
        return Event(
            title=title,
            description=None,
            url=url,
            city=normalize_city(chapter.get("city")),
            location=location,
            is_online=False,
            start_date=start,
            end_date=end,
            category=category,
            is_free=None,
            price=None,
            provider=provider_name,
        )
    except ValidationError:
        return None


class BevyEventProvider(EventProvider):
    # Subclasses override these:
    name = "bevy"
    base_url = ""
    cache_key = "bevy:india-upcoming"
    category = EventCategory.MEETUP

    def __init__(
        self,
        *,
        ttl_seconds: float = _DATA_TTL_SECONDS,
        transport: httpx.BaseTransport | None = None,
        url: str | None = None,
        max_pages: int = _MAX_PAGES,
        page_size: int = _PAGE_SIZE,
        today: date | None = None,
    ) -> None:
        self._cache: TTLCache[str, list[Event]] = TTLCache(ttl_seconds)
        self._transport = transport
        self._url = url or self.base_url
        self._max_pages = max_pages
        self._page_size = page_size
        self._today = today

    async def search(self, query: SearchQuery) -> list[Event]:
        events = self._cache.get(self.cache_key)
        if events is None:
            events = await self._load()
            if events:
                self._cache.set(self.cache_key, events)
        return [event for event in events if matches(event, query)]

    async def _load(self) -> list[Event]:
        raw = await self._fetch_upcoming_india()
        normalized = [
            event
            for entry in raw
            if (
                event := normalize_bevy_event(
                    entry, provider_name=self.name, category=self.category
                )
            )
            is not None
        ]
        logger.info(
            "%s: loaded %d upcoming India events (%d raw)",
            self.name,
            len(normalized),
            len(raw),
        )
        return normalized

    async def _fetch_upcoming_india(self) -> list[dict]:
        today = (self._today or date.today()).isoformat()
        collected: list[dict] = []
        async with httpx.AsyncClient(transport=self._transport, timeout=15.0) as client:
            for page in range(1, self._max_pages + 1):
                results = await self._fetch_page(client, page)
                if not results:
                    break
                for entry in results:
                    chapter = entry.get("chapter") or {}
                    start = (entry.get("start_date") or "")[:10]
                    if chapter.get("country") == "IN" and start >= today:
                        collected.append(entry)
                # Descending order: once the oldest event on this page is in the
                # past, every later page is older too — stop.
                page_oldest = (results[-1].get("start_date") or "")[:10]
                if page_oldest and page_oldest < today:
                    break
            else:
                logger.warning(
                    "%s: hit page cap (%d); results may be incomplete",
                    self.name,
                    self._max_pages,
                )
        return collected

    async def _fetch_page(self, client: httpx.AsyncClient, page: int) -> list[dict]:
        try:
            response = await client.get(
                self._url,
                params={
                    "status": "Published",
                    "order_by": "-start_date",
                    "per_page": self._page_size,
                    "page": page,
                },
                headers={"Accept": "application/json"},
            )
            if response.status_code == 200:
                results = response.json().get("results", [])
                if isinstance(results, list):
                    return results
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("%s fetch failed for page=%s: %s", self.name, page, exc)
        return []
