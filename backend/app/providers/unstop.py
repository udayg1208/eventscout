"""Unstop provider — India hackathons, workshops, conferences & tech competitions (Phase 11A).

Source: Unstop's public opportunity API (no key, no auth):
    GET https://unstop.com/api/public/opportunity/search-result
        ?opportunity=<type>&oppstatus=open&page=P
    -> data.data[]  (each: title, seo_url, region, start_date/end_date in IST, organisation, status)

Unstop is India's largest student/tech competition platform. We pull the *open* (registration-open)
listings across the event-like opportunity types — hackathons, workshops, conferences, and
competitions — because those are the actionable, upcoming events (the default feed mixes in years
of closed listings). Competitions are the noisiest type, so they are kept only when the title is a
tech/engineering event (keyword gate); the other types pass through. Normalization is honest: dates
come straight from the feed (IST calendar date), online/offline from `region`, the host org becomes
the display location, and price/description stay None (the list API carries neither — never
fabricated). Upcoming-only, deduped by URL. Page cap logged if hit (no silent truncation).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date

import httpx
from pydantic import ValidationError

from app.cache import TTLCache
from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.base import EventProvider
from app.providers.categorize import category_from_title
from app.providers.filtering import matches

logger = logging.getLogger(__name__)

PROVIDER_NAME = "unstop"
UNSTOP_URL = "https://unstop.com/api/public/opportunity/search-result"
_CACHE_KEY = "unstop:india"
_DATA_TTL_SECONDS = 3600
_PER_PAGE = 30
_MAX_PAGES = 40  # per type; the default feed mixes closed listings, so we scan then early-stop
_EMPTY_STREAK = 4  # stop a type after this many pages with no new upcoming event
_CLOSED = {"CLOSED", "EXPIRED", "REGISTRATION_CLOSED"}

# Keep a broad "competition" only if its title reads as a real tech/engineering event.
_TECH = (
    "ai",
    "ml",
    "machine learning",
    "deep learning",
    "data",
    "analytics",
    "code",
    "coding",
    "hack",
    "dev",
    "developer",
    "tech",
    "robot",
    "cyber",
    "cloud",
    "web",
    "app ",
    "software",
    "engineer",
    "innovation",
    "programming",
    "blockchain",
    "iot",
    "design",
    "ux",
    "ui",
    "product",
    "gen ai",
    "genai",
    "llm",
    "python",
    "java",
    "startup",
    "quantum",
    "devops",
)


@dataclass(frozen=True)
class _Kind:
    opportunity: str
    category: EventCategory
    tech_gated: bool = False


# The event-like opportunity types on Unstop, with their default category.
_KINDS: tuple[_Kind, ...] = (
    _Kind("hackathons", EventCategory.HACKATHON),
    _Kind("workshops", EventCategory.WORKSHOP),
    _Kind("conferences", EventCategory.CONFERENCE),
    _Kind("competitions", EventCategory.HACKATHON, tech_gated=True),
)


def _date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _is_tech(title: str) -> bool:
    low = title.lower()
    return any(k in low for k in _TECH)


def _upcoming(item: dict, today: date) -> bool:
    """True if the item's anchor date (deadline, else start) is today or later."""
    anchor = _date(item.get("end_date")) or _date(item.get("start_date"))
    return anchor is not None and anchor >= today


def normalize_opportunity(item: dict, kind: _Kind) -> Event | None:
    """Map one Unstop opportunity into an Event, or None if unusable (never fabricates)."""
    title = item.get("title")
    url = item.get("seo_url")
    if not title or not url:
        return None
    if (item.get("status") or "").upper() in _CLOSED:
        return None
    if kind.tech_gated and not _is_tech(title):
        return None

    start = _date(item.get("start_date"))
    end = _date(item.get("end_date"))
    anchor = start or end  # many listings expose only the deadline (end_date)
    if anchor is None:
        return None
    start = start or anchor
    end = end if (end and end != start) else None

    region = (item.get("region") or "").lower()
    is_online = region == "online"
    org = (item.get("organisation") or {}).get("name")

    try:
        return Event(
            title=title,
            description=None,
            url=url,
            city=None,  # the list API carries no city; do not infer one
            location="Online" if is_online else (org or None),
            is_online=is_online,
            start_date=start,
            end_date=end,
            category=category_from_title(title, default=kind.category),
            is_free=None,
            price=None,
            provider=PROVIDER_NAME,
        )
    except ValidationError:
        return None


class UnstopProvider(EventProvider):
    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        ttl_seconds: float = _DATA_TTL_SECONDS,
        transport: httpx.BaseTransport | None = None,
        base_url: str = UNSTOP_URL,
        kinds: tuple[_Kind, ...] = _KINDS,
        max_pages: int = _MAX_PAGES,
        per_page: int = _PER_PAGE,
        today: date | None = None,
    ) -> None:
        self._cache: TTLCache[str, list[Event]] = TTLCache(ttl_seconds)
        self._transport = transport
        self._base = base_url
        self._kinds = kinds
        self._max_pages = max_pages
        self._per_page = per_page
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
            transport=self._transport, timeout=20.0, follow_redirects=True
        ) as client:
            batches = await asyncio.gather(
                *(self._fetch_kind(client, kind) for kind in self._kinds)
            )

        seen: set[str] = set()
        events: list[Event] = []
        for kind, raw in zip(self._kinds, batches, strict=True):
            for item in raw:
                event = normalize_opportunity(item, kind)
                if event is None:
                    continue
                key = str(event.url)
                if key in seen or (event.end_date or event.start_date) < today:
                    continue
                seen.add(key)
                events.append(event)
        logger.info(
            "unstop: loaded %d upcoming events across %d types", len(events), len(self._kinds)
        )
        return events

    async def _fetch_kind(self, client: httpx.AsyncClient, kind: _Kind) -> list[dict]:
        """Scan a type's feed, keeping upcoming listings; stop once pages stop adding new ones.

        The default feed is not date-ordered (it mixes years of closed listings), so we page and
        early-stop after `_EMPTY_STREAK` consecutive pages contribute no new upcoming event —
        bounding the work without silently truncating a live tail."""
        today = self._today or date.today()
        collected: list[dict] = []
        empty = 0
        for page in range(1, self._max_pages + 1):
            items = await self._fetch_page(client, kind.opportunity, page)
            if not items:
                break
            fresh = [it for it in items if _upcoming(it, today)]
            collected.extend(fresh)
            empty = 0 if fresh else empty + 1
            if empty >= _EMPTY_STREAK:
                break
        else:
            logger.warning("unstop: %s hit page cap (%d)", kind.opportunity, self._max_pages)
        return collected

    async def _fetch_page(
        self, client: httpx.AsyncClient, opportunity: str, page: int
    ) -> list[dict]:
        try:
            response = await client.get(
                self._base,
                params={
                    "opportunity": opportunity,
                    "per_page": self._per_page,
                    "page": page,
                },
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            )
            if response.status_code == 200:
                data = (response.json().get("data") or {}).get("data")
                if isinstance(data, list):
                    return data
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("unstop fetch failed (%s p%s): %s", opportunity, page, exc)
        return []
