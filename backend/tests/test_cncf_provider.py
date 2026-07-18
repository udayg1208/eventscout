"""CNCFProvider: normalization, India+upcoming filtering, cache, failure.

The Bevy paging/stop logic is shared (bevy.py) and covered by the GDG tests; here
we verify the CNCF-specific wiring (host, provider name, category) and behavior.
"""

from __future__ import annotations

import asyncio
from datetime import date

import httpx

from app.models.event import EventCategory
from app.models.search import SearchQuery
from app.providers.cncf import CNCFProvider, normalize_event

TODAY = date(2026, 7, 14)


def run(coro):
    return asyncio.run(coro)


PAGE1 = [
    {
        "title": "KCD Gujarat 2026",
        "url": "https://community2.cncf.io/e/kcd-guj/",
        "start_date": "2026-09-19T09:00:00+05:30",
        "chapter": {"city": "Ahmedabad", "country": "IN", "country_name": "India"},
    },
    {
        "title": "KubeCon EU",
        "url": "https://community2.cncf.io/e/kceu/",
        "start_date": "2026-08-01T09:00:00+02:00",
        "chapter": {"city": "Amsterdam", "country": "NL"},
    },
    {
        "title": "KCD Bengaluru 2025 (past)",
        "url": "https://community2.cncf.io/e/kcd-blr/",
        "start_date": "2025-06-07T09:00:00+05:30",
        "chapter": {"city": "Bengaluru", "country": "IN"},
    },
]


def _transport(calls: list[str], status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params.get("page"))
        if status != 200:
            return httpx.Response(status)
        data = PAGE1 if request.url.params.get("page") == "1" else []
        return httpx.Response(200, json={"results": data})

    return httpx.MockTransport(handler)


def _provider(calls: list[str], status: int = 200) -> CNCFProvider:
    return CNCFProvider(transport=_transport(calls, status), ttl_seconds=300, today=TODAY)


def test_normalize_sets_cncf_provider_and_meetup_category():
    event = normalize_event(PAGE1[0])
    assert event is not None
    assert event.provider == "cncf"
    assert event.category == EventCategory.MEETUP
    assert event.city == "Ahmedabad"
    assert event.start_date == date(2026, 9, 19)
    assert event.is_free is None


def test_search_returns_india_upcoming_only():
    events = run(_provider([]).search(SearchQuery()))
    # KubeCon EU (NL) excluded; KCD Bengaluru 2025 (past) excluded.
    assert {e.title for e in events} == {"KCD Gujarat 2026"}
    assert all(e.provider == "cncf" for e in events)


def test_data_is_cached_between_searches():
    calls: list[str] = []
    provider = _provider(calls)
    run(provider.search(SearchQuery()))
    after_first = len(calls)
    run(provider.search(SearchQuery(city="Ahmedabad")))
    assert len(calls) == after_first


def test_fetch_failure_returns_empty_and_not_cached():
    calls: list[str] = []
    provider = _provider(calls, status=500)
    assert run(provider.search(SearchQuery())) == []
    after_first = len(calls)
    assert run(provider.search(SearchQuery())) == []
    assert len(calls) > after_first
