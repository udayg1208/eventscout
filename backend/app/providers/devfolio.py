"""Devfolio provider — India hackathons.

Source: Devfolio's public search API (no key, no auth):
    POST https://api.devfolio.co/api/search/hackathons  {"type": ..., "from": 0, "size": N}
Valid `type` values used here: "application_open", "upcoming".

Normalization notes:
- Every event is category=HACKATHON.
- is_free=True: Devfolio hackathons are free to participate — a property of the
  source, not a fabricated value.
- Cities are canonicalized at this boundary (Bengaluru -> Bangalore).
- Cached like ConfsTech (short TTL, reusing TTLCache); empty/failed loads not cached.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta

import httpx
from pydantic import ValidationError

from app.cache import TTLCache
from app.city import normalize_city
from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.base import EventProvider
from app.providers.filtering import matches

logger = logging.getLogger(__name__)

PROVIDER_NAME = "devfolio"
DEVFOLIO_URL = "https://api.devfolio.co/api/search/hackathons"
_TYPES = ["application_open", "upcoming"]
_CACHE_KEY = "devfolio:india"
_DATA_TTL_SECONDS = 1800
_IST_OFFSET = timedelta(hours=5, minutes=30)


def _ist_date(iso: str) -> date:
    """Parse an ISO timestamp (UTC) and return the India-local calendar date."""
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC) + _IST_OFFSET
    return dt.date()


def normalize_hackathon(source: dict) -> Event | None:
    """Map one Devfolio `_source` record into an Event, or None if unusable."""
    name = source.get("name")
    setting = source.get("hackathon_setting") or {}
    subdomain = setting.get("subdomain") or source.get("slug")
    starts = source.get("starts_at")
    if not name or not subdomain or not starts:
        return None
    try:
        start = _ist_date(starts)
    except ValueError:
        return None

    end: date | None = None
    ends = source.get("ends_at")
    if ends:
        try:
            candidate = _ist_date(ends)
            if candidate != start:
                end = candidate
        except ValueError:
            end = None

    is_online = bool(source.get("is_online", False))
    location = source.get("location") or ("Online" if is_online else None)
    description = source.get("desc") or source.get("tagline")
    if description:
        description = " ".join(description.split())[:300]

    try:
        return Event(
            title=name,
            description=description,
            url=f"https://{subdomain}.devfolio.co",
            city=normalize_city(source.get("city")),
            location=location,
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


class DevfolioProvider(EventProvider):
    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        ttl_seconds: float = _DATA_TTL_SECONDS,
        transport: httpx.BaseTransport | None = None,
        url: str = DEVFOLIO_URL,
        types: list[str] | None = None,
        page_size: int = 50,
    ) -> None:
        self._cache: TTLCache[str, list[Event]] = TTLCache(ttl_seconds)
        self._transport = transport
        self._url = url
        self._types = types or _TYPES
        self._page_size = page_size

    async def search(self, query: SearchQuery) -> list[Event]:
        events = self._cache.get(_CACHE_KEY)
        if events is None:
            events = await self._load()
            if events:
                self._cache.set(_CACHE_KEY, events)
        return [event for event in events if matches(event, query)]

    async def _load(self) -> list[Event]:
        raw = await self._fetch_india_hackathons()
        normalized = [event for src in raw if (event := normalize_hackathon(src)) is not None]
        logger.info("devfolio: loaded %d India hackathons (%d raw)", len(normalized), len(raw))
        return normalized

    async def _fetch_india_hackathons(self) -> list[dict]:
        async with httpx.AsyncClient(transport=self._transport, timeout=15.0) as client:
            results = await asyncio.gather(*(self._fetch_type(client, t) for t in self._types))
        seen: set[str] = set()
        merged: list[dict] = []
        for hits in results:
            for hit in hits:
                source = hit.get("_source", {})
                uuid = source.get("uuid", "")
                if source.get("country") == "India" and uuid and uuid not in seen:
                    seen.add(uuid)
                    merged.append(source)
        return merged

    async def _fetch_type(self, client: httpx.AsyncClient, type_: str) -> list[dict]:
        try:
            response = await client.post(
                self._url, json={"type": type_, "from": 0, "size": self._page_size}
            )
            if response.status_code == 200:
                data = response.json()
                hits = data.get("hits", {}).get("hits", [])
                if isinstance(hits, list):
                    return hits
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("devfolio fetch failed for type=%s: %s", type_, exc)
        return []
