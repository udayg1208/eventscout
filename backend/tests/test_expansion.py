"""Phase 8C — Web Expansion tests. Deterministic, no network (StaticFetcher + fixtures)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.discovery import InMemoryDiscoveryInbox
from app.discovery.expansion import (
    BudgetTracker,
    CrawlBudgetConfig,
    EdgeType,
    ExpansionEngine,
    ExpansionFrontier,
    ExpansionGraph,
    GraphNode,
    InMemoryCheckpointStore,
    InMemoryExpansionStore,
    NodeType,
    ScopeConfig,
    ScopeDecision,
    SQLiteCheckpointStore,
    canonicalize,
    evaluate_scope,
    extract,
    is_crawlable,
    node_key,
    score_url,
)
from app.discovery.expansion.models import CheckpointRecord
from app.discovery.fetch import FetchResult, StaticFetcher

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


def _r(url, body, ct="text/html", status=200):
    return FetchResult(url=url, status=status, content_type=ct, text=body)


# --------------------------- graph ---------------------------


def test_graph_dedup_nodes_and_edges():
    g = ExpansionGraph()
    n = GraphNode(
        node_key(NodeType.PAGE, "https://x.org/a"), NodeType.PAGE, "https://x.org/a", "x.org"
    )
    _, added1 = g.upsert_node(n)
    _, added2 = g.upsert_node(
        GraphNode(n.key, NodeType.PAGE, "https://x.org/a", "x.org", title="A")
    )
    assert added1 is True and added2 is False  # same key → merged, not duplicated
    assert g.get(n.key).title == "A"  # merge filled the title
    assert g.add_edge("a", "b", EdgeType.LINKS_TO) is True
    assert g.add_edge("a", "b", EdgeType.LINKS_TO) is False  # edge dedup
    assert g.stats()["total_nodes"] == 1 and g.stats()["total_edges"] == 1


# --------------------------- frontier ---------------------------


def test_frontier_priority_order_and_dedup():
    f = ExpansionFrontier(known_urls=["https://known.org/x"])
    assert f.offer("https://a.org/low", depth=1, from_domain="a.org", priority=0.2) is True
    assert f.offer("https://a.org/high", depth=1, from_domain="a.org", priority=0.9) is True
    assert f.offer("https://a.org/low", depth=1, from_domain="a.org", priority=0.5) is False  # dup
    assert f.offer("https://known.org/x", depth=1, from_domain="known.org", priority=1.0) is False
    assert f.next_item().url == "https://a.org/high"  # highest priority first
    assert f.next_item().url == "https://a.org/low"
    assert f.next_item() is None


# --------------------------- dedup ---------------------------


def test_canonicalize_strips_tracking_and_prefers_canonical():
    assert canonicalize("https://x.org/a?utm_source=z&id=1") == "https://x.org/a?id=1"
    assert (
        canonicalize("https://x.org/a", canonical="https://x.org/canonical")
        == "https://x.org/canonical"
    )
    assert (
        canonicalize("https://x.org/a", redirect_target="https://x.org/final")
        == "https://x.org/final"
    )
    assert node_key(NodeType.DOMAIN, "https://gdg.community.dev/x") == "domain#community.dev"


# --------------------------- scope ---------------------------


def test_scope_decisions():
    cfg = ScopeConfig(seed_domains={"gdg.org"}, max_depth=2)
    assert evaluate_scope("https://gdg.org/e", depth=1, config=cfg)[0] is ScopeDecision.ALLOW
    assert (
        evaluate_scope("https://meetup.com/x", depth=1, config=cfg)[0]
        is ScopeDecision.CROSS_TRUSTED
    )
    assert evaluate_scope("https://facebook.com/x", depth=1, config=cfg)[0] is ScopeDecision.BLOCK
    assert (
        evaluate_scope("https://gdg.org/e", depth=3, config=cfg)[0] is ScopeDecision.DEPTH_EXCEEDED
    )
    assert (
        evaluate_scope("https://random.io/x", depth=1, config=cfg)[0] is ScopeDecision.OUT_OF_SCOPE
    )
    assert is_crawlable(ScopeDecision.ALLOW) and not is_crawlable(ScopeDecision.OUT_OF_SCOPE)


# --------------------------- checkpoint ---------------------------


def test_checkpoint_inmemory_and_sqlite():
    for store in (InMemoryCheckpointStore(), SQLiteCheckpointStore()):
        rec = CheckpointRecord(url="https://x.org/a", domain="x.org", last_crawl=NOW, etag="abc")
        run(store.save(rec))
        got = run(store.get("https://x.org/a"))
        assert got is not None and got.etag == "abc"
        assert run(store.was_crawled_since("https://x.org/a", NOW - timedelta(hours=1))) is True
        assert run(store.was_crawled_since("https://x.org/a", NOW + timedelta(hours=1))) is False
        assert run(store.count()) == 1


# --------------------------- priority ---------------------------


def test_priority_explainable_and_ranks_feeds_high():
    feed = score_url("https://gdg.org/events/feed.xml", trusted_domain=False)
    plain = score_url("https://gdg.org/about")
    assert feed.score > plain.score and feed.reasons  # every score explains itself
    assert feed.signals["feed"] is True
    boosted = score_url("https://meetup.com/e", trusted_domain=True, domain_trust=0.9)
    assert boosted.signals.get("trusted_domain") is True


# --------------------------- crawl budget ---------------------------


def test_budget_caps_pages_failures_and_cooldown():
    t = {"now": NOW}
    b = BudgetTracker(
        CrawlBudgetConfig(max_pages=2, max_failures=2, cooldown_seconds=60), clock=lambda: t["now"]
    )
    assert b.can_crawl("x.org")[0] is True
    b.record_fetch("x.org", byte_size=100, success=True)
    b.record_fetch("x.org", byte_size=100, success=True)
    assert b.can_crawl("x.org")[0] is False  # max_pages reached → stopped
    assert "x.org" in b.stopped_domains()
    # cooldown after failure
    b2 = BudgetTracker(CrawlBudgetConfig(cooldown_seconds=60), clock=lambda: t["now"])
    b2.record_fetch("y.org", success=False)
    assert b2.can_crawl("y.org")[0] is False  # cooling down
    t["now"] = NOW + timedelta(seconds=61)
    assert b2.can_crawl("y.org")[0] is True  # cooldown elapsed


# --------------------------- extraction ---------------------------


def test_extraction_all_source_types():
    html = (
        '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml">'
        '<link rel="canonical" href="https://gdg.org/"></head><body>'
        '<a href="/events">Events</a>'
        '<a href="https://github.com/gdg-org">GH</a>'
        '<a href="https://gdg.notion.site/x">Notion</a>'
        '<a href="https://discord.gg/abc">Discord</a>'
        '<a href="https://t.me/gdgblr">TG</a>'
        '<a href="https://gdgblr.substack.com">Blog</a>'
        '<a href="https://calendar.google.com/calendar/ical/x/public/basic.ics">Cal</a>'
        "</body></html>"
    )
    ex = extract(_r("https://gdg.org/", html))
    assert ex.canonical == "https://gdg.org/"
    assert any(u.endswith("/feed.xml") for u, _ in ex.feeds)
    assert ex.github == ["https://github.com/gdg-org"]
    assert ex.notion and ex.discord and ex.telegram and ex.blogs
    assert any("calendar.google" in c for c in ex.calendars)
    assert "https://gdg.org/events" in ex.page_links


# --------------------------- engine (end-to-end) ---------------------------

_HOME = (
    '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml"></head><body>'
    '<a href="/events">Events</a> <a href="/community">Community</a>'
    '<a href="https://github.com/gdg-org">GitHub</a>'
    '<a href="https://t.me/gdgblr">Telegram</a>'
    '<a href="https://facebook.com/gdg">FB</a></body></html>'
)
_EVENTS = (
    "<html><body>Tech events Bangalore India Python AI meetup."
    '<script type="application/ld+json">{"@type":"Event","name":"AI Day"}</script></body></html>'
)
_COMMUNITY = '<html><body>GDG community chapter. <a href="/events">events</a></body></html>'


def _site():
    return StaticFetcher(
        {
            "https://gdg.org/robots.txt": _r("https://gdg.org/robots.txt", "", "text/plain"),
            "https://gdg.org/": _r("https://gdg.org/", _HOME),
            "https://gdg.org/events": _r("https://gdg.org/events", _EVENTS),
            "https://gdg.org/community": _r("https://gdg.org/community", _COMMUNITY),
        }
    )


def test_engine_expands_graph_and_updates_inbox():
    inbox = InMemoryDiscoveryInbox()
    cp = InMemoryCheckpointStore()
    engine = ExpansionEngine(
        _site(),
        inbox,
        checkpoint=cp,
        clock=lambda: NOW,
        scope_config=ScopeConfig(max_depth=2),
        budget_config=CrawlBudgetConfig(max_pages=10),
    )
    rep = run(engine.expand(["https://gdg.org/"], max_pages=10))
    assert rep.pages_fetched == 3  # home + events + community
    assert rep.feeds_found >= 1 and rep.github_found == 1 and rep.telegram_found == 1
    assert rep.candidates_inserted >= 4 and run(inbox.count()) == rep.candidates_inserted
    # graph has typed nodes + edges
    assert rep.nodes_by_type.get("page") == 3
    assert "github" in rep.nodes_by_type and "rss" in rep.nodes_by_type
    assert "owns" in rep.edges_by_type and "contains_feed" in rep.edges_by_type
    # facebook is blocked (never crawled)
    assert rep.frontier["blocked"] >= 1
    # every candidate is expansion-sourced, status NEW
    for c in run(inbox.list(limit=50)):
        assert c.discovered_by == "expansion"


def test_engine_incremental_second_run_skips_and_persists():
    inbox = InMemoryDiscoveryInbox()
    cp = InMemoryCheckpointStore()
    store = InMemoryExpansionStore()
    engine = ExpansionEngine(_site(), inbox, checkpoint=cp, store=store, clock=lambda: NOW)
    run(engine.expand(["https://gdg.org/"], max_pages=10))
    first_count = run(inbox.count())
    # second run: everything crawled recently → skipped; inbox stable
    rep2 = run(engine.expand(["https://gdg.org/"], max_pages=10))
    assert rep2.pages_fetched == 0 and rep2.pages_skipped >= 1
    assert run(inbox.count()) == first_count
    # graph persisted + reloadable
    reloaded = run(store.load_graph())
    assert reloaded.stats()["total_nodes"] == engine.graph.stats()["total_nodes"]


def test_engine_budget_stops_domain():
    inbox = InMemoryDiscoveryInbox()
    engine = ExpansionEngine(
        _site(),
        inbox,
        checkpoint=InMemoryCheckpointStore(),
        clock=lambda: NOW,
        budget_config=CrawlBudgetConfig(max_pages=1),  # only 1 page per domain
    )
    rep = run(engine.expand(["https://gdg.org/"], max_pages=10))
    assert rep.pages_fetched == 1  # budget stopped gdg.org after 1 page
    assert "gdg.org" in rep.stopped_domains
