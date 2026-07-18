"""GDGProvider: normalization, India+upcoming filtering, pagination stop, cache, failure."""

from __future__ import annotations

import asyncio
from datetime import date

import httpx

from app.models.event import EventCategory
from app.models.search import SearchQuery
from app.providers.gdg import GDGProvider, normalize_event

TODAY = date(2026, 7, 14)


def run(coro):
    return asyncio.run(coro)


# Descending start_date order. Page 1 is entirely future; page 2 crosses TODAY.
PAGE1 = [
    {
        "title": "Far US Conf",
        "url": "https://gdg.community.dev/e/us1/",
        "start_date": "2027-01-01T10:00:00-05:00",
        "chapter": {"city": "New York", "country": "US", "country_name": "United States"},
    },
    {
        "title": "GDG Cloud Bengaluru DevFest",
        "url": "https://gdg.community.dev/e/blr1/",
        "start_date": "2026-12-01T10:00:00+05:30",
        "end_date": "2026-12-02T17:00:00+05:30",
        "chapter": {
            "city": "Bengaluru", "country": "IN", "country_name": "India",
            "chapter_location": "Bengaluru (IN)",
        },
    },
    {
        "title": "GDG Pune Meetup",
        "url": "https://gdg.community.dev/e/pune1/",
        "start_date": "2026-11-01T10:00:00+05:30",
        "chapter": {"city": "Pune", "country": "IN"},
    },
]
PAGE2 = [
    {
        "title": "GDG Mumbai AI Day",
        "url": "https://gdg.community.dev/e/mum1/",
        "start_date": "2026-08-01T10:00:00+05:30",
        "chapter": {"city": "Mumbai", "country": "IN"},
    },
    {
        "title": "GDG Delhi Study Jam",
        "url": "https://gdg.community.dev/e/del1/",
        "start_date": "2026-07-20T10:00:00+05:30",
        "chapter": {"city": "New Delhi", "country": "IN"},
    },
    {  # in the past relative to TODAY -> excluded, and triggers the stop
        "title": "GDG Chennai (past)",
        "url": "https://gdg.community.dev/e/che1/",
        "start_date": "2026-06-01T10:00:00+05:30",
        "chapter": {"city": "Chennai", "country": "IN"},
    },
]
PAGE3 = [
    {
        "title": "should never be fetched",
        "url": "https://gdg.community.dev/e/x/",
        "start_date": "2020-01-01T00:00:00Z",
        "chapter": {"country": "IN"},
    }
]


def _transport(calls: list[str], status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page")
        calls.append(page)
        if status != 200:
            return httpx.Response(status)
        data = {"1": PAGE1, "2": PAGE2, "3": PAGE3}.get(page, [])
        return httpx.Response(200, json={"results": data})

    return httpx.MockTransport(handler)


def _provider(calls: list[str], status: int = 200) -> GDGProvider:
    return GDGProvider(transport=_transport(calls, status), ttl_seconds=300, today=TODAY)


# --------------------------- normalization ---------------------------

def test_normalize_maps_fields():
    event = normalize_event(PAGE1[1])
    assert event is not None
    assert event.title == "GDG Cloud Bengaluru DevFest"
    assert event.city == "Bangalore"                 # Bengaluru normalized
    assert event.start_date == date(2026, 12, 1)
    assert event.end_date == date(2026, 12, 2)
    assert event.category == EventCategory.MEETUP     # GDG source property
    assert event.is_free is None                      # not exposed -> honest None
    assert event.description is None
    assert event.provider == "gdg"


def test_normalize_drops_incomplete_records():
    assert normalize_event({"title": "x"}) is None
    assert normalize_event({"title": "x", "url": "https://x", "start_date": "bad"}) is None


# --------------------------- search / filtering ---------------------------

def test_search_returns_india_upcoming_only():
    events = run(_provider([]).search(SearchQuery()))
    assert {e.title for e in events} == {
        "GDG Cloud Bengaluru DevFest",
        "GDG Pune Meetup",
        "GDG Mumbai AI Day",
        "GDG Delhi Study Jam",
    }
    assert all(e.category == EventCategory.MEETUP for e in events)
    assert all(e.provider == "gdg" for e in events)


def test_paging_stops_once_events_go_past_today():
    calls: list[str] = []
    run(_provider(calls).search(SearchQuery()))
    assert calls == ["1", "2"]        # page 3 never fetched (page 2 crossed today)


def test_city_filter_uses_normalization():
    events = run(_provider([]).search(SearchQuery(city="Bangalore")))
    assert {e.title for e in events} == {"GDG Cloud Bengaluru DevFest"}


# --------------------------- cache & failure ---------------------------

def test_data_is_cached_between_searches():
    calls: list[str] = []
    provider = _provider(calls)
    run(provider.search(SearchQuery()))
    after_first = len(calls)
    run(provider.search(SearchQuery(city="Pune")))
    assert len(calls) == after_first


def test_fetch_failure_returns_empty_and_not_cached():
    calls: list[str] = []
    provider = _provider(calls, status=500)
    assert run(provider.search(SearchQuery())) == []
    after_first = len(calls)
    assert run(provider.search(SearchQuery())) == []
    assert len(calls) > after_first
