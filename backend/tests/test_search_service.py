"""M4 tests: SearchService orchestration + TTL cache.

Covers cache hit, cache miss, parser invocation, provider invocation, empty
results, provider failure, and cache expiration. The parser and provider are
spies; the cache clock is a controllable fake, so nothing sleeps or hits a network.
"""

from __future__ import annotations

import asyncio
from datetime import date

from app.cache import TTLCache
from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.parsers.base import QueryParser
from app.providers.base import EventProvider
from app.services.search_service import SearchService


def run(coro):
    return asyncio.run(coro)


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


class SpyParser(QueryParser):
    def __init__(self, query: SearchQuery) -> None:
        self._query = query
        self.calls = 0
        self.seen: list[str] = []

    async def parse(self, text: str) -> SearchQuery:
        self.calls += 1
        self.seen.append(text)
        return self._query


class SpyProvider(EventProvider):
    name = "spy"

    def __init__(self, events: list[Event] | None = None, error: Exception | None = None) -> None:
        self._events = events or []
        self._error = error
        self.calls = 0
        self.seen: list[SearchQuery] = []

    async def search(self, query: SearchQuery) -> list[Event]:
        self.calls += 1
        self.seen.append(query)
        if self._error is not None:
            raise self._error
        return list(self._events)


def make_event(title: str = "Event") -> Event:
    return Event(
        title=title,
        url="https://example.com/e",
        start_date=date(2026, 8, 1),
        category=EventCategory.WORKSHOP,
        provider="spy",
    )


def make_service(parser, provider, clock=None, ttl=300):
    clock = clock or FakeClock()
    return SearchService(
        parser=parser,
        provider=provider,
        parse_cache=TTLCache(ttl, clock),
        results_cache=TTLCache(ttl, clock),
    )


# --------------------------- cache hit / miss ---------------------------


def test_repeat_text_hits_both_caches_and_skips_parser_and_provider():
    parser = SpyParser(SearchQuery(city="Pune"))
    provider = SpyProvider([make_event()])
    svc = make_service(parser, provider)

    r1 = run(svc.search("events in pune"))
    assert parser.calls == 1 and provider.calls == 1
    assert r1.parse_cached is False and r1.cached is False
    assert len(r1.events) == 1

    r2 = run(svc.search("events in pune"))
    assert parser.calls == 1  # parse-cache hit -> Gemini skipped (req 5)
    assert provider.calls == 1  # results-cache hit -> provider skipped
    assert r2.parse_cached is True and r2.cached is True
    assert r2.events == r1.events


def test_distinct_text_same_query_still_hits_results_cache():
    # Two different phrasings that resolve to the SAME SearchQuery.
    parser = SpyParser(SearchQuery(city="Pune"))
    provider = SpyProvider([make_event()])
    svc = make_service(parser, provider)

    run(svc.search("pune events"))
    r2 = run(svc.search("events in pune"))

    assert parser.calls == 2  # new wording -> parsed again
    assert provider.calls == 1  # identical SearchQuery -> results-cache hit (req 4)
    assert r2.parse_cached is False and r2.cached is True


# --------------------------- invocation wiring ---------------------------


def test_parser_invoked_with_original_raw_text():
    parser = SpyParser(SearchQuery())
    provider = SpyProvider([])
    svc = make_service(parser, provider)
    run(svc.search("  Hello   World  "))
    assert parser.seen == ["  Hello   World  "]  # raw text passed as-is to the parser


def test_provider_invoked_with_parsed_query():
    query = SearchQuery(city="Mumbai", categories=[EventCategory.AI])
    parser = SpyParser(query)
    provider = SpyProvider([make_event()])
    svc = make_service(parser, provider)
    run(svc.search("ai in mumbai"))
    assert provider.seen == [query]


# --------------------------- empty & failure ---------------------------


def test_empty_results_are_cached():
    parser = SpyParser(SearchQuery(city="Nowhere"))
    provider = SpyProvider([])  # provider legitimately finds nothing
    svc = make_service(parser, provider)

    r1 = run(svc.search("q"))
    assert r1.events == [] and provider.calls == 1

    r2 = run(svc.search("q"))
    assert r2.events == [] and provider.calls == 1  # empty list cached, provider not re-called
    assert r2.cached is True


def test_provider_failure_returns_empty_and_is_not_cached():
    parser = SpyParser(SearchQuery(city="X"))
    provider = SpyProvider(error=RuntimeError("boom"))
    svc = make_service(parser, provider)

    r1 = run(svc.search("q"))
    assert r1.events == [] and r1.cached is False
    assert provider.calls == 1

    run(svc.search("q"))
    assert parser.calls == 1  # parse-cache still hit
    assert provider.calls == 2  # failure was NOT cached -> provider retried


# --------------------------- expiration ---------------------------


def test_cache_expires_after_ttl():
    clock = FakeClock()
    parser = SpyParser(SearchQuery(city="Pune"))
    provider = SpyProvider([make_event()])
    svc = make_service(parser, provider, clock=clock, ttl=300)

    run(svc.search("pune"))
    assert parser.calls == 1 and provider.calls == 1

    clock.advance(299)  # still within TTL
    run(svc.search("pune"))
    assert parser.calls == 1 and provider.calls == 1

    clock.advance(2)  # now 301s > 300s TTL -> both caches expired
    run(svc.search("pune"))
    assert parser.calls == 2 and provider.calls == 2


# --------------------------- TTLCache unit ---------------------------


def test_ttl_cache_get_set_and_expiry():
    clock = FakeClock()
    cache: TTLCache[str, list[int]] = TTLCache(10, clock)
    assert cache.get("k") is None
    cache.set("k", [1, 2])
    assert cache.get("k") == [1, 2]
    clock.advance(9)
    assert cache.get("k") == [1, 2]
    clock.advance(2)  # 11 >= 10 -> expired
    assert cache.get("k") is None


def test_ttl_cache_treats_empty_value_as_hit():
    cache: TTLCache[str, list[int]] = TTLCache(10, FakeClock())
    cache.set("k", [])
    assert cache.get("k") == []  # not None -> a hit, not a miss


# --------------------------- metrics ---------------------------


def test_metrics_tracks_requests_caches_provider_and_latency():
    parser = SpyParser(SearchQuery(city="Pune"))
    provider = SpyProvider([make_event()])
    svc = make_service(parser, provider)

    run(svc.search("pune events"))  # parse miss, results miss
    run(svc.search("pune events"))  # parse hit,  results hit
    run(svc.search("different text"))  # parse miss, same query -> results hit

    m = svc.metrics()
    assert m["total_requests"] == 3
    assert m["parse_cache"] == {"lookups": 3, "hits": 1, "hit_rate": round(1 / 3, 4)}
    assert m["results_cache"] == {"lookups": 3, "hits": 2, "hit_rate": round(2 / 3, 4)}
    assert m["provider_calls"] == 1
    assert m["avg_latency_ms"] >= 0.0
    assert m["gemini_calls"] == 0  # SpyParser exposes no counter -> 0
    assert m["fallback_count"] == 0


def test_metrics_surfaces_parser_counters_via_getattr():
    parser = SpyParser(SearchQuery())
    parser.gemini_calls = 7  # simulate a Gemini-backed parser
    parser.fallback_count = 2
    svc = make_service(parser, SpyProvider([]))
    run(svc.search("x"))
    m = svc.metrics()
    assert m["gemini_calls"] == 7
    assert m["fallback_count"] == 2
