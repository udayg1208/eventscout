"""M5 tests: ConfsTechProvider — normalization, filtering, caching, resilience.

No network: an httpx.MockTransport serves canned Confs.tech JSON, so the real
fetch -> normalize -> filter -> cache path is exercised end to end.
"""

from __future__ import annotations

import asyncio
from datetime import date

import httpx

from app.cache import TTLCache
from app.models.event import EventCategory
from app.models.search import SearchQuery
from app.parsers.keyword import KeywordQueryParser
from app.providers.confstech import ConfsTechProvider, normalize_entry
from app.services.search_service import SearchService


def run(coro):
    return asyncio.run(coro)


INDIA_ENTRIES = [
    {
        "name": "droidCon India",
        "url": "https://india.droidcon.com/",
        "startDate": "2026-11-20",
        "endDate": "2026-11-21",
        "city": "Bengaluru",
        "country": "India",
    },
    {
        "name": "FlutterCon India",
        "url": "https://india.fluttercon.dev/",
        "startDate": "2026-11-21",
        "city": "Bangalore",
        "country": "India",
    },
    {
        "name": "Online AI Summit India",
        "url": "https://ai.example.in/",
        "startDate": "2026-12-01",
        "country": "India",
        "online": True,
    },
]
OTHER_COUNTRY = [
    {
        "name": "US Conf",
        "url": "https://us.example.com/",
        "startDate": "2026-10-01",
        "city": "New York",
        "country": "USA",
    }
]


def _transport(calls: list[str], status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if status != 200:
            return httpx.Response(status)
        if request.url.path.endswith("/2026/general.json"):
            return httpx.Response(200, json=INDIA_ENTRIES + OTHER_COUNTRY)
        return httpx.Response(200, json=[])

    return httpx.MockTransport(handler)


def _provider(calls: list[str], status: int = 200) -> ConfsTechProvider:
    return ConfsTechProvider(transport=_transport(calls, status), ttl_seconds=300, years=[2026])


# --------------------------- normalization ---------------------------


def test_normalize_maps_all_fields():
    event = normalize_entry(INDIA_ENTRIES[0])
    assert event is not None
    assert event.title == "droidCon India"
    assert str(event.url) == "https://india.droidcon.com/"
    assert event.city == "Bengaluru"
    assert event.start_date == date(2026, 11, 20)
    assert event.end_date == date(2026, 11, 21)
    assert event.category == EventCategory.CONFERENCE
    assert event.is_free is None  # source has no price -> honest None
    assert event.description is None
    assert event.provider == "confs.tech"


def test_normalize_online_entry_without_city():
    event = normalize_entry(INDIA_ENTRIES[2])
    assert event is not None
    assert event.is_online is True
    assert event.location == "Online"


def test_normalize_drops_entry_without_date_or_url():
    assert normalize_entry({"name": "x", "url": "https://x.com"}) is None
    assert normalize_entry({"name": "x", "startDate": "2026-01-01"}) is None
    assert normalize_entry({"name": "x", "url": "https://x.com", "startDate": "nope"}) is None


# --------------------------- search / filtering ---------------------------


def test_search_returns_only_india_events():
    provider = _provider([])
    events = run(provider.search(SearchQuery()))
    assert {e.title for e in events} == {
        "droidCon India",
        "FlutterCon India",
        "Online AI Summit India",
    }
    assert all(e.provider == "confs.tech" for e in events)


def test_search_city_filter_normalizes_aliases():
    # M6 closed the alias gap: both "Bangalore" and "Bengaluru" events now match.
    provider = _provider([])
    events = run(provider.search(SearchQuery(city="Bangalore")))
    titles = {e.title for e in events}
    assert "FlutterCon India" in titles  # city == "Bangalore"
    assert "droidCon India" in titles  # city == "Bengaluru", now normalized


def test_search_category_conference_matches_all_but_others_match_none():
    provider = _provider([])
    assert len(run(provider.search(SearchQuery(categories=[EventCategory.CONFERENCE])))) == 3
    assert run(provider.search(SearchQuery(categories=[EventCategory.HACKATHON]))) == []


# --------------------------- caching & resilience ---------------------------


def test_data_is_cached_and_not_refetched():
    calls: list[str] = []
    provider = _provider(calls)
    run(provider.search(SearchQuery()))
    after_first = len(calls)
    run(provider.search(SearchQuery(city="Pune")))
    assert len(calls) == after_first  # second search hit the cache, no refetch


def test_fetch_failure_returns_empty_and_is_not_cached():
    calls: list[str] = []
    provider = _provider(calls, status=500)
    assert run(provider.search(SearchQuery())) == []
    after_first = len(calls)
    assert run(provider.search(SearchQuery())) == []
    assert len(calls) > after_first  # failure not cached -> retried


# --------------------------- SearchService works unchanged (req 7) ---------------------------


def test_search_service_works_with_confstech_provider():
    service = SearchService(
        parser=KeywordQueryParser(),
        provider=_provider([]),
        parse_cache=TTLCache(300),
        results_cache=TTLCache(300),
    )
    outcome = run(service.search("conferences in Bangalore"))
    # City aliases now normalized: both the "Bangalore" and "Bengaluru" conferences match.
    assert {e.title for e in outcome.events} == {"FlutterCon India", "droidCon India"}
    assert outcome.query.city == "Bangalore"
    assert outcome.query.categories == [EventCategory.CONFERENCE]
