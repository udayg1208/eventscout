"""Confs.tech provider — the first production event source.

Promoted from the validated M2.5 spike. Fetches the open, keyless Confs.tech
conference dataset (GitHub JSON), normalizes India entries into our Event model,
and filters by the SearchQuery.

Notes:
- Confs.tech only lists conferences, so every event is category=CONFERENCE. It
  carries no price/description, so those map to honest None (never fabricated).
- The upstream dataset is query-independent and near-static, so fetched events are
  held in a short-TTL cache (reusing TTLCache) and filtered in memory per query.
  Empty/failed loads are NOT cached, so an upstream outage self-heals.
- City-alias normalization (Bengaluru vs Bangalore) is intentionally deferred to M6.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

import httpx
from pydantic import ValidationError

from app.cache import TTLCache
from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.base import EventProvider
from app.providers.filtering import matches

logger = logging.getLogger(__name__)

PROVIDER_NAME = "confs.tech"
RAW_BASE = "https://raw.githubusercontent.com/tech-conferences/conference-data/main/conferences"
TOPICS = [
    "general",
    "data",
    "python",
    "javascript",
    "devops",
    "security",
    "leadership",
    "product",
    "ux",
    "golang",
    "java",
    "rust",
    "php",
    "ruby",
    "dotnet",
    "android",
    "ios",
    "graphql",
    "agile",
    "scala",
]
_CACHE_KEY = "confstech:india"
_DATA_TTL_SECONDS = 3600  # dataset changes infrequently


def normalize_entry(entry: dict) -> Event | None:
    """Map one Confs.tech entry into an Event, or None if it can't be used."""
    start_raw = entry.get("startDate")
    name = entry.get("name")
    url = entry.get("url")
    if not start_raw or not name or not url:
        return None
    try:
        start = date.fromisoformat(start_raw)
    except ValueError:
        return None

    end_raw = entry.get("endDate")
    end: date | None = None
    if end_raw and end_raw != start_raw:
        try:
            end = date.fromisoformat(end_raw)
        except ValueError:
            end = None

    city = entry.get("city")
    country = entry.get("country")
    is_online = bool(entry.get("online", False))
    if is_online and not city:
        location = "Online"
    else:
        location = ", ".join(p for p in (city, country) if p) or None

    try:
        return Event(
            title=name,
            description=None,
            url=url,
            city=city,
            location=location,
            is_online=is_online,
            start_date=start,
            end_date=end,
            category=EventCategory.CONFERENCE,
            is_free=None,
            price=None,
            provider=PROVIDER_NAME,
        )
    except ValidationError:
        return None


class ConfsTechProvider(EventProvider):
    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        ttl_seconds: float = _DATA_TTL_SECONDS,
        transport: httpx.BaseTransport | None = None,
        base_url: str = RAW_BASE,
        topics: list[str] | None = None,
        years: list[int] | None = None,
    ) -> None:
        self._cache: TTLCache[str, list[Event]] = TTLCache(ttl_seconds)
        self._transport = transport  # injected in tests (httpx.MockTransport)
        self._base = base_url
        self._topics = topics or TOPICS
        self._years = years or [date.today().year, date.today().year + 1]

    async def search(self, query: SearchQuery) -> list[Event]:
        events = self._cache.get(_CACHE_KEY)
        if events is None:
            events = await self._load()
            if events:  # never cache an empty/failed load
                self._cache.set(_CACHE_KEY, events)
        return [event for event in events if matches(event, query)]

    async def _load(self) -> list[Event]:
        raw = await self._fetch_india_entries()
        normalized = [event for entry in raw if (event := normalize_entry(entry)) is not None]
        logger.info(
            "confs.tech: loaded %d India events (%d raw entries)",
            len(normalized),
            len(raw),
        )
        return normalized

    async def _fetch_india_entries(self) -> list[dict]:
        urls = [
            f"{self._base}/{year}/{topic}.json" for year in self._years for topic in self._topics
        ]
        async with httpx.AsyncClient(transport=self._transport, timeout=15.0) as client:
            results = await asyncio.gather(*(self._get(client, url) for url in urls))

        seen: set[str] = set()
        merged: list[dict] = []
        for data in results:
            for entry in data:
                url = entry.get("url", "")
                if entry.get("country") == "India" and url and url not in seen:
                    seen.add(url)
                    merged.append(entry)
        return merged

    async def _get(self, client: httpx.AsyncClient, url: str) -> list[dict]:
        try:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    return data
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("confs.tech fetch failed for %s: %s", url, exc)
        return []
