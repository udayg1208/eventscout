"""Phase 10A — Real Discovery Execution tests. Mocked HTTP + fixture sites, NO network."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from app.discovery import InMemoryDiscoveryInbox
from app.discovery.fetch import FetchResult, StaticFetcher
from app.discovery.models import CandidateSource, ConfidenceSignals, DiscoveryStatus, FeedType
from app.discovery.robots import RobotsCache
from app.discovery.search import QuerySpec
from app.discovery.web import (
    BingWebSearchProvider,
    DuckDuckGoProvider,
    GoogleProgrammableSearchProvider,
    SearchResult,
    SerpApiSearchProvider,
    WebSearchProvider,
)
from app.execution import (
    DEFAULT_SEEDS,
    SEED_LIST_VERSION,
    ExecutionMetrics,
    PageFetcher,
    ProductionSeedList,
    RealDiscoveryPipeline,
    Seed,
    SeedCategory,
    SourceVerifier,
    VerifyingInbox,
    active_provider_name,
    build_web_provider,
)
from app.execution.verification import VerificationResult
from app.orchestrator import SQLiteOrchestratorStore

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- fixtures


class FixtureProvider(WebSearchProvider):
    name = "fixture"

    def __init__(self, results=None):
        self._results = results or []

    async def search(self, query, *, limit=10):
        return list(self._results)[:limit]


def _page() -> str:
    nd = json.dumps(
        {
            "props": {
                "pageProps": {
                    "events": [
                        {"title": "React Meetup Bangalore", "start_date": "2026-08-01"},
                        {"title": "PyData Pune", "start_date": "2026-08-02"},
                    ]
                }
            }
        }
    )
    return (
        "<!doctype html><html><head><title>Tech Events India</title>"
        '<meta property="og:site_name" content="GDG Bangalore">'
        '<script type="application/ld+json">{"@type":"Event","name":"DevFest Bangalore 2026",'
        '"startDate":"2026-11-01","location":{"name":"Bangalore"}}</script>'
        '<link rel="alternate" type="application/rss+xml" href="/feed.xml"></head><body>'
        '<div id="__next"></div>'
        f'<script id="__NEXT_DATA__" type="application/json">{nd}</script>'
        '<script>fetch("/api/events?city=bangalore");</script>'
        "Python, AI and Kubernetes workshops in Bangalore, India.</body></html>"
    )


def _R(url, text, ct="text/html", status=200):
    return FetchResult(url=url, status=status, content_type=ct, text=text)


def fixture_internet() -> dict[str, FetchResult]:
    return {
        "https://ex.test/robots.txt": _R(
            "https://ex.test/robots.txt", "User-agent: *\nAllow: /", "text/plain"
        ),
        "https://ex.test/events": _R("https://ex.test/events", _page()),
        "https://blocked.test/robots.txt": _R(
            "https://blocked.test/robots.txt", "User-agent: *\nDisallow: /", "text/plain"
        ),
        "https://blocked.test/events": _R("https://blocked.test/events", _page()),
    }


def small_seeds() -> ProductionSeedList:
    return ProductionSeedList(
        version="test.1",
        seeds=(
            Seed("https://ex.test/events", SeedCategory.CONFERENCE, "Ex"),
            Seed("https://blocked.test/events", SeedCategory.CONFERENCE, "Blocked"),
        ),
    )


def candidate(key="https://k.test/x", *, relevant=True, last_seen=None) -> CandidateSource:
    return CandidateSource(
        key=key,
        url=key,
        domain="k.test",
        feed_type=FeedType.JSON_API,
        discovery_confidence=0.8 if relevant else 0.0,
        signals=ConfidenceSignals(has_api_endpoint=True) if relevant else ConfidenceSignals(),
        discovered_by="rendered",
        last_seen_at=last_seen,
    )


# --------------------------------------------------------------------------- seed list


def test_seed_list_is_versioned_and_categorized():
    seeds = DEFAULT_SEEDS
    assert seeds.version == SEED_LIST_VERSION
    assert len(seeds.seeds) >= 20
    cats = seeds.categories()
    for c in SeedCategory:  # every category represented
        assert cats.get(c.value, 0) >= 1
    assert all(u.startswith("https://") for u in seeds.urls())


def test_seed_sample_is_deterministic_and_spread():
    a = DEFAULT_SEEDS.sample(6)
    b = DEFAULT_SEEDS.sample(6)
    assert [s.url for s in a] == [s.url for s in b]  # deterministic
    assert len({s.category for s in a}) >= 5  # spread across categories


# --------------------------------------------------------------------------- provider factory


def test_active_provider_name_by_env():
    assert active_provider_name({"GOOGLE_API_KEY": "k", "GOOGLE_CX": "cx"}) == "google"
    assert active_provider_name({"BING_API_KEY": "k"}) == "bing"
    assert active_provider_name({"SERPAPI_KEY": "k"}) == "serpapi"
    assert active_provider_name({}) == "duckduckgo"


def test_build_web_provider_selects_real_impl():
    from app.discovery.web import PoliteFetcher

    f = PoliteFetcher()
    assert isinstance(build_web_provider(f, env={}), DuckDuckGoProvider)
    assert isinstance(
        build_web_provider(f, env={"GOOGLE_API_KEY": "k", "GOOGLE_CX": "c"}),
        GoogleProgrammableSearchProvider,
    )
    assert isinstance(build_web_provider(f, env={"BING_API_KEY": "k"}), BingWebSearchProvider)
    assert isinstance(build_web_provider(f, env={"SERPAPI_KEY": "k"}), SerpApiSearchProvider)


# --------------------------------------------------------------------------- page fetcher


def test_page_fetcher_fetches_caches_and_gates_robots():
    fetcher = StaticFetcher(fixture_internet())
    robots = RobotsCache(fetcher)
    pf = PageFetcher(fetcher, robots=robots)
    page = run(pf.fetch("https://ex.test/events"))
    assert page is not None and "Tech Events" in page.html
    assert pf.stats.fetched == 1
    run(pf.fetch("https://ex.test/events"))  # cache hit
    assert pf.stats.cache_hits == 1
    assert run(pf.fetch("https://blocked.test/events")) is None  # robots disallow
    assert pf.stats.skipped_robots == 1


def test_page_fetcher_skips_non_html_and_errors():
    fetcher = StaticFetcher(
        {
            "https://x.test/robots.txt": _R("https://x.test/robots.txt", "", "text/plain"),
            "https://x.test/a.pdf": _R("https://x.test/a.pdf", "%PDF", "application/pdf"),
            "https://x.test/404": _R("https://x.test/404", "nope", "text/html", status=404),
        }
    )
    pf = PageFetcher(fetcher, robots=RobotsCache(fetcher))
    assert run(pf.fetch("https://x.test/a.pdf")) is None
    assert run(pf.fetch("https://x.test/404")) is None
    assert pf.stats.skipped_error == 2


# --------------------------------------------------------------------------- verifier


def test_verifier_accessibility_robots_relevance_duplicate():
    fetcher = StaticFetcher(fixture_internet())
    v = SourceVerifier(robots=RobotsCache(fetcher), clock=lambda: NOW)

    # accessibility fail
    bad = candidate(key="ftp://x/y")
    r = run(v.verify(bad, None))
    assert not r.passed and r.checks["accessibility"] is False

    # robots block
    blocked = candidate(key="https://blocked.test/events")
    r = run(v.verify(blocked, None))
    assert not r.passed and r.checks["robots"] is False

    # relevance below threshold
    noise = candidate(key="https://ex.test/x", relevant=False)
    r = run(v.verify(noise, None))
    assert not r.passed and r.checks["relevance"] is False

    # duplicate — existing seen within revisit window
    good = candidate(key="https://ex.test/x")
    existing = candidate(key="https://ex.test/x", last_seen=NOW - timedelta(hours=1))
    r = run(v.verify(good, existing))
    assert r.duplicate and not r.passed

    # clean pass (no robots, new, relevant)
    v2 = SourceVerifier(robots=None, clock=lambda: NOW)
    assert run(v2.verify(candidate(key="https://ex.test/x"), None)).passed


def test_verifying_inbox_gates_and_delegates():
    inner = InMemoryDiscoveryInbox()
    events: list = []
    v = SourceVerifier(robots=None, clock=lambda: NOW)
    vinbox = VerifyingInbox(inner, v, on_result=lambda c, r, o: events.append(o))

    assert run(vinbox.upsert(candidate(key="https://a.test/x"))) == "inserted"
    assert run(vinbox.upsert(candidate(key="https://b.test/x", relevant=False))) == "rejected"
    assert run(vinbox.count()) == 1  # only the accepted one reached the real inbox
    assert run(vinbox.get("https://a.test/x")) is not None
    assert events == ["inserted", "rejected"]


# --------------------------------------------------------------------------- metrics


def test_execution_metrics_derive_precision_and_rates():
    m = ExecutionMetrics()
    m.record_pages(crawled=10, skipped=4, cost_bytes=2048)
    m.record_verification(candidate(key="https://a.test/1"), VerificationResult(True), "inserted")
    m.record_verification(candidate(key="https://a.test/2"), VerificationResult(True), "updated")
    m.record_verification(candidate(), VerificationResult(False, reasons=["noise"]), "rejected")
    m.record_verification(candidate(), VerificationResult(False, duplicate=True), "duplicate")
    snap = m.snapshot(date="2026-07-16")
    assert snap.pages_crawled == 10 and snap.pages_skipped == 4
    assert snap.accepted == 2 and snap.rejected == 1 and snap.duplicates == 1
    assert snap.new_sources == 1  # only one "inserted"
    assert snap.new_domains == 1  # a.test
    assert round(snap.discovery_precision, 4) == round(2 / 3, 4)
    assert round(snap.duplicate_rate, 4) == round(1 / 4, 4)
    assert snap.crawl_cost_bytes == 2048


# --------------------------------------------------------------------------- integration


def _pipeline(**kw):
    fetcher = StaticFetcher(fixture_internet())
    provider = FixtureProvider(
        [
            SearchResult(
                title="DevFest",
                url="https://ex.test/events",
                snippet="python ai",
                rank=1,
                engine="fixture",
            )
        ]
    )
    spec = QuerySpec(
        cities=("Bangalore",),
        technologies=("Python",),
        platforms=(),
        community_sites=(),
        event_types=(),
        universities=(),
        companies=(),
    )
    return RealDiscoveryPipeline(
        fetcher=fetcher,
        web_provider=provider,
        seeds=small_seeds(),
        spec=spec,
        min_relevance=0.0,
        clock=lambda: NOW,
        **kw,
    )


def test_integration_full_cycle_reaches_inbox():
    pipe = _pipeline()
    report = run(pipe.run_cycle(max_cycles=15))
    # the whole pipeline executed
    for stage in ("search_discovery", "expansion", "social_discovery", "rendered_discovery"):
        assert stage in report.orchestrator.stages_run
    # real candidates landed in the inbox, all NEW, all discovered by the real engines
    cands = run(pipe.inbox.list(limit=50))
    assert len(cands) >= 2
    assert all(c.status is DiscoveryStatus.NEW for c in cands)
    assert report.inbox_new == report.inbox_total
    # rendered found the hidden API + hydration from the real fixture page
    urls = {c.url for c in cands}
    assert any("/api/events" in u for u in urls)


def test_integration_respects_robots_on_blocked_origin():
    pipe = _pipeline()
    run(pipe.run_cycle(max_cycles=15))
    cands = run(pipe.inbox.list(limit=50))
    assert not any("blocked.test" in c.url for c in cands)  # robots-disallowed → never discovered
    assert pipe.page_fetcher.stats.skipped_robots >= 1


def test_integration_metrics_populated():
    pipe = _pipeline()
    report = run(pipe.run_cycle(max_cycles=15))
    m = report.metrics
    assert m.pages_crawled >= 1
    assert m.new_sources >= 2
    assert m.new_domains >= 1
    assert m.discovery_precision > 0.0
    assert report.provider == "fixture"
    assert report.seed_version == "test.1"


# ------------------------------------------------------------------ reliability (orchestrator)


def test_reliability_checkpoint_and_resume():
    store = SQLiteOrchestratorStore(":memory:")
    try:
        pipe = _pipeline(orchestrator_store=store)
        run(pipe.run_cycle(max_cycles=15))
        assert run(store.checkpoint_count()) >= 1  # checkpointed every cycle
        # a fresh pipeline over the same store can resume the persisted state
        pipe2 = _pipeline(orchestrator_store=store)
        assert run(pipe2.resume()) is True
    finally:
        run(store.close())


def test_reliability_graceful_shutdown():
    pipe = _pipeline()
    run(pipe.run_cycle(max_cycles=15))
    # the loop terminated cleanly (stop_when_idle) — not left running
    assert pipe.orchestrator.state.running is False
    # stop() is the cooperative shutdown signal the loop checks between cycles
    pipe.stop()
    assert pipe.orchestrator.state.running is False
