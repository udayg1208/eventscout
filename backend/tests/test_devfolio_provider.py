"""DevfolioProvider: normalization, filtering, caching, resilience."""

from __future__ import annotations

import asyncio
import json
from datetime import date

import httpx

from app.models.event import EventCategory
from app.models.search import SearchQuery
from app.providers.devfolio import DevfolioProvider, normalize_hackathon


def run(coro):
    return asyncio.run(coro)


HACKATHON = {
    "name": "Build with Gemma",
    "slug": "build-with-gemma",
    "country": "India",
    "city": "Bengaluru",
    "is_online": False,
    "starts_at": "2026-07-18T03:30:00+00:00",
    "ends_at": "2026-07-18T15:00:00+00:00",
    "desc": "A one-day   in-person   hackathon.",
    "uuid": "u1",
    "hackathon_setting": {"subdomain": "build-with-gemma"},
}
ONLINE_HACKATHON = {
    "name": "Online Sprint",
    "slug": "online-sprint",
    "country": "India",
    "is_online": True,
    "starts_at": "2026-08-01T05:00:00+00:00",
    "uuid": "u2",
    "hackathon_setting": {"subdomain": "online-sprint"},
}
FOREIGN = {
    "name": "US Hack",
    "slug": "us-hack",
    "country": "USA",
    "starts_at": "2026-09-01T05:00:00+00:00",
    "uuid": "u3",
    "hackathon_setting": {"subdomain": "us-hack"},
}


def _transport(calls, status=200):
    def handler(request):
        calls.append(str(request.url))
        if status != 200:
            return httpx.Response(status)
        body = json.loads(request.content)
        if body.get("type") == "application_open":
            hits = [{"_source": h} for h in (HACKATHON, ONLINE_HACKATHON, FOREIGN)]
        else:
            hits = []
        return httpx.Response(200, json={"hits": {"hits": hits}})

    return httpx.MockTransport(handler)


def _provider(calls, status=200):
    return DevfolioProvider(transport=_transport(calls, status), ttl_seconds=300)


# --------------------------- normalization ---------------------------


def test_normalize_maps_fields():
    event = normalize_hackathon(HACKATHON)
    assert event is not None
    assert event.title == "Build with Gemma"
    assert str(event.url) == "https://build-with-gemma.devfolio.co/"
    assert event.category == EventCategory.HACKATHON
    assert event.is_free is True
    assert event.city == "Bangalore"  # Bengaluru normalized
    assert event.start_date == date(2026, 7, 18)  # UTC 03:30 -> IST 09:00 same day
    assert event.description == "A one-day in-person hackathon."  # whitespace collapsed


def test_normalize_online_and_missing_fields():
    online = normalize_hackathon(ONLINE_HACKATHON)
    assert online is not None and online.is_online is True and online.location == "Online"
    assert normalize_hackathon({"name": "x"}) is None  # no subdomain/date


# --------------------------- search / filtering ---------------------------


def test_search_returns_india_hackathons_only():
    events = run(_provider([]).search(SearchQuery()))
    assert {e.title for e in events} == {"Build with Gemma", "Online Sprint"}
    assert all(e.category == EventCategory.HACKATHON for e in events)


def test_search_filters_by_category_and_city():
    provider = _provider([])
    assert run(provider.search(SearchQuery(categories=[EventCategory.HACKATHON])))
    assert run(provider.search(SearchQuery(categories=[EventCategory.WORKSHOP]))) == []
    bangalore = run(provider.search(SearchQuery(city="Bangalore")))
    assert {e.title for e in bangalore} == {"Build with Gemma"}


# --------------------------- caching & resilience ---------------------------


def test_data_cached_between_searches():
    calls: list[str] = []
    provider = _provider(calls)
    run(provider.search(SearchQuery()))
    after_first = len(calls)
    run(provider.search(SearchQuery(city="Bangalore")))
    assert len(calls) == after_first


def test_fetch_failure_returns_empty_and_not_cached():
    calls: list[str] = []
    provider = _provider(calls, status=500)
    assert run(provider.search(SearchQuery())) == []
    after_first = len(calls)
    assert run(provider.search(SearchQuery())) == []
    assert len(calls) > after_first
