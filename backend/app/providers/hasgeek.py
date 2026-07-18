"""Hasgeek provider — India tech conferences & community events.

Hasgeek (The Fifth Elephant, Rootconf, Anthill Inside, community meetups) server-
renders upcoming project URLs on its homepage, and each project page embeds a
schema.org **JSON-LD `Event`** (a stable structured contract). So:

    homepage -> extract project URLs -> fetch each -> parse JSON-LD Event.

Pages without an `Event` block are skipped, so non-event links filter themselves
out. No HTML-structure scraping beyond collecting URLs; the event data comes from
JSON-LD (name, startDate, endDate, location). India-native platform.
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
from app.city import detect_city
from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.base import EventProvider
from app.providers.categorize import category_from_title
from app.providers.filtering import matches

logger = logging.getLogger(__name__)

PROVIDER_NAME = "hasgeek"
HASGEEK_HOME = "https://hasgeek.com/"
HASGEEK_BASE = "https://hasgeek.com"
_CACHE_KEY = "hasgeek:upcoming"
_DATA_TTL_SECONDS = 1800
_MAX_PROJECTS = 40

# Two-segment relative project links (e.g. /fifthelephant/2026/).
_PROJECT_HREF = re.compile(r'href="(/[a-z0-9][\w.-]*/[a-z0-9][\w.-]*/)"', re.I)
_LDJSON = re.compile(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.S)


def extract_project_paths(html: str) -> list[str]:
    seen: set[str] = set()
    paths: list[str] = []
    for match in _PROJECT_HREF.finditer(html):
        path = match.group(1)
        if path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def parse_event_ldjson(html: str) -> dict | None:
    for match in _LDJSON.finditer(html):
        try:
            obj = json.loads(match.group(1))
        except ValueError:
            continue
        for item in obj if isinstance(obj, list) else [obj]:
            if isinstance(item, dict) and item.get("@type") == "Event":
                return item
    return None


def normalize_event(ld: dict, path: str) -> Event | None:
    """Map a JSON-LD Event (+ its project path) into an Event, or None."""
    name = ld.get("name")
    start_raw = ld.get("startDate")
    if not name or not start_raw:
        return None
    try:
        start = date.fromisoformat(start_raw[:10])
    except ValueError:
        return None

    end: date | None = None
    end_raw = ld.get("endDate")
    if end_raw:
        try:
            candidate = date.fromisoformat(end_raw[:10])
            if candidate != start:
                end = candidate
        except ValueError:
            end = None

    loc = ld.get("location")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    venue = None
    city_text = None
    is_online = False
    if isinstance(loc, dict):
        venue = loc.get("name")
        if loc.get("@type") == "VirtualLocation":
            is_online = True
        address = loc.get("address")
        if isinstance(address, dict):
            city_text = address.get("addressLocality")
    elif isinstance(loc, str):
        venue = loc
    if str(ld.get("eventAttendanceMode", "")).endswith("OnlineEventAttendanceMode"):
        is_online = True

    description = ld.get("description")
    if description:
        description = " ".join(description.split())[:300]

    try:
        return Event(
            title=name,
            description=description,
            url=f"{HASGEEK_BASE}{path}",
            city=detect_city(city_text, venue, name),
            location=venue,
            is_online=is_online,
            start_date=start,
            end_date=end,
            category=category_from_title(name, default=EventCategory.CONFERENCE),
            is_free=None,
            price=None,
            provider=PROVIDER_NAME,
        )
    except ValidationError:
        return None


class HasgeekProvider(EventProvider):
    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        ttl_seconds: float = _DATA_TTL_SECONDS,
        transport: httpx.BaseTransport | None = None,
        home_url: str = HASGEEK_HOME,
        max_projects: int = _MAX_PROJECTS,
        today: date | None = None,
    ) -> None:
        self._cache: TTLCache[str, list[Event]] = TTLCache(ttl_seconds)
        self._transport = transport
        self._home_url = home_url
        self._max_projects = max_projects
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
        pages = await self._fetch_pages()
        events: list[Event] = []
        for path, html in pages:
            if not html:
                continue
            ld = parse_event_ldjson(html)
            if ld is None:
                continue
            event = normalize_event(ld, path)
            # Keep genuinely upcoming events (drops stale CFP windows).
            if event is not None and (event.end_date or event.start_date) >= today:
                events.append(event)
        logger.info(
            "hasgeek: loaded %d upcoming events (%d project pages)", len(events), len(pages)
        )
        return events

    async def _fetch_pages(self) -> list[tuple[str, str | None]]:
        async with httpx.AsyncClient(
            transport=self._transport, timeout=15.0, follow_redirects=True
        ) as client:
            home = await self._get(client, self._home_url)
            if home is None:
                return []
            paths = extract_project_paths(home)[: self._max_projects]
            htmls = await asyncio.gather(*(self._get(client, f"{HASGEEK_BASE}{p}") for p in paths))
        return list(zip(paths, htmls, strict=True))

    async def _get(self, client: httpx.AsyncClient, url: str) -> str | None:
        try:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if response.status_code == 200:
                return response.text
        except httpx.HTTPError as exc:
            logger.warning("hasgeek fetch failed for %s: %s", url, exc)
        return None
