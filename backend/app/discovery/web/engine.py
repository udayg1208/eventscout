"""Web Discovery Engine (Phase 8B) — real search → Discovery Inbox.

    generate queries → (prioritize) → execute (cached, rate-limited) → normalize → dedupe
                     → score → Discovery Inbox

Wires a REAL `WebSearchProvider` into the reused D3 search-discovery pipeline (query builder →
parser → ranking → candidate builder → inbox) and reuses 8A (gap analysis + query optimizer) to
prioritize which queries to run first and drop historically-bad ones. Bounded by a crawl budget,
served from a 24h cache, and rate-limited. Output stops at the Discovery Inbox — nothing is
onboarded or promoted.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.discovery.optimization import DiscoveryRecord, find_gaps, optimize_queries
from app.discovery.search import (
    DEFAULT_SPEC,
    Frontier,
    QuerySpec,
    build_queries,
    build_search_candidate,
    score_source,
)
from app.discovery.store import DiscoveryInbox
from app.discovery.web.cache import SearchCache
from app.discovery.web.interfaces import ProviderError, WebSearchProvider
from app.discovery.web.normalizer import dedupe_across, normalize_results
from app.discovery.web.rate_limit import Budget, RateLimiter

logger = logging.getLogger("discovery.web")


@dataclass
class WebDiscoveryReport:
    provider: str
    queries_generated: int
    queries_executed: int
    cache_hits: int
    cache_misses: int
    provider_errors: int
    results_collected: int
    unique_results: int
    inserted: int
    updated: int
    skipped_known: int
    below_threshold: int
    new_domains: list[str] = field(default_factory=list)


class WebDiscoveryEngine:
    def __init__(
        self,
        provider: WebSearchProvider,
        inbox: DiscoveryInbox,
        *,
        cache: SearchCache | None = None,
        rate_limiter: RateLimiter | None = None,
        budget: Budget | None = None,
        min_score: float = 0.3,
        results_per_query: int = 10,
        history: list[DiscoveryRecord] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._provider = provider
        self._inbox = inbox
        self._cache = cache
        self._rate = rate_limiter
        self._budget = budget
        self._min_score = min_score
        self._per_query = results_per_query
        self._history = history or []
        self._clock = clock

    def _prioritize(self, queries: list[str]) -> list[str]:
        """Reuse 8A: drop historically-retired queries, float gap-filling queries to the front."""
        if not self._history:
            return queries
        opt = optimize_queries(self._history)
        retire = {s.query for s in opt.stats if s.recommendation == "retire"} | set(opt.zero_yield)
        gap_terms = set()
        for g in find_gaps(self._history):
            gap_terms.add(g.technology.lower())
            if g.scope.startswith("city:"):
                gap_terms.add(g.scope.split(":", 1)[1].lower())
        kept = [q for q in queries if q not in retire]
        index = {q: i for i, q in enumerate(kept)}
        return sorted(
            kept,
            key=lambda q: (0 if any(t in q.lower() for t in gap_terms) else 1, index[q]),
        )

    async def _seed_frontier(self) -> Frontier:
        existing = await self._inbox.list(limit=100_000)
        return Frontier(
            known_urls=[c.url for c in existing], known_domains=[c.domain for c in existing]
        )

    async def _search_cached(self, query: str) -> tuple[list, bool, bool]:
        """Return (results, cache_hit, provider_error)."""
        if self._cache is not None:
            cached = self._cache.get(self._provider.name, query)
            if cached is not None:
                return cached, True, False
        if self._rate is not None:
            await self._rate.acquire(self._provider.name)
        try:
            results = await self._provider.search(query, limit=self._per_query)
        except ProviderError as exc:
            logger.warning("web-discovery: provider error on %r: %s", query, exc)
            return [], False, True
        if self._cache is not None:
            self._cache.put(self._provider.name, query, results)
        return results, False, False

    async def run(self, spec: QuerySpec = DEFAULT_SPEC) -> WebDiscoveryReport:
        queries = self._prioritize(build_queries(spec))
        frontier = await self._seed_frontier()

        executed = hits = misses = errors = 0
        collected = []
        for query in queries:
            if self._budget is not None and not self._budget.consume():
                break
            results, hit, err = await self._search_cached(query)
            executed += 1
            hits += hit
            misses += not hit and not err
            errors += err
            collected.extend(normalize_results(results, query))

        deduped = dedupe_across(collected)
        inserted = updated = skipped = below = 0
        domains: set[str] = set()
        for parsed in deduped:
            if not frontier.is_new(parsed.url):
                skipped += 1
                continue
            frontier.record(parsed.url)
            score = score_source(parsed)
            if score.total < self._min_score:
                below += 1
                continue
            candidate = build_search_candidate(parsed, score, now=self._clock())
            outcome = await self._inbox.upsert(candidate)
            inserted += outcome == "inserted"
            updated += outcome == "updated"
            domains.add(parsed.domain)

        return WebDiscoveryReport(
            provider=self._provider.name,
            queries_generated=len(queries),
            queries_executed=executed,
            cache_hits=hits,
            cache_misses=misses,
            provider_errors=errors,
            results_collected=len(collected),
            unique_results=len(deduped),
            inserted=inserted,
            updated=updated,
            skipped_known=skipped,
            below_threshold=below,
            new_domains=sorted(domains),
        )
