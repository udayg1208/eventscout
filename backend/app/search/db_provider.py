"""DatabaseSearchProvider — the catalog-backed search engine (Phase 4B retrieval pipeline).

Implements the frozen `EventProvider` interface, so `SearchService`, the HTTP API, and the
frontend are unchanged — only what `get_provider()` returns changes. It never fetches from
live providers; every search runs through the retrieval pipeline:

  SearchQuery → (cache) → Query Planner → Retrievers (keyword / structured / entity)
              → Hybrid RRF fusion → load events → structured filter → Ranking → results

The Search Index (SQLite FTS5) and the Entity Graph are **projections** of the catalog,
built lazily from the Repository (the source of truth) on first search and rebuilt on
`invalidate()`. Semantic retrieval is interface-only (not emitted by the planner yet).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import date

from app.config import get_settings
from app.entities.builder import GraphBuilder
from app.entities.queries import EntityQueries
from app.entities.resolution import EntityResolver
from app.models.event import Event
from app.models.search import SearchQuery
from app.providers.base import EventProvider
from app.search.analytics import SearchAnalytics
from app.search.cache import InMemorySearchCache, SearchCache, search_cache_key
from app.search.criteria import to_criteria  # re-exported for callers/tests
from app.search.hybrid import HybridRetriever
from app.search.index import IndexDocument, SearchIndex, SQLiteFTS5Index
from app.search.metrics import SearchMetrics
from app.search.pipeline import RetrievalPipeline
from app.search.planner import QueryPlanner
from app.search.retrievers import EntityRetriever, KeywordRetriever, StructuredRetriever
from app.storage.models import SearchCriteria
from app.storage.repository import EventRepository

__all__ = ["DatabaseSearchProvider", "build_search_provider", "to_criteria"]

logger = logging.getLogger("search.database")


class DatabaseSearchProvider(EventProvider):
    name = "database"

    def __init__(
        self,
        repo: EventRepository,
        *,
        cache: SearchCache | None = None,
        analytics: SearchAnalytics | None = None,
        metrics: SearchMetrics | None = None,
        index: SearchIndex | None = None,
        candidate_limit: int = 500,
        clock: Callable[[], date] = date.today,
    ) -> None:
        self._repo = repo
        self._cache = cache
        self._analytics = analytics or SearchAnalytics()
        self._metrics = metrics or SearchMetrics()
        self._index = index or SQLiteFTS5Index()
        self._limit = candidate_limit
        self._clock = clock
        self._pipeline: RetrievalPipeline | None = None
        self._ready = False

    @property
    def analytics(self) -> SearchAnalytics:
        return self._analytics

    @property
    def metrics(self) -> SearchMetrics:
        return self._metrics

    async def search(self, query: SearchQuery) -> list[Event]:
        started = time.perf_counter()
        key = search_cache_key(query)

        if self._cache is not None:
            cached = await self._cache.get(key)
            if cached is not None:
                self._record(query, cached, started, cache_hit=True)
                return cached

        await self._ensure_projections()
        assert self._pipeline is not None
        ranked = await self._pipeline.search(query)

        if self._cache is not None:
            await self._cache.set(key, ranked)
        self._record(query, ranked, started, cache_hit=False)
        return ranked

    async def refresh(self) -> None:
        """Rebuild the index + entity-graph projections from the catalog."""
        self._ready = False
        await self._ensure_projections()

    async def invalidate(self) -> None:
        """Drop cached results and mark projections stale (rebuilt on next search).
        Call after an ingestion run mutates the catalog."""
        if self._cache is not None:
            await self._cache.clear()
        self._ready = False

    # --- projections (built from the Repository, the source of truth) ---

    async def _ensure_projections(self) -> None:
        if self._ready:
            return
        stored = [s async for s in self._repo.iterate(SearchCriteria(active_only=True))]

        documents = [
            IndexDocument(
                key=s.key,
                title=s.event.title,
                description=s.event.description or "",
                city=s.event.city or "",
            )
            for s in stored
        ]
        await self._index.rebuild(documents)
        graph = GraphBuilder(resolver=EntityResolver()).build(stored)
        self._pipeline = self._build_pipeline(graph)
        self._ready = True
        logger.info("search projections built events=%d indexed=%d", len(stored), len(documents))

    def _build_pipeline(self, graph) -> RetrievalPipeline:
        keyword = KeywordRetriever(self._index)
        structured = StructuredRetriever(self._repo, clock=self._clock)
        entity = EntityRetriever(graph, EntityResolver())
        planner = QueryPlanner(
            keyword=keyword,
            structured=structured,
            entity=entity,
            entity_queries=EntityQueries(graph, EntityResolver()),
        )
        return RetrievalPipeline(
            planner=planner,
            hybrid=HybridRetriever(),
            repo=self._repo,
            metrics=self._metrics,
            candidate_limit=self._limit,
            clock=self._clock,
        )

    def _record(
        self, query: SearchQuery, results: list[Event], started: float, *, cache_hit: bool
    ) -> None:
        latency_ms = (time.perf_counter() - started) * 1000
        self._analytics.record(
            query, result_count=len(results), latency_ms=latency_ms, cache_hit=cache_hit
        )


def build_search_provider() -> DatabaseSearchProvider:
    """Construct the production read-path provider over the shared catalog."""
    from app.catalog import get_repository  # lazy: avoid an import cycle at module load

    settings = get_settings()
    return DatabaseSearchProvider(
        get_repository(),
        cache=InMemorySearchCache(settings.search_cache_ttl_seconds),
        candidate_limit=settings.search_candidate_limit,
    )
