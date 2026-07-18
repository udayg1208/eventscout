"""Phase 6F / D3 — Search Discovery tests. Deterministic, no network, no API keys."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.discovery import FeedType, InMemoryDiscoveryInbox, SQLiteDiscoveryInbox
from app.discovery.models import DiscoveryStatus
from app.discovery.search import (
    DEFAULT_SPEC,
    Frontier,
    MockPage,
    MockSearchProvider,
    QuerySpec,
    SearchDiscoveryEngine,
    build_queries,
    build_search_candidate,
    by_domain,
    dedupe,
    parse_results,
    score_source,
)
from app.discovery.search.search import SearchResult, parse_query

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


# A mock search index spanning Meetup / GDG / FOSS / Hasgeek / IEEE / university / company /
# conference sources — plus off-topic noise that ranking must penalize out.
CORPUS = [
    MockPage(
        "https://www.meetup.com/bangpypers/",
        "BangPypers - Bangalore Python User Group",
        "Monthly Python meetup in Bangalore, India.",
        ("bangalore", "python", "meetup"),
    ),
    MockPage(
        "https://www.meetup.com/reactjs-bangalore/",
        "ReactJS Bangalore",
        "React developers meetup in Bangalore.",
        ("bangalore", "react", "meetup"),
    ),
    MockPage(
        "https://gdg.community.dev/gdg-cloud-bangalore/",
        "GDG Cloud Bangalore",
        "Google Developer Group - AI and cloud events in Bangalore, India.",
        ("bangalore", "ai", "gdg", "india"),
    ),
    MockPage(
        "https://fossunited.org/c/bangalore",
        "FOSS United Bangalore",
        "Open source community meetup, Bangalore India.",
        ("bangalore", "fossunited", "opensource", "meetup"),
    ),
    MockPage(
        "https://hasgeek.com/rootconf",
        "Rootconf - DevOps Conference",
        "Rootconf DevOps and infrastructure conference, India.",
        ("devops", "conference", "india", "rootconf"),
    ),
    MockPage(
        "https://ieee.nitk.ac.in/",
        "IEEE NITK Student Branch",
        "IEEE student branch workshops and tech events.",
        ("ieee", "workshop", "students"),
    ),
    MockPage(
        "https://www.iitb.ac.in/tech-club",
        "IIT Bombay Tech Club",
        "AI and Python workshops at IIT Bombay, India.",
        ("iit", "ai", "python", "workshop"),
    ),
    MockPage(
        "https://in.pycon.org/",
        "PyCon India",
        "The annual Python conference for India.",
        ("python", "conference", "india", "pycon"),
    ),
    # ---- off-topic noise (must be penalized below threshold) ----
    MockPage(
        "https://in.bookmyshow.com/bangalore/movies",
        "Movies in Bangalore | BookMyShow",
        "Book movie tickets and concerts in Bangalore.",
        ("bangalore", "movies", "concert"),
    ),
    MockPage(
        "https://www.makemytrip.com/bangalore",
        "Bangalore Tourism and Hotels",
        "Travel, tourism and hotel booking in Bangalore.",
        ("bangalore", "tourism", "travel"),
    ),
]

# Focused spec whose queries exercise the corpus deterministically.
TEST_SPEC = QuerySpec(
    cities=("Bangalore",),
    technologies=("Python", "AI", "React"),
    platforms=("meetup.com",),
    community_sites=("gdg.community.dev", "fossunited.org", "hasgeek.com"),
    event_types=("meetup", "conference"),
    universities=("IIT",),
    companies=("Google",),
)


def _pr(url, title="", snippet="", rank=1, engine="mock", query="q"):
    return parse_results([SearchResult(title, url, snippet, rank, engine)], query)[0]


# --------------------------- query generation ---------------------------


def test_build_queries_deterministic_and_templated():
    q1 = build_queries(TEST_SPEC)
    q2 = build_queries(TEST_SPEC)
    assert q1 == q2  # deterministic order
    assert "site:meetup.com Bangalore Python" in q1
    assert "site:gdg.community.dev India" in q1
    assert "site:hasgeek.com conference" in q1
    assert "IIT Python club events" in q1
    assert "Google tech talks India" in q1
    assert len(q1) == len(set(q1))  # de-duplicated


def test_build_queries_dedupe_and_limit():
    spec = QuerySpec(
        cities=("Delhi", "Delhi"),  # duplicate collapses
        technologies=("Kubernetes",),
        platforms=("meetup.com",),
        community_sites=(),
        event_types=(),
        universities=(),
        companies=(),
    )
    qs = build_queries(spec)
    assert qs.count("site:meetup.com Delhi Kubernetes") == 1
    assert build_queries(DEFAULT_SPEC, limit=5) == build_queries(DEFAULT_SPEC)[:5]


def test_parse_query_site_and_terms():
    assert parse_query("site:meetup.com Bangalore Python") == (
        "meetup.com",
        ["bangalore", "python"],
    )
    assert parse_query("AI conference Delhi") == (None, ["ai", "conference", "delhi"])


# --------------------------- search provider (mock) ---------------------------


def test_mock_search_site_filter_and_ranking():
    provider = MockSearchProvider(CORPUS)
    results = run(provider.search("site:meetup.com Bangalore Python"))
    assert results  # meetup pages only
    assert all("meetup.com" in r.url for r in results)
    assert results[0].url == "https://www.meetup.com/bangpypers/"  # best term overlap first
    assert [r.rank for r in results] == list(range(1, len(results) + 1))


def test_mock_search_subdomain_site_match():
    provider = MockSearchProvider(CORPUS)
    # site:gdg.community.dev must match the full host (registrable domain is community.dev)
    results = run(provider.search("site:gdg.community.dev India"))
    assert len(results) == 1 and results[0].url.startswith("https://gdg.community.dev/")


def test_mock_search_no_match_is_empty():
    provider = MockSearchProvider(CORPUS)
    assert run(provider.search("site:meetup.com Reykjavik Haskell")) == []


# --------------------------- parser ---------------------------


def test_parser_normalizes_and_extracts_domain():
    p = _pr("https://GDG.community.dev/Cloud-Bangalore/", "GDG", "AI events")
    assert (
        p.url == "https://gdg.community.dev/Cloud-Bangalore"
    )  # normalized (host-lowered, slash trimmed)
    assert p.domain == "community.dev"


def test_parser_drops_junk_and_dupes():
    results = [
        SearchResult("A", "https://x.org/a", rank=1),
        SearchResult("dup", "https://x.org/a", rank=2),  # same URL → dropped
        SearchResult("mail", "mailto:a@b.com", rank=3),  # unusable → dropped
    ]
    parsed = parse_results(results, "q")
    assert len(parsed) == 1 and parsed[0].url == "https://x.org/a"


# --------------------------- ranking ---------------------------


def test_ranking_high_for_meetup_and_penalizes_noise():
    good = score_source(
        _pr(
            "https://www.meetup.com/bangpypers/",
            "BangPypers - Bangalore Python User Group",
            "Monthly Python meetup in Bangalore, India.",
        )
    )
    assert good.total >= 0.5
    assert good.is_meetup and good.known_community and good.has_city and good.india >= 0.8

    bad = score_source(
        _pr(
            "https://in.bookmyshow.com/bangalore/movies",
            "Movies in Bangalore | BookMyShow",
            "Book movie tickets and concerts.",
        )
    )
    assert bad.penalty >= 0.6 and bad.total < 0.3  # off-topic domain + terms → filtered


def test_ranking_conference_and_jsonld_signals():
    s = score_source(
        _pr(
            "https://hasgeek.com/rootconf",
            "Rootconf - DevOps Conference",
            "DevOps and infrastructure conference, India.",
        )
    )
    assert s.is_conference and s.jsonld_hint and s.known_community


def test_ranking_deterministic():
    p = _pr("https://in.pycon.org/", "PyCon India", "Annual Python conference India.")
    assert score_source(p) == score_source(p)


# --------------------------- dedup ---------------------------


def test_dedupe_collapses_urls_keeps_best_rank():
    a = _pr("https://x.org/a", "A", rank=5, query="q1")
    b = _pr("https://x.org/a", "A", rank=2, query="q2")  # same URL, better rank
    c = _pr("https://x.org/b", "B", rank=1, query="q1")
    out = dedupe([a, b, c])
    assert len(out) == 2
    kept = next(r for r in out if r.url == "https://x.org/a")
    assert kept.rank == 2  # strongest rank retained
    assert by_domain(out) == {"x.org": 2}


# --------------------------- frontier ---------------------------


def test_frontier_novelty_and_known_seeding():
    f = Frontier(known_urls=["https://known.org/a"])
    assert "known.org" in f.known_domains
    assert f.is_new("https://known.org/a") is False  # already known
    assert f.is_new("https://fresh.org/x") is True
    assert f.offer("https://fresh.org/x") is True
    assert f.offer("https://fresh.org/x") is False  # never rediscover an identical page
    assert f.next_pending() == "https://fresh.org/x"
    assert f.stats()["seen_urls"] == 1


# --------------------------- candidate builder + inbox ---------------------------


def test_build_search_candidate_fields():
    p = _pr(
        "https://gdg.community.dev/gdg-cloud-bangalore/",
        "GDG Cloud Bangalore",
        "Google Developer Group AI events in Bangalore, India.",
        rank=3,
        engine="mock",
        query="site:gdg.community.dev India",
    )
    cand = build_search_candidate(p, score_source(p), now=NOW)
    assert cand.feed_type is FeedType.SEARCH_RESULT
    assert cand.discovered_by == "search"
    assert cand.search_query == "site:gdg.community.dev India"
    assert cand.search_rank == 3 and cand.search_engine == "mock"
    assert cand.key == cand.url and cand.status is DiscoveryStatus.NEW
    assert cand.city == "Bangalore" and cand.country == "India"
    assert cand.structured_data_score == 0  # not crawled → no structured data confirmed


def test_sqlite_persists_search_provenance():
    inbox = SQLiteDiscoveryInbox()
    p = _pr(
        "https://in.pycon.org/",
        "PyCon India",
        "Python conference India.",
        rank=2,
        query="Python conference",
    )
    cand = build_search_candidate(p, score_source(p), now=NOW)
    assert run(inbox.upsert(cand)) == "inserted"
    got = run(inbox.get(cand.key))
    assert got.discovered_by == "search" and got.search_rank == 2
    assert got.search_query == "Python conference" and got.search_engine == "mock"
    assert got.feed_type is FeedType.SEARCH_RESULT
    run(inbox.close())


# --------------------------- end-to-end engine ---------------------------


def test_engine_end_to_end_discovers_and_filters():
    inbox = InMemoryDiscoveryInbox()
    engine = SearchDiscoveryEngine(
        MockSearchProvider(CORPUS), inbox, min_score=0.3, clock=lambda: NOW
    )
    report = run(engine.run(TEST_SPEC))

    domains = set(report.discovered_domains)
    assert "community.dev" in domains  # GDG
    assert "meetup.com" in domains  # BangPypers / ReactJS
    assert "fossunited.org" in domains
    assert "hasgeek.com" in domains
    # noise stayed out
    assert "bookmyshow.com" not in domains and "makemytrip.com" not in domains

    stored = run(inbox.list(limit=100))
    assert all(c.discovered_by == "search" for c in stored)
    assert all(c.feed_type is FeedType.SEARCH_RESULT for c in stored)
    assert report.accepted == len(stored)
    assert report.below_threshold >= 1  # at least one off-topic page scored under threshold


def test_engine_duplicate_suppression_and_incremental():
    inbox = InMemoryDiscoveryInbox()
    engine = SearchDiscoveryEngine(
        MockSearchProvider(CORPUS), inbox, min_score=0.3, clock=lambda: NOW
    )
    first = run(engine.run(TEST_SPEC))
    # the same page is surfaced by multiple queries → collapsed before insertion
    assert first.duplicates_removed >= 1
    count_after_first = run(inbox.count())
    assert count_after_first == first.inserted

    # second run: frontier is seeded from the inbox → everything already known, nothing re-added
    second = run(engine.run(TEST_SPEC))
    assert second.inserted == 0
    assert second.skipped_known >= count_after_first
    assert run(inbox.count()) == count_after_first  # inbox size stable
