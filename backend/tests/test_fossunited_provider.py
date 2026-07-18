"""FOSSUnitedProvider: normalization (category/free/city), search, cache, failure."""

from __future__ import annotations

import asyncio
from datetime import date

import httpx

from app.models.event import EventCategory
from app.models.search import SearchQuery
from app.providers.fossunited import FOSSUnitedProvider, normalize_event

TODAY = date(2026, 7, 14)


def run(coro):
    return asyncio.run(coro)


ROWS = [
    {
        "event_name": "FOSS Meetup July",
        "event_type": "Meet Up",
        "event_start_date": "2026-07-25 18:00:00",
        "event_end_date": "2026-07-25 20:00:00",
        "event_location": "Bangalore",
        "chapter_name": "FOSS United Bangalore",
        "route": "c/bangalore/july",
        "is_paid_event": 0,
        "event_bio": "A   community   meetup",
    },
    {
        "event_name": "Frappe Workshop",
        "event_type": "Workshop",
        "event_start_date": "2026-08-01 10:00:00",
        "event_location": "NIT Trichy",
        "chapter_name": "NIT",
        "route": "/c/nit/frappe",  # leading slash handled
        "is_paid_event": 1,
    },
    {
        "event_name": "Open Community Call",
        "event_type": "Online",
        "event_start_date": "2026-07-20 18:00:00",
        "event_location": "Virtual",
        "route": "c/org/call",
        "is_paid_event": 0,
    },
    {  # unusable — no route
        "event_name": "Broken",
        "event_type": "Meet Up",
        "event_start_date": "2026-07-30 10:00:00",
        "route": None,
    },
]


def _transport(calls: list[str], status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, json={"data": ROWS})

    return httpx.MockTransport(handler)


def _provider(calls: list[str], status: int = 200) -> FOSSUnitedProvider:
    return FOSSUnitedProvider(transport=_transport(calls, status), ttl_seconds=300, today=TODAY)


# --------------------------- normalization ---------------------------


def test_normalize_meetup_free_with_city():
    event = normalize_event(ROWS[0])
    assert event is not None
    assert event.category == EventCategory.MEETUP
    assert event.is_free is True  # is_paid_event == 0
    assert event.city == "Bangalore"  # detected from location
    assert str(event.url) == "https://fossunited.org/c/bangalore/july"
    assert event.description == "A community meetup"
    assert event.provider == "fossunited"


def test_normalize_workshop_paid_and_slash_route():
    event = normalize_event(ROWS[1])
    assert event is not None
    assert event.category == EventCategory.WORKSHOP
    assert event.is_free is False  # is_paid_event == 1
    assert event.city is None  # "NIT Trichy" has no known city
    assert str(event.url) == "https://fossunited.org/c/nit/frappe"


def test_normalize_online_maps_to_webinar():
    event = normalize_event(ROWS[2])
    assert event is not None
    assert event.category == EventCategory.WEBINAR
    assert event.is_online is True


def test_normalize_drops_row_without_route():
    assert normalize_event(ROWS[3]) is None


# --------------------------- search / filtering ---------------------------


def test_search_returns_all_valid_events():
    events = run(_provider([]).search(SearchQuery()))
    assert {e.title for e in events} == {
        "FOSS Meetup July",
        "Frappe Workshop",
        "Open Community Call",
    }


def test_free_only_excludes_paid_workshop():
    events = run(_provider([]).search(SearchQuery(free_only=True)))
    assert {e.title for e in events} == {"FOSS Meetup July", "Open Community Call"}


def test_category_filter_workshop():
    events = run(_provider([]).search(SearchQuery(categories=[EventCategory.WORKSHOP])))
    assert {e.title for e in events} == {"Frappe Workshop"}


# --------------------------- cache & failure ---------------------------


def test_data_is_cached_between_searches():
    calls: list[str] = []
    provider = _provider(calls)
    run(provider.search(SearchQuery()))
    after_first = len(calls)
    run(provider.search(SearchQuery(free_only=True)))
    assert len(calls) == after_first


def test_fetch_failure_returns_empty_and_not_cached():
    calls: list[str] = []
    provider = _provider(calls, status=500)
    assert run(provider.search(SearchQuery())) == []
    after_first = len(calls)
    assert run(provider.search(SearchQuery())) == []
    assert len(calls) > after_first
