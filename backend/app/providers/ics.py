"""Generic iCalendar (ICS) provider — one source per feed URL.

The redesign's workhorse: most communities (Meetup groups, Google Calendars, Luma
calendars, university clubs) expose a public **.ics** feed. A single parser handles them
all, and each feed is instantiated as its own provider with its own name, city, category,
health, and refresh interval — the hierarchical "hundreds of small providers" model.

Discovery is not automatable at ₹0 (see spikes/probe_discovery.py), so feeds are supplied
by a curated catalog (`ics_sources.py`); this class is the mechanism, not the list.
"""

from __future__ import annotations

import logging
import re
from datetime import date

import httpx
from pydantic import ValidationError

from app.cache import TTLCache
from app.city import detect_city, normalize_city
from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.base import EventProvider
from app.providers.filtering import matches

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (compatible; EventScout/1.0; +https://eventscout.example)"
_DATE = re.compile(r"(\d{4})(\d{2})(\d{2})")


def _unescape(value: str) -> str:
    return (
        value.replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\n", " ")
        .replace("\\N", " ")
        .strip()
    )


def parse_vevents(ics: str) -> list[dict[str, str]]:
    """Parse VEVENT blocks from an iCalendar document (line-unfolding first)."""
    unfolded = re.sub(r"\r?\n[ \t]", "", ics)
    events: list[dict[str, str]] = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", unfolded, re.DOTALL):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.split(";")[0].upper()] = value.strip()
        events.append(fields)
    return events


def _ics_date(raw: str | None) -> date | None:
    if not raw:
        return None
    match = _DATE.match(raw.strip())
    if not match:
        return None
    try:
        return date(int(match[1]), int(match[2]), int(match[3]))
    except ValueError:
        return None


class ICSProvider(EventProvider):
    """One iCalendar feed → Events. `name`, `city`, `category` come from the source config."""

    def __init__(
        self,
        *,
        name: str,
        ics_url: str,
        city: str | None = None,
        category: EventCategory = EventCategory.MEETUP,
        transport: httpx.BaseTransport | None = None,
        ttl_seconds: float = 3600,
    ) -> None:
        self.name = name
        self._url = ics_url
        self._city = normalize_city(city)
        self._category = category
        self._transport = transport
        self._cache: TTLCache[str, list[Event]] = TTLCache(ttl_seconds)

    async def search(self, query: SearchQuery) -> list[Event]:
        events = self._cache.get(self.name)
        if events is None:
            events = await self._load()
            if events:
                self._cache.set(self.name, events)
        return [event for event in events if matches(event, query)]

    async def _load(self) -> list[Event]:
        text = await self._fetch()
        events = [e for ve in parse_vevents(text) if (e := self._normalize(ve)) is not None]
        logger.info("%s: loaded %d ICS events", self.name, len(events))
        return events

    async def _fetch(self) -> str:
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=15.0, headers={"User-Agent": _UA}
            ) as client:
                response = await client.get(self._url, follow_redirects=True)
                if response.status_code == 200 and "BEGIN:VEVENT" in response.text:
                    return response.text
        except httpx.HTTPError as exc:
            logger.warning("%s ICS fetch failed: %s", self.name, exc)
        return ""

    def _normalize(self, ve: dict[str, str]) -> Event | None:
        title = _unescape(ve.get("SUMMARY", ""))
        url = ve.get("URL", "").strip()
        start = _ics_date(ve.get("DTSTART"))
        if not title or not url or start is None:
            return None  # url required: it is the per-event identity (no collision)

        end = _ics_date(ve.get("DTEND"))
        if end == start:
            end = None
        location = _unescape(ve.get("LOCATION", "")) or None
        is_online = bool(location and "online" in location.casefold())
        description = _unescape(ve.get("DESCRIPTION", ""))[:300] or None

        try:
            return Event(
                title=title,
                description=description,
                url=url,
                city=self._city or detect_city(location),
                location=location,
                is_online=is_online,
                start_date=start,
                end_date=end,
                category=self._category,
                is_free=None,
                price=None,
                provider=self.name,
            )
        except ValidationError:
            return None
