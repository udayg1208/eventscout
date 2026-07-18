"""Devpost provider — India-relevant hackathons.

Source: Devpost's public hackathon JSON API (no key, no auth):
    GET https://devpost.com/api/hackathons?search=india&order_by=deadline&page=N

Normalization notes:
- Every event is category=HACKATHON.
- is_free=True: Devpost hackathons are free to enter — a property of the platform, not a
  fabricated value (same stance as Devfolio).
- `submission_period_dates` is a human string ("Jul 15 - Aug 15, 2026") → parsed to dates.
- Cities are recovered from the free-text location via `detect_city` (major cities only);
  unknown locations keep the raw string and a null city.
- Cached like the other providers; empty/failed loads are not cached (self-heal).
"""

from __future__ import annotations

import logging
from datetime import date, datetime

import httpx
from pydantic import ValidationError

from app.cache import TTLCache
from app.city import detect_city
from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.base import EventProvider
from app.providers.filtering import matches

logger = logging.getLogger(__name__)

PROVIDER_NAME = "devpost"
DEVPOST_URL = "https://devpost.com/api/hackathons"
_CACHE_KEY = "devpost:india"
_DATA_TTL_SECONDS = 3600
_MAX_PAGES = 5
_OPEN_STATES = {"open", "upcoming"}


def _parse_period(text: str) -> tuple[date | None, date | None]:
    """Parse Devpost's 'MMM DD - [MMM ]DD, YYYY' submission window into (start, end)."""
    try:
        left, right = (p.strip() for p in text.split(" - ", 1))
        right_main, year = (p.strip() for p in right.rsplit(",", 1))
        start_month, start_day = left.split()[:2]
        parts = right_main.split()
        end_month, end_day = (parts[0], parts[1]) if len(parts) >= 2 else (start_month, parts[0])
        start = datetime.strptime(f"{start_month} {start_day} {year}", "%b %d %Y").date()
        end = datetime.strptime(f"{end_month} {end_day} {year}", "%b %d %Y").date()
        return start, (end if end != start else None)
    except (ValueError, IndexError):
        return None, None


def normalize_hackathon(hack: dict) -> Event | None:
    """Map one Devpost hackathon record into an Event, or None if unusable."""
    title = (hack.get("title") or "").strip()
    url = (hack.get("url") or "").rstrip("/")
    if not title or not url:
        return None
    if hack.get("open_state") not in _OPEN_STATES:
        return None

    start, end = _parse_period(hack.get("submission_period_dates") or "")
    if start is None:
        return None

    loc = hack.get("displayed_location") or {}
    location_text = (loc.get("location") or "").strip()
    is_online = loc.get("icon") == "globe" or location_text.casefold() == "online"

    try:
        return Event(
            title=title,
            description=None,
            url=url,
            city=detect_city(location_text),
            location="Online" if is_online else (location_text or None),
            is_online=is_online,
            start_date=start,
            end_date=end,
            category=EventCategory.HACKATHON,
            is_free=True,
            price=None,
            provider=PROVIDER_NAME,
        )
    except ValidationError:
        return None


class DevpostProvider(EventProvider):
    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        ttl_seconds: float = _DATA_TTL_SECONDS,
        transport: httpx.BaseTransport | None = None,
        url: str = DEVPOST_URL,
        max_pages: int = _MAX_PAGES,
    ) -> None:
        self._cache: TTLCache[str, list[Event]] = TTLCache(ttl_seconds)
        self._transport = transport
        self._url = url
        self._max_pages = max_pages

    async def search(self, query: SearchQuery) -> list[Event]:
        events = self._cache.get(_CACHE_KEY)
        if events is None:
            events = await self._load()
            if events:
                self._cache.set(_CACHE_KEY, events)
        return [event for event in events if matches(event, query)]

    async def _load(self) -> list[Event]:
        raw = await self._fetch_india_hackathons()
        normalized = [event for h in raw if (event := normalize_hackathon(h)) is not None]
        logger.info("devpost: loaded %d India hackathons (%d raw)", len(normalized), len(raw))
        return normalized

    async def _fetch_india_hackathons(self) -> list[dict]:
        collected: list[dict] = []
        async with httpx.AsyncClient(transport=self._transport, timeout=15.0) as client:
            for page in range(1, self._max_pages + 1):
                hacks = await self._fetch_page(client, page)
                if not hacks:
                    break
                collected.extend(hacks)
        return collected

    async def _fetch_page(self, client: httpx.AsyncClient, page: int) -> list[dict]:
        try:
            response = await client.get(
                self._url,
                params={"search": "india", "order_by": "deadline", "page": page},
                headers={"Accept": "application/json"},
            )
            if response.status_code == 200:
                hacks = response.json().get("hackathons", [])
                if isinstance(hacks, list):
                    return hacks
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("devpost fetch failed for page=%s: %s", page, exc)
        return []
