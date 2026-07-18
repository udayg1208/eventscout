"""Retrieval Pipeline — plan → retrieve → fuse → load → filter → rank.

Ties the retrieval components together and produces the final ranked `list[Event]`. Events
are loaded from the Repository only *after* fusion. Ranking is the existing engine, used
unchanged. Search metrics are recorded per call.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import date

from app.models.event import Event
from app.models.search import SearchQuery
from app.providers.ranking import rank
from app.search.filters import apply_filters
from app.search.hybrid import HybridRetriever
from app.search.metrics import SearchMetrics
from app.search.planner import QueryPlanner
from app.storage.repository import EventRepository


class RetrievalPipeline:
    def __init__(
        self,
        *,
        planner: QueryPlanner,
        hybrid: HybridRetriever,
        repo: EventRepository,
        metrics: SearchMetrics,
        candidate_limit: int,
        clock: Callable[[], date] = date.today,
    ) -> None:
        self._planner = planner
        self._hybrid = hybrid
        self._repo = repo
        self._metrics = metrics
        self._limit = candidate_limit
        self._clock = clock

    async def search(self, query: SearchQuery) -> list[Event]:
        today = self._clock()
        plan = self._planner.plan(query)

        # --- retrieve (concurrently) + fuse ---
        started = time.perf_counter()
        candidate_sets = await asyncio.gather(
            *(retriever.retrieve(query, self._limit) for retriever in plan.retrievers)
        )
        fused = self._hybrid.fuse(candidate_sets, limit=self._limit)
        retrieval_ms = (time.perf_counter() - started) * 1000

        # --- load events AFTER fusion, then structured-filter ---
        keys = [candidate.event_key for candidate in fused]
        stored = await self._repo.get_many(keys)
        events = [stored[key].event for key in keys if key in stored]
        filtered = apply_filters(events, query, today)

        # --- rank (existing engine, unchanged) ---
        ranked_started = time.perf_counter()
        ranked = rank(filtered, query, today)
        ranking_ms = (time.perf_counter() - ranked_started) * 1000

        self._metrics.record(
            retrieval_ms=retrieval_ms,
            ranking_ms=ranking_ms,
            candidates_by_source={cs.source: len(cs) for cs in candidate_sets},
            fused_count=len(fused),
            result_count=len(ranked),
        )
        return ranked
