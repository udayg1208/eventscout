"""Search orchestration — the SearchService.

Ties the two seams together with two-tier caching:

    raw text --[parse-cache]--> SearchQuery --[results-cache]--> events

The API route stays thin; all business logic lives here. Dependencies (parser,
provider, caches) are injected so the service is fully unit-testable without any
network or global state.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from app.cache import TTLCache
from app.config import get_settings
from app.models.event import Event
from app.models.search import SearchQuery
from app.parsers import get_query_parser
from app.parsers.base import QueryParser
from app.providers import get_provider
from app.providers.base import EventProvider

logger = logging.getLogger(__name__)


@dataclass
class SearchOutcome:
    query: SearchQuery
    events: list[Event]
    cached: bool  # results-cache hit (provider skipped)
    parse_cached: bool  # parse-cache hit (parser/Gemini skipped)
    elapsed_ms: float


class SearchService:
    def __init__(
        self,
        *,
        parser: QueryParser,
        provider: EventProvider,
        parse_cache: TTLCache[str, SearchQuery],
        results_cache: TTLCache[str, list[Event]],
    ) -> None:
        self._parser = parser
        self._provider = provider
        self._parse_cache = parse_cache
        self._results_cache = results_cache

        # --- lightweight dev observability counters ---
        self._total_requests = 0
        self._parse_lookups = 0
        self._parse_hits = 0
        self._results_lookups = 0
        self._results_hits = 0
        self._provider_calls = 0
        self._total_latency_ms = 0.0

    async def search(self, raw_text: str) -> SearchOutcome:
        """Full pipeline: parse (cached) -> fetch events (cached)."""
        start = time.perf_counter()
        self._total_requests += 1
        logger.info("search: incoming query=%r", raw_text.strip()[:120])

        query, parse_cached = await self._parse(raw_text)
        events, results_cached = await self._fetch(query)

        elapsed_ms = (time.perf_counter() - start) * 1000
        self._total_latency_ms += elapsed_ms
        logger.info(
            "search: done parse_cached=%s results_cached=%s count=%d elapsed_ms=%.1f",
            parse_cached,
            results_cached,
            len(events),
            elapsed_ms,
        )
        return SearchOutcome(
            query=query,
            events=events,
            cached=results_cached,
            parse_cached=parse_cached,
            elapsed_ms=elapsed_ms,
        )

    async def search_by_query(self, query: SearchQuery) -> tuple[list[Event], bool]:
        """Results-cache + provider only (used by the structured endpoint)."""
        return await self._fetch(query)

    # --- stages ---------------------------------------------------------------

    async def _parse(self, raw_text: str) -> tuple[SearchQuery, bool]:
        self._parse_lookups += 1
        key = self._text_key(raw_text)
        cached = self._parse_cache.get(key)
        if cached is not None:
            self._parse_hits += 1
            logger.info("parse-cache HIT -> skipping parser")
            return cached, True
        logger.info("parse-cache MISS -> invoking QueryParser")
        query = await self._parser.parse(raw_text)  # parser logs its own path
        self._parse_cache.set(key, query)
        return query, False

    async def _fetch(self, query: SearchQuery) -> tuple[list[Event], bool]:
        self._results_lookups += 1
        key = self._query_key(query)
        cached = self._results_cache.get(key)
        if cached is not None:
            self._results_hits += 1
            logger.info("results-cache HIT -> skipping provider")
            return cached, True
        logger.info("results-cache MISS -> invoking provider=%s", self._provider.name)
        self._provider_calls += 1
        try:
            events = await self._provider.search(query)
        except Exception:  # degrade, don't crash; do NOT cache a failure
            logger.exception("provider=%s failed; returning empty results", self._provider.name)
            return [], False
        self._results_cache.set(key, events)
        return events, False

    # --- metrics (dev observability) ------------------------------------------

    def metrics(self) -> dict:
        """A snapshot of counters. Gemini/fallback counts are read from the parser
        via getattr, so a non-Gemini parser simply reports 0 (no contract change)."""

        def hit_rate(hits: int, lookups: int) -> float:
            return round(hits / lookups, 4) if lookups else 0.0

        avg_latency = (
            round(self._total_latency_ms / self._total_requests, 2) if self._total_requests else 0.0
        )
        return {
            "total_requests": self._total_requests,
            "parse_cache": {
                "lookups": self._parse_lookups,
                "hits": self._parse_hits,
                "hit_rate": hit_rate(self._parse_hits, self._parse_lookups),
            },
            "results_cache": {
                "lookups": self._results_lookups,
                "hits": self._results_hits,
                "hit_rate": hit_rate(self._results_hits, self._results_lookups),
            },
            "avg_latency_ms": avg_latency,
            "provider_calls": self._provider_calls,
            "gemini_calls": getattr(self._parser, "gemini_calls", 0),
            "fallback_count": getattr(self._parser, "fallback_count", 0),
        }

    # --- cache keys -----------------------------------------------------------

    @staticmethod
    def _text_key(raw_text: str) -> str:
        return " ".join(raw_text.split()).casefold()

    @staticmethod
    def _query_key(query: SearchQuery) -> str:
        # Canonical form: sort the list fields so semantically-equal queries collide.
        data = query.model_dump(mode="json")
        data["keywords"] = sorted(data.get("keywords") or [])
        data["categories"] = sorted(data.get("categories") or [])
        return json.dumps(data, sort_keys=True, ensure_ascii=False)


_search_service: SearchService | None = None


def get_search_service() -> SearchService:
    """Singleton service so the in-memory caches persist across requests."""
    global _search_service
    if _search_service is None:
        ttl = get_settings().cache_ttl_seconds
        _search_service = SearchService(
            parser=get_query_parser(),
            provider=get_provider(),
            parse_cache=TTLCache(ttl),
            results_cache=TTLCache(ttl),
        )
    return _search_service
