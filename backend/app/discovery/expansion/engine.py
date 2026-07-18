"""Expansion Engine (Phase 8C) — grow the Discovery Graph from every page.

    Discovery Inbox → frontier → fetch → extract (links + feeds + calendars + communities + GitHub/
    Notion/Discord/Telegram) → graph (dedup) → priority → frontier … → Discovery Inbox

Reuses D1's fetcher/robots/feed detection/candidate builder and this package's scope/priority/
budget/checkpoint/graph. Every crawled page adds nodes + edges and enqueues in-scope links; every
discovered source (feed/calendar/community/platform page) becomes a Discovery Inbox candidate
(`discovered_by="expansion"`, `status=NEW`). Bounded by scope + budget + depth. HTML only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from app.discovery.candidates import build_candidate
from app.discovery.expansion.budget import BudgetTracker
from app.discovery.expansion.checkpoint import CheckpointStore, InMemoryCheckpointStore
from app.discovery.expansion.crawler import ExpansionCrawler
from app.discovery.expansion.dedup import canonicalize, node_key
from app.discovery.expansion.extractor import extract
from app.discovery.expansion.frontier import ExpansionFrontier
from app.discovery.expansion.graph import ExpansionGraph
from app.discovery.expansion.models import (
    DEFAULT_CRAWL_BUDGET,
    CrawlBudgetConfig,
    EdgeType,
    ExpansionReport,
    GraphNode,
    NodeType,
)
from app.discovery.expansion.priority import score_url
from app.discovery.expansion.scope import ScopeConfig, evaluate_scope, is_crawlable
from app.discovery.expansion.store import ExpansionStore
from app.discovery.feeds import detect_feeds
from app.discovery.models import (
    CandidateSource,
    ConfidenceSignals,
    DiscoveryStatus,
    FeedType,
)
from app.discovery.robots import RobotsCache
from app.discovery.signals import collect_signals
from app.discovery.store import DiscoveryInbox
from app.discovery.urls import normalize_url, registrable_domain

_NOT_A_CANDIDATE = {FeedType.XML_SITEMAP, FeedType.UNKNOWN}
_MAX_LINKS_PER_PAGE = 120  # deterministic cap so one page can't flood the frontier

_FEED_TO_NODE = {
    FeedType.RSS: NodeType.RSS,
    FeedType.ATOM: NodeType.RSS,
    FeedType.JSON_FEED: NodeType.RSS,
    FeedType.ICS: NodeType.ICS,
    FeedType.GOOGLE_CALENDAR: NodeType.CALENDAR,
    FeedType.JSONLD_EVENT: NodeType.JSONLD,
    FeedType.MICRODATA_EVENT: NodeType.JSONLD,
    FeedType.OPENGRAPH_EVENT: NodeType.JSONLD,
    FeedType.EVENT_SITEMAP: NodeType.SITEMAP,
}


def _org_hint(domain: str) -> str:
    label = domain.split(".")[0]
    return label.upper() if len(label) <= 4 else label.capitalize()


class ExpansionEngine:
    def __init__(
        self,
        fetcher,
        inbox: DiscoveryInbox,
        *,
        graph: ExpansionGraph | None = None,
        scope_config: ScopeConfig | None = None,
        budget_config: CrawlBudgetConfig = DEFAULT_CRAWL_BUDGET,
        checkpoint: CheckpointStore | None = None,
        store: ExpansionStore | None = None,
        domain_trust: dict[str, float] | None = None,
        refresh_after_hours: float = 24.0,
        min_interval: float = 0.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._inbox = inbox
        self._graph = graph or ExpansionGraph()
        self._scope = scope_config or ScopeConfig()
        self._store = store
        self._domain_trust = domain_trust or {}
        self._clock = clock
        self._checkpoint = checkpoint or InMemoryCheckpointStore()
        budget = BudgetTracker(budget_config, clock=clock)
        self._budget = budget
        crawler_kwargs = {
            "refresh_after_hours": refresh_after_hours,
            "min_interval": min_interval,
            "clock": clock,
        }
        if sleep is not None:
            crawler_kwargs["sleep"] = sleep
        self._crawler = ExpansionCrawler(
            fetcher, RobotsCache(fetcher), budget, self._checkpoint, **crawler_kwargs
        )

    # ------------------------------ candidate + node helpers ------------------------------

    def _source_candidate(
        self, url: str, feed_type: FeedType, *, node_type: NodeType, now
    ) -> CandidateSource:
        domain = registrable_domain(url)
        return CandidateSource(
            key=url,
            url=url,
            domain=domain,
            feed_type=feed_type,
            title=None,
            organization=_org_hint(domain),
            signals=ConfidenceSignals(),
            discovery_method="expansion",
            discovery_path=[],
            discovered_by="expansion",
            classification=node_type.value,
            status=DiscoveryStatus.NEW,
            crawl_timestamp=now,
            first_seen_at=now,
            last_seen_at=now,
        )

    async def _upsert_source(
        self, url, feed_type, node_type, page_key, edge_type, report, counter, now
    ) -> None:
        canonical = canonicalize(url)
        if not canonical:
            return
        node = GraphNode(
            key=node_key(node_type, canonical),
            node_type=node_type,
            url=canonical,
            domain=registrable_domain(canonical),
            first_seen_at=now,
            last_seen_at=now,
        )
        _, added = self._graph.upsert_node(node)
        report.nodes_added += added
        report.edges_added += self._graph.add_edge(page_key, node.key, edge_type)
        outcome = await self._inbox.upsert(
            self._source_candidate(canonical, feed_type, node_type=node_type, now=now)
        )
        report.candidates_inserted += outcome == "inserted"
        report.candidates_updated += outcome == "updated"
        setattr(report, counter, getattr(report, counter) + 1)

    # ------------------------------ per-page processing ------------------------------

    async def _process_page(self, result, item, frontier, report) -> None:
        now = self._clock()
        canonical = canonicalize(result.url) or result.url
        domain = registrable_domain(canonical)

        # PAGE + DOMAIN nodes
        page_key = node_key(NodeType.PAGE, canonical)
        _, a = self._graph.upsert_node(
            GraphNode(
                page_key, NodeType.PAGE, canonical, domain, first_seen_at=now, last_seen_at=now
            )
        )
        report.nodes_added += a
        dom_key = node_key(NodeType.DOMAIN, canonical)
        _, a = self._graph.upsert_node(
            GraphNode(dom_key, NodeType.DOMAIN, f"https://{domain}", domain, first_seen_at=now)
        )
        report.nodes_added += a
        report.edges_added += self._graph.add_edge(dom_key, page_key, EdgeType.OWNS)

        ex = extract(result)

        # (1) D1 structured detection on the page → candidates + typed nodes
        detections = detect_feeds(result)
        signals = collect_signals(result, detections, ex.page_links)
        for det in detections:
            if det.feed_type in _NOT_A_CANDIDATE:
                continue
            cand = build_candidate(
                result=result, detection=det, signals=signals, discovery_path=[item.url], now=now
            )
            cand.discovered_by = "expansion"
            outcome = await self._inbox.upsert(cand)
            report.candidates_inserted += outcome == "inserted"
            report.candidates_updated += outcome == "updated"
            ntype = _FEED_TO_NODE.get(det.feed_type, NodeType.JSONLD)
            fkey = node_key(ntype, canonicalize(det.url) or det.url)
            _, a = self._graph.upsert_node(
                GraphNode(
                    fkey,
                    ntype,
                    det.url,
                    registrable_domain(det.url),
                    det.title,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
            report.nodes_added += a
            edge = (
                EdgeType.CONTAINS_CALENDAR
                if ntype in (NodeType.ICS, NodeType.CALENDAR)
                else (EdgeType.CONTAINS_FEED if ntype is NodeType.RSS else EdgeType.CONTAINS_EVENTS)
            )
            report.edges_added += self._graph.add_edge(page_key, fkey, edge)
            if ntype in (NodeType.ICS, NodeType.CALENDAR):
                report.calendars_found += 1
            else:
                report.feeds_found += 1

        # (2) feed <link rel=alternate> URLs → RSS candidates + nodes
        for feed_url, ftype in ex.feeds:
            await self._upsert_source(
                feed_url,
                ftype,
                _FEED_TO_NODE.get(ftype, NodeType.RSS),
                page_key,
                EdgeType.CONTAINS_FEED,
                report,
                "feeds_found",
                now,
            )
        # (3) calendars (.ics / google calendar)
        for cal in ex.calendars:
            ft = FeedType.GOOGLE_CALENDAR if "calendar.google" in cal else FeedType.ICS
            await self._upsert_source(
                cal,
                ft,
                NodeType.CALENDAR,
                page_key,
                EdgeType.CONTAINS_CALENDAR,
                report,
                "calendars_found",
                now,
            )
        # (4) platform links → typed nodes + SEARCH_RESULT candidates
        for url in ex.github:
            await self._upsert_source(
                url,
                FeedType.SEARCH_RESULT,
                NodeType.GITHUB,
                page_key,
                EdgeType.REFERENCES,
                report,
                "github_found",
                now,
            )
        for url in ex.notion:
            await self._upsert_source(
                url,
                FeedType.SEARCH_RESULT,
                NodeType.NOTION,
                page_key,
                EdgeType.REFERENCES,
                report,
                "notion_found",
                now,
            )
        for url in ex.discord:
            await self._upsert_source(
                url,
                FeedType.SEARCH_RESULT,
                NodeType.DISCORD,
                page_key,
                EdgeType.REFERENCES,
                report,
                "discord_found",
                now,
            )
        for url in ex.telegram:
            await self._upsert_source(
                url,
                FeedType.SEARCH_RESULT,
                NodeType.TELEGRAM,
                page_key,
                EdgeType.REFERENCES,
                report,
                "telegram_found",
                now,
            )
        for url in ex.blogs:
            await self._upsert_source(
                url,
                FeedType.SEARCH_RESULT,
                NodeType.BLOG,
                page_key,
                EdgeType.REFERENCES,
                report,
                "blogs_found",
                now,
            )

        # (5) recursion: in-scope links → priority → frontier; out-of-scope → reference node
        for link in ex.page_links[:_MAX_LINKS_PER_PAGE]:
            ld = registrable_domain(link)
            decision, _reason = evaluate_scope(link, depth=item.depth + 1, config=self._scope)
            if is_crawlable(decision):
                pr = score_url(
                    link,
                    trusted_domain=(ld in self._scope.trusted_external),
                    domain_trust=self._domain_trust.get(ld, 0.0),
                )
                if frontier.offer(
                    link, depth=item.depth + 1, from_domain=domain, priority=pr.score
                ):
                    lk = canonicalize(link) or link
                    _, a = self._graph.upsert_node(
                        GraphNode(
                            node_key(NodeType.PAGE, lk), NodeType.PAGE, lk, ld, first_seen_at=now
                        )
                    )
                    report.nodes_added += a
                    report.edges_added += self._graph.add_edge(
                        page_key, node_key(NodeType.PAGE, lk), EdgeType.LINKS_TO
                    )
            else:
                if decision.value == "block":
                    frontier.mark_blocked(link)
                dk = node_key(NodeType.DOMAIN, f"https://{ld}")
                _, a = self._graph.upsert_node(
                    GraphNode(dk, NodeType.DOMAIN, f"https://{ld}", ld, first_seen_at=now)
                )
                report.nodes_added += a
                report.edges_added += self._graph.add_edge(page_key, dk, EdgeType.REFERENCES)

    # ------------------------------ the loop ------------------------------

    async def expand(self, seeds: list[str], *, max_pages: int = 50) -> ExpansionReport:
        report = ExpansionReport(seeds=len(seeds))
        existing = await self._inbox.list(limit=100_000)
        frontier = ExpansionFrontier(
            known_urls=[]
        )  # seeds must be crawlable even if already inbox'd
        for seed in seeds:
            norm = normalize_url(seed) or seed
            self._scope.seed_domains.add(registrable_domain(norm))
            frontier.offer(norm, depth=0, from_domain=registrable_domain(norm), priority=1.0)
        _ = existing  # inbox is seeded elsewhere; upsert dedups re-discovered candidates

        pages = 0
        while pages < max_pages:
            item = frontier.next_item()
            if item is None:
                break
            domain = registrable_domain(item.url)
            outcome = await self._crawler.fetch(item.url, domain=domain, depth=item.depth)
            if not outcome.fetched:
                report.pages_skipped += 1
                reason = outcome.skip_reason or ""
                if reason.startswith("robots"):
                    frontier.mark_blocked(item.url)
                elif reason.startswith("budget") or reason.startswith("checkpoint"):
                    frontier.mark_deferred(item.url)
                else:
                    frontier.mark_failed(item.url)
                continue
            pages += 1
            report.pages_fetched += 1
            frontier.mark_visited(item.url)
            await self._process_page(outcome.result, item, frontier, report)

        stats = self._graph.stats()
        report.nodes_by_type = stats["nodes_by_type"]
        report.edges_by_type = stats["edges_by_type"]
        report.frontier = frontier.stats()
        report.stopped_domains = self._budget.stopped_domains()
        if self._store is not None:
            await self._store.save_graph(self._graph)
            await self._store.save_report(report.as_dict())
        return report

    @property
    def graph(self) -> ExpansionGraph:
        return self._graph
