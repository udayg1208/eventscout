"""DevpostProvider: period parsing, open-state filter, online/city detection, cache, failure."""

from __future__ import annotations

import asyncio
from datetime import date

import httpx

from app.models.event import EventCategory
from app.models.search import SearchQuery
from app.providers.devpost import DevpostProvider, _parse_period, normalize_hackathon

HACK = {
    "title": "AI Hack India",
    "url": "https://aihack.devpost.com/",
    "open_state": "open",
    "submission_period_dates": "Jul 15 - Aug 15, 2026",
    "displayed_location": {"icon": "map-marker-alt", "location": "VITM, Indore"},
}
ONLINE = {
    "title": "Global Online Hack",
    "url": "https://g.devpost.com/",
    "open_state": "upcoming",
    "submission_period_dates": "Aug 01 - 10, 2026",
    "displayed_location": {"icon": "globe", "location": "Online"},
}
BLR = {
    "title": "Bengaluru Buildathon",
    "url": "https://blr.devpost.com/",
    "open_state": "open",
    "submission_period_dates": "Sep 05 - 06, 2026",
    "displayed_location": {"icon": "map-marker-alt", "location": "Bengaluru, India"},
}


def run(coro):
    return asyncio.run(coro)


# --------------------------- period parsing ---------------------------


def test_parse_period_cross_month_and_same_month():
    assert _parse_period("Jul 15 - Aug 15, 2026") == (date(2026, 7, 15), date(2026, 8, 15))
    assert _parse_period("Jul 03 - 31, 2026") == (date(2026, 7, 3), date(2026, 7, 31))


def test_parse_period_single_day_end_is_none():
    assert _parse_period("Jul 20 - 20, 2026") == (date(2026, 7, 20), None)


def test_parse_period_garbage():
    assert _parse_period("coming soon") == (None, None)


# --------------------------- normalization ---------------------------


def test_normalize_maps_fields():
    event = normalize_hackathon(HACK)
    assert event is not None
    assert event.title == "AI Hack India"
    assert str(event.url) == "https://aihack.devpost.com/"  # pydantic normalizes host-only URL
    assert event.category == EventCategory.HACKATHON
    assert event.is_free is True  # platform property
    assert event.start_date == date(2026, 7, 15)
    assert event.end_date == date(2026, 8, 15)
    assert event.is_online is False
    assert event.city is None  # Indore not a canonical city → honest None


def test_normalize_online_and_city_detection():
    online = normalize_hackathon(ONLINE)
    assert online.is_online is True and online.location == "Online"
    assert normalize_hackathon(BLR).city == "Bangalore"


def test_normalize_rejects_closed_and_bad_dates():
    assert normalize_hackathon({**HACK, "open_state": "ended"}) is None
    assert normalize_hackathon({**HACK, "submission_period_dates": "soon"}) is None
    assert normalize_hackathon({"title": "x"}) is None


# --------------------------- search / pagination / cache / failure ---------------------------


def _transport(pages: dict[str, list], status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page")
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, json={"hackathons": pages.get(page, [])})

    return httpx.MockTransport(handler)


def test_search_pages_until_empty():
    provider = DevpostProvider(
        transport=_transport({"1": [HACK, ONLINE], "2": [BLR]}), ttl_seconds=300
    )
    events = run(provider.search(SearchQuery()))
    assert {e.title for e in events} == {
        "AI Hack India",
        "Global Online Hack",
        "Bengaluru Buildathon",
    }
    assert all(e.category == EventCategory.HACKATHON for e in events)


def test_fetch_failure_returns_empty_and_not_cached():
    provider = DevpostProvider(transport=_transport({}, status=500))
    assert run(provider.search(SearchQuery())) == []
    assert run(provider.search(SearchQuery())) == []  # still tries (not cached)
