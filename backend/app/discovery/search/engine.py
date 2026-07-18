"""Search Discovery Engine (Phase 6F / D3) — the orchestrator.

Pipeline: Generate Queries → Search → Parse → Rank → Deduplicate → Discovery Inbox.

It turns a `QuerySpec` into search queries, runs them through a `SearchProvider`, normalizes and
de-duplicates the results, scores each discovered source deterministically, and upserts the ones
that clear a threshold into the Discovery Inbox as `SEARCH_RESULT` candidates (`discovered_by=
"search"`, `status=NEW`). It **discovers sources only** — nothing is crawled, ingested, or written
to the catalog. The frontier is seeded from the existing inbox so known pages are never re-added.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.city import detect_city
from app.discovery.models import (
    CandidateSource,
    ConfidenceSignals,
    DiscoveryStatus,
    FeedType,
)
from app.discovery.search.dedup import dedupe
from app.discovery.search.frontier import Frontier
from app.discovery.search.parser import ParsedResult, parse_results
from app.discovery.search.query_builder import DEFAULT_SPEC, QuerySpec, build_queries
from app.discovery.search.ranking import DiscoveryScore, score_source
from app.discovery.search.search import SearchProvider
from app.discovery.store import DiscoveryInbox

logger = logging.getLogger("discovery.search")

_SEED_LIMIT = 100_000  # how many existing candidates to seed the frontier with (cross-run dedup)


@dataclass
class SearchDiscoveryReport:
    queries: int
    results_found: int  # parsed rows across all queries (before URL dedup)
    unique_results: int  # after collapsing identical URLs
    duplicates_removed: int
    below_threshold: int  # scored under min_score → not inbox'd
    skipped_known: int  # already in the inbox from a prior run
    accepted: int  # new + above threshold
    inserted: int
    updated: int
    discovered_domains: list[str]
    frontier: dict[str, int] = field(default_factory=dict)


def _org_hint(domain: str, title: str | None) -> str:
    label = domain.split(".")[0]
    return label.upper() if len(label) <= 4 else label.capitalize()


def build_search_candidate(
    parsed: ParsedResult, score: DiscoveryScore, *, now: datetime
) -> CandidateSource:
    """Assemble a Discovery Inbox candidate from a scored search result.

    The per-dimension confidences are transparent aggregates of the ranking signals (same contract
    as D1/D2). `structured_data_score` stays 0 — search metadata cannot confirm structured data;
    that is only known once the page is actually crawled by D1/D2.
    """
    india_refs = 2 if score.india >= 1.0 else (1 if score.india >= 0.5 else 0)
    signals = ConfidenceSignals(
        tech_keyword_count=round(score.technology * 3),
        india_reference_count=india_refs,
        has_organizer=score.is_meetup or score.known_community,
    )
    professional = min(
        1.0,
        0.5 * float(score.is_meetup)
        + 0.3 * float(score.is_conference)
        + 0.2 * float(score.known_community),
    )
    return CandidateSource(
        key=parsed.url,  # search sources key by normalized URL (each page a distinct source)
        url=parsed.url,
        domain=parsed.domain,
        feed_type=FeedType.SEARCH_RESULT,
        title=parsed.title or None,
        organization=_org_hint(parsed.domain, parsed.title),
        country="India" if score.india >= 0.5 else None,
        city=detect_city(parsed.title, parsed.snippet),
        technology_confidence=score.technology,
        india_confidence=score.india,
        professional_confidence=round(professional, 3),
        structured_data_score=signals.structured_count(),
        signals=signals,
        discovery_method="search-discovery",
        discovery_path=[parsed.query],
        discovered_by="search",
        search_query=parsed.query,
        search_rank=parsed.rank,
        search_engine=parsed.engine,
        status=DiscoveryStatus.NEW,
        crawl_timestamp=now,
        first_seen_at=now,
        last_seen_at=now,
    )


class SearchDiscoveryEngine:
    def __init__(
        self,
        provider: SearchProvider,
        inbox: DiscoveryInbox,
        *,
        min_score: float = 0.3,
        results_per_query: int = 10,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._provider = provider
        self._inbox = inbox
        self._min_score = min_score
        self._per_query = results_per_query
        self._clock = clock

    async def _seed_frontier(self) -> Frontier:
        existing = await self._inbox.list(limit=_SEED_LIMIT)
        return Frontier(
            known_urls=[c.url for c in existing],
            known_domains=[c.domain for c in existing],
        )

    async def run(self, spec: QuerySpec = DEFAULT_SPEC) -> SearchDiscoveryReport:
        queries = build_queries(spec)
        frontier = await self._seed_frontier()

        # Generate → Search → Parse (gather every query's results)
        parsed_all: list[ParsedResult] = []
        for query in queries:
            results = await self._provider.search(query, limit=self._per_query)
            parsed_all.extend(parse_results(results, query))

        # Deduplicate identical pages surfaced by different queries
        deduped = dedupe(parsed_all)
        duplicates_removed = len(parsed_all) - len(deduped)

        below = skipped_known = accepted = inserted = updated = 0
        domains: set[str] = set()

        # Rank → threshold → frontier novelty → Discovery Inbox
        for parsed in deduped:
            if not frontier.is_new(parsed.url):
                skipped_known += 1
                continue
            frontier.record(parsed.url)
            score = score_source(parsed)
            if score.total < self._min_score:
                below += 1
                continue
            candidate = build_search_candidate(parsed, score, now=self._clock())
            outcome = await self._inbox.upsert(candidate)
            accepted += 1
            inserted += outcome == "inserted"
            updated += outcome == "updated"
            domains.add(parsed.domain)

        logger.info(
            "search-discovery: queries=%d parsed=%d unique=%d accepted=%d",
            len(queries),
            len(parsed_all),
            len(deduped),
            accepted,
        )
        return SearchDiscoveryReport(
            queries=len(queries),
            results_found=len(parsed_all),
            unique_results=len(deduped),
            duplicates_removed=duplicates_removed,
            below_threshold=below,
            skipped_known=skipped_known,
            accepted=accepted,
            inserted=inserted,
            updated=updated,
            discovered_domains=sorted(domains),
            frontier=frontier.stats(),
        )
