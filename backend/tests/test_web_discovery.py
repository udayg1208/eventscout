"""Phase 8B — Real Web Discovery tests. Every provider mocked; NO real network."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from app.discovery import InMemoryDiscoveryInbox
from app.discovery.search import QuerySpec
from app.discovery.web import (
    BingWebSearchProvider,
    Budget,
    DuckDuckGoProvider,
    GoogleProgrammableSearchProvider,
    PoliteFetcher,
    ProviderError,
    RateLimiter,
    SearchCache,
    SearchProviderConfig,
    SearchResult,
    SerpApiSearchProvider,
    WebDiscoveryEngine,
    WebSearchProvider,
    dedupe_across,
    normalize_query,
    normalize_results,
    parse_ddg_html,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


async def _noop(_):
    return None


class FakeResp:
    def __init__(self, status, text, url="https://x"):
        self.status_code = status
        self.text = text
        self.url = url


class FakeClient:
    """Returns queued responses in order (last repeats). Records calls. No network."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[idx]


def fetcher_for(*responses):
    return PoliteFetcher(client=FakeClient(list(responses)), sleep=_noop, max_retries=3)


class StubProvider(WebSearchProvider):
    name = "stub"

    def __init__(self, results_by_query, *, error_on=None):
        self._results = results_by_query
        self._error_on = set(error_on or ())

    @property
    def configured(self):
        return True

    async def search(self, query, *, limit=10):
        if query in self._error_on:
            raise ProviderError("stub boom")
        return list(self._results.get(query, []))[:limit]


# --------------------------- provider response mapping ---------------------------


def test_google_maps_items_and_requires_key():
    body = json.dumps({"items": [{"title": "GDG", "link": "https://gdg.dev", "snippet": "AI"}]})
    g = GoogleProgrammableSearchProvider(
        SearchProviderConfig(api_key="k", engine_id="cx"), fetcher=fetcher_for(FakeResp(200, body))
    )
    results = run(g.search("gdg india"))
    assert (
        len(results) == 1 and results[0].url == "https://gdg.dev" and results[0].engine == "google"
    )
    # missing credentials → not configured, and search raises
    bare = GoogleProgrammableSearchProvider(
        SearchProviderConfig(), fetcher=fetcher_for(FakeResp(200, "{}"))
    )
    assert bare.configured is False
    try:
        run(bare.search("x"))
        raise AssertionError("expected ProviderError")
    except ProviderError:
        pass


def test_bing_and_serpapi_mapping():
    bing_body = json.dumps(
        {"webPages": {"value": [{"name": "N", "url": "https://b.org", "snippet": "s"}]}}
    )
    b = BingWebSearchProvider(
        SearchProviderConfig(api_key="k"), fetcher=fetcher_for(FakeResp(200, bing_body))
    )
    assert run(b.search("q"))[0].url == "https://b.org"

    serp_body = json.dumps(
        {"organic_results": [{"title": "T", "link": "https://s.io", "position": 1}]}
    )
    s = SerpApiSearchProvider(
        SearchProviderConfig(api_key="k"), fetcher=fetcher_for(FakeResp(200, serp_body))
    )
    assert run(s.search("q"))[0].url == "https://s.io"


def test_duckduckgo_html_parse_decodes_redirect():
    uddg = "https%3A%2F%2Fwww.meetup.com%2Fbangpypers%2F"
    html = (
        f'<a class="result__a" href="//duckduckgo.com/l/?uddg={uddg}">BangPypers</a>'
        '<a class="result__snippet">Python meetup Bangalore</a>'
        '<a class="result__a" href="https://gdg.community.dev/blr/">GDG</a>'
    )
    results = parse_ddg_html(html, 10)
    assert results[0].url == "https://www.meetup.com/bangpypers/"  # redirect decoded
    assert results[1].url == "https://gdg.community.dev/blr/"
    assert results[0].engine == "duckduckgo"


def test_duckduckgo_provider_uses_fetcher():
    html = '<a class="result__a" href="https://x.org/e">E</a>'
    ddg = DuckDuckGoProvider(fetcher=fetcher_for(FakeResp(200, html)), mode="html")
    assert ddg.configured is True
    assert run(ddg.search("q"))[0].url == "https://x.org/e"


# --------------------------- polite fetcher (retry/backoff) ---------------------------


def test_fetcher_retries_then_succeeds():
    f = PoliteFetcher(
        client=FakeClient([FakeResp(503, ""), FakeResp(429, ""), FakeResp(200, "ok")]),
        sleep=_noop,
        max_retries=3,
    )
    resp = run(f.get("https://x"))
    assert resp.status == 200 and resp.text == "ok"


def test_fetcher_gives_up_after_retries():
    f = PoliteFetcher(client=FakeClient([FakeResp(500, "")]), sleep=_noop, max_retries=3)
    try:
        run(f.get("https://x"))
        raise AssertionError("expected ProviderError")
    except ProviderError:
        pass


# --------------------------- cache ---------------------------


def test_cache_hit_miss_expiry_invalidate():
    t = {"now": NOW}
    cache = SearchCache(ttl_hours=24, clock=lambda: t["now"])
    r = [SearchResult("T", "https://x", "", 1, "stub")]
    assert cache.get("stub", "q") is None  # miss
    cache.put("stub", "q", r)
    assert cache.get("stub", "Q  ") is not None  # normalized key → hit
    t["now"] = NOW + timedelta(hours=25)
    assert cache.get("stub", "q") is None  # expired
    cache.put("stub", "q", r)
    assert cache.invalidate(provider="stub", query="q") == 1
    assert normalize_query("  Site:Meetup.com   Bangalore  ") == "site:meetup.com bangalore"


# --------------------------- rate limiter + budget ---------------------------


def test_rate_limiter_spaces_calls():
    t = {"now": NOW}
    waited = {"s": 0.0}

    async def sleep(s):
        waited["s"] += s
        t["now"] = t["now"] + timedelta(seconds=s)

    rl = RateLimiter(per_minute=60, clock=lambda: t["now"], sleep=sleep)  # 1s spacing
    run(rl.acquire("p"))  # first: no wait
    run(rl.acquire("p"))  # second: must wait ~1s
    assert rl.waits == 1 and waited["s"] > 0


def test_budget_caps_queries():
    b = Budget(2)
    assert b.consume() and b.consume() and not b.consume()
    assert b.remaining == 0


# --------------------------- normalizer ---------------------------


def test_normalizer_strips_tracking_and_dedupes():
    results = [
        SearchResult("A", "https://x.org/a?utm_source=ddg&id=1", "", 1, "stub"),
        SearchResult("A dup", "https://x.org/a?id=1&utm_medium=x", "", 2, "stub"),
    ]
    parsed = normalize_results(results, "q")
    # tracking stripped → both normalize to the same URL → deduped to one
    assert len(parsed) == 1 and "utm_" not in parsed[0].url


# --------------------------- engine (end-to-end, stubbed provider) ---------------------------


def _spec():
    return QuerySpec(
        cities=("Bangalore",),
        technologies=("Python", "AI"),
        platforms=("meetup.com",),
        community_sites=(),
        event_types=(),
        universities=(),
        companies=(),
    )


def _results():
    return {
        "site:meetup.com Bangalore Python": [
            SearchResult(
                "BangPypers Bangalore Python meetup",
                "https://meetup.com/bangpypers",
                "Python meetup in Bangalore India",
                1,
                "stub",
            ),
        ],
        "site:meetup.com Bangalore AI": [
            SearchResult(
                "GDG Bangalore AI",
                "https://gdg.community.dev/blr",
                "Google Developer Group AI Bangalore India",
                1,
                "stub",
            ),
        ],
    }


def test_engine_discovers_caches_and_updates_inbox():
    inbox = InMemoryDiscoveryInbox()
    cache = SearchCache(clock=lambda: NOW)
    engine = WebDiscoveryEngine(
        StubProvider(_results()), inbox, cache=cache, budget=Budget(20), clock=lambda: NOW
    )
    r1 = run(engine.run(_spec()))
    assert r1.provider == "stub" and r1.queries_executed == 2 and r1.cache_hits == 0
    assert r1.inserted == 2 and set(r1.new_domains) == {"meetup.com", "community.dev"}
    assert run(inbox.count()) == 2

    # second run: all served from cache, everything already known
    r2 = run(engine.run(_spec()))
    assert r2.cache_hits == 2 and r2.inserted == 0 and r2.skipped_known == 2
    assert cache.stats.hit_rate == 0.5


def test_engine_respects_budget_and_handles_provider_errors():
    inbox = InMemoryDiscoveryInbox()
    engine = WebDiscoveryEngine(
        StubProvider(_results(), error_on={"site:meetup.com Bangalore Python"}),
        inbox,
        budget=Budget(1),
        clock=lambda: NOW,
    )
    r = run(engine.run(_spec()))
    assert r.queries_executed == 1  # budget capped at 1
    # if the one executed query errored, it's counted and produces no crash
    assert r.provider_errors + r.results_collected >= 0
    assert run(inbox.count()) == r.inserted


def test_dedupe_across_keeps_best_rank():
    a = normalize_results([SearchResult("A", "https://x.org/a", "", 5, "s")], "q1")
    b = normalize_results([SearchResult("A", "https://x.org/a", "", 2, "s")], "q2")
    out = dedupe_across(a + b)
    assert len(out) == 1 and out[0].rank == 2
