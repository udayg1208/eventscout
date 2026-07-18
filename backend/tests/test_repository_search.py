"""Phase 3E: repository-backed search (the cutover).

Network-free: an in-memory catalog is populated directly, then searched through the
`DatabaseSearchProvider`. Covers filtering, keyword/city/category search, ranking +
determinism, empty results, the bounded candidate window (large-dataset simulation), the
search cache (hit/miss/TTL/invalidation), analytics, latency, and the unchanged
`SearchService` interface — all with zero live-provider fetching.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

from app.cache import TTLCache
from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.parsers.keyword import KeywordQueryParser
from app.providers.ranking import rank
from app.search.analytics import SearchAnalytics
from app.search.cache import InMemorySearchCache, search_cache_key
from app.search.db_provider import DatabaseSearchProvider, to_criteria
from app.services.search_service import SearchService
from app.storage.models import SearchCriteria, StoredEvent
from app.storage.sqlite_repository import SQLiteEventRepository


def run(coro):
    return asyncio.run(coro)


NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
TODAY = date(2026, 7, 15)


def _event(
    title="Event",
    *,
    start=date(2026, 9, 1),
    city="Bangalore",
    category=EventCategory.MEETUP,
    is_free=None,
    description=None,
    url=None,
):
    return Event(
        title=title,
        url=url or f"https://x.example.com/{title.replace(' ', '-').lower()}",
        city=city,
        description=description,
        is_free=is_free,
        start_date=start,
        category=category,
        provider="seed",
    )


def _repo(events=()):
    repo = SQLiteEventRepository()
    if events:
        run(repo.bulk_upsert([StoredEvent.from_event(e, seen_at=NOW) for e in events]))
    return repo


def _provider(repo, *, cache=None, analytics=None, limit=500):
    return DatabaseSearchProvider(
        repo, cache=cache, analytics=analytics, candidate_limit=limit, clock=lambda: TODAY
    )


def _titles(events):
    return [e.title for e in events]


# --------------------------- translation ---------------------------


def test_to_criteria_maps_query_and_scopes_to_upcoming():
    c = to_criteria(
        SearchQuery(city="Pune", categories=[EventCategory.AI], keywords=["ml"], free_only=True),
        today=TODAY,
        limit=50,
    )
    assert c.city == "Pune" and c.categories == [EventCategory.AI]
    assert c.keywords == ["ml"] and c.free_only is True
    assert c.active_only is True and c.upcoming_on_or_after == TODAY and c.limit == 50


# --------------------------- filtering / search ---------------------------


def test_search_returns_events_from_catalog():
    repo = _repo([_event("A"), _event("B")])
    results = run(_provider(repo).search(SearchQuery()))
    assert set(_titles(results)) == {"A", "B"}
    assert all(isinstance(e, Event) for e in results)


def test_filter_by_category():
    repo = _repo(
        [_event("m", category=EventCategory.MEETUP), _event("w", category=EventCategory.WORKSHOP)]
    )
    results = run(_provider(repo).search(SearchQuery(categories=[EventCategory.WORKSHOP])))
    assert _titles(results) == ["w"]


def test_filter_by_city():
    repo = _repo([_event("blr", city="Bangalore"), _event("del", city="Delhi")])
    results = run(_provider(repo).search(SearchQuery(city="Bangalore")))
    assert _titles(results) == ["blr"]


def test_filter_free_only():
    repo = _repo([_event("free", is_free=True), _event("paid", is_free=False), _event("unknown")])
    results = run(_provider(repo).search(SearchQuery(free_only=True)))
    assert _titles(results) == ["free"]


def test_filter_by_date_range():
    repo = _repo(
        [
            _event("early", start=date(2026, 9, 1)),
            _event("mid", start=date(2026, 9, 10)),
            _event("late", start=date(2026, 9, 20)),
        ]
    )
    results = run(
        _provider(repo).search(SearchQuery(date_from=date(2026, 9, 5), date_to=date(2026, 9, 15)))
    )
    assert _titles(results) == ["mid"]


def test_keyword_search():
    repo = _repo([_event("AI Summit"), _event("Cloud Workshop", description="kubernetes")])
    assert _titles(run(_provider(repo).search(SearchQuery(keywords=["ai"])))) == ["AI Summit"]
    assert _titles(run(_provider(repo).search(SearchQuery(keywords=["kubernetes"])))) == [
        "Cloud Workshop"
    ]


def test_empty_result():
    repo = _repo([_event("A", city="Bangalore")])
    assert run(_provider(repo).search(SearchQuery(city="Atlantis"))) == []


def test_past_events_are_never_returned():
    repo = _repo([_event("past", start=date(2020, 1, 1)), _event("future", start=date(2026, 9, 1))])
    assert _titles(run(_provider(repo).search(SearchQuery()))) == ["future"]


# --------------------------- ranking ---------------------------


def test_ranking_is_applied_and_matches_ranker():
    events = [
        _event("Sparse Soon", start=date(2026, 9, 1)),
        _event(
            "Rich Later",
            start=date(2026, 9, 5),
            description="x" * 300,
            is_free=True,
            city="Bangalore",
        ),
    ]
    repo = _repo(events)
    query = SearchQuery()
    candidates = run(repo.search(to_criteria(query, today=TODAY, limit=500))).items
    expected = rank([s.event for s in candidates], query, TODAY)
    results = run(_provider(repo).search(query))  # no cache
    assert results == expected


def test_ranking_is_deterministic():
    events = [_event(f"E{i}", start=date(2026, 9, 1 + i)) for i in range(6)]
    repo = _repo(events)
    provider = _provider(repo)  # no cache
    first = _titles(run(provider.search(SearchQuery())))
    second = _titles(run(provider.search(SearchQuery())))
    assert first == second


# --------------------------- bounded / large dataset ---------------------------


def test_candidate_window_is_bounded_on_large_catalog():
    events = [
        _event(f"E{i}", start=date(2026, 9, 1) + timedelta(days=i % 300)) for i in range(1000)
    ]
    repo = _repo(events)
    results = run(_provider(repo, limit=50).search(SearchQuery()))
    assert len(results) == 50  # bounded window — never loads all 1000
    assert run(repo.count(SearchCriteria())) == 1000  # but the catalog holds them all


# --------------------------- cache ---------------------------


def test_search_cache_hit_and_miss():
    analytics = SearchAnalytics()
    repo = _repo([_event("A")])
    provider = _provider(repo, cache=InMemorySearchCache(60), analytics=analytics)
    run(provider.search(SearchQuery()))  # miss
    run(provider.search(SearchQuery()))  # hit
    assert analytics.cache_hits == 1 and analytics.total_searches == 2


def test_search_cache_invalidation_reflects_new_events():
    repo = _repo([_event("A")])
    provider = _provider(repo, cache=InMemorySearchCache(600))
    assert len(run(provider.search(SearchQuery()))) == 1
    run(repo.bulk_upsert([StoredEvent.from_event(_event("B"), seen_at=NOW)]))
    assert len(run(provider.search(SearchQuery()))) == 1  # still cached (stale)
    run(provider.invalidate())
    assert len(run(provider.search(SearchQuery()))) == 2  # fresh after invalidation


def test_in_memory_cache_ttl_expiry():
    clock = {"t": 1000.0}
    cache = InMemorySearchCache(30, time_fn=lambda: clock["t"])
    run(cache.set("k", [_event("A")]))
    assert run(cache.get("k")) is not None
    clock["t"] += 31
    assert run(cache.get("k")) is None  # expired


def test_search_cache_key_is_order_independent():
    a = search_cache_key(
        SearchQuery(keywords=["b", "a"], categories=[EventCategory.AI, EventCategory.MEETUP])
    )
    b = search_cache_key(
        SearchQuery(keywords=["a", "b"], categories=[EventCategory.MEETUP, EventCategory.AI])
    )
    assert a == b
    assert a != search_cache_key(SearchQuery(city="Pune"))


# --------------------------- analytics ---------------------------


def test_search_analytics_snapshot():
    analytics = SearchAnalytics()
    repo = _repo([_event("AI Summit", category=EventCategory.AI, city="Bangalore")])
    provider = _provider(repo, cache=InMemorySearchCache(60), analytics=analytics)
    run(
        provider.search(
            SearchQuery(categories=[EventCategory.AI], city="Bangalore", keywords=["ai"])
        )
    )
    run(
        provider.search(
            SearchQuery(categories=[EventCategory.AI], city="Bangalore", keywords=["ai"])
        )
    )  # cache hit
    run(provider.search(SearchQuery(city="Atlantis")))  # empty

    snap = analytics.snapshot()
    assert snap["total_searches"] == 3
    assert snap["empty_searches"] == 1
    assert snap["cache_hits"] == 1
    assert snap["avg_latency_ms"] >= 0.0
    assert ("ai", 2) in snap["popular_categories"]
    assert ("bangalore", 2) in snap["popular_cities"]
    assert ("ai", 2) in snap["popular_topics"]


# --------------------------- SearchService interface unchanged ---------------------------


def test_search_service_works_with_database_provider():
    repo = _repo([_event("AI Summit", category=EventCategory.AI), _event("Cloud Meet")])
    service = SearchService(
        parser=KeywordQueryParser(),
        provider=_provider(repo, cache=InMemorySearchCache(60)),
        parse_cache=TTLCache(60),
        results_cache=TTLCache(60),
    )
    # structured path
    events, _ = run(service.search_by_query(SearchQuery(categories=[EventCategory.AI])))
    assert _titles(events) == ["AI Summit"]
    # natural-language path (keyword parser → structured → repository)
    outcome = run(service.search("ai events"))
    assert any(e.category is EventCategory.AI for e in outcome.events)
