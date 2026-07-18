"""CompositeProvider — the multi-provider event discovery engine.

DEPRECATED for search (Phase 3E): search now reads from the Repository via
`DatabaseSearchProvider`; this search-time fan-out is no longer wired into
`get_provider()`. Kept as a valid `EventProvider` for tests/reference and as a possible
manual catalog warm-up tool. Its stages (city-normalize / classify / dedup) already moved
to the ingestion write path in Phase 3C.

Itself an EventProvider, so SearchService (which takes a single provider) is
completely unchanged. Fans out to its sub-providers in parallel, then:
    merge -> canonicalize city -> deduplicate -> rank.

A failing sub-provider degrades to empty results; the others still return.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from app.city import normalize_city
from app.models.event import Event
from app.models.search import SearchQuery
from app.providers.base import EventProvider
from app.providers.classify import classify_category
from app.providers.dedup import deduplicate
from app.providers.ranking import rank

logger = logging.getLogger(__name__)


class CompositeProvider(EventProvider):
    name = "composite"

    def __init__(self, providers: list[EventProvider], *, today: date | None = None) -> None:
        self._providers = list(providers)
        self._today = today  # injectable for deterministic ranking in tests

    async def search(self, query: SearchQuery) -> list[Event]:
        # Fetch with the category filter stripped so sub-providers don't drop events
        # by their raw category; category filtering happens AFTER classification.
        fetch_query = query.model_copy(update={"categories": []})
        results = await asyncio.gather(
            *(self._safe_search(provider, fetch_query) for provider in self._providers)
        )
        merged = [event for result in results for event in result]
        refined = [self._refine(event) for event in merged]
        if query.categories:
            refined = [e for e in refined if e.category in query.categories]
        deduped = deduplicate(refined)
        ranked = rank(deduped, query, self._today)
        logger.info(
            "composite: %d providers -> %d merged -> %d after dedup",
            len(self._providers),
            len(merged),
            len(ranked),
        )
        return ranked

    async def _safe_search(self, provider: EventProvider, query: SearchQuery) -> list[Event]:
        try:
            return await provider.search(query)
        except Exception:
            logger.exception("composite: provider '%s' failed", provider.name)
            return []

    @staticmethod
    def _refine(event: Event) -> Event:
        """Canonicalize city and classify category (both at the boundary)."""
        updates: dict[str, object] = {}
        canonical = normalize_city(event.city)
        if canonical != event.city:
            updates["city"] = canonical
        category = classify_category(event)
        if category != event.category:
            updates["category"] = category
        return event.model_copy(update=updates) if updates else event
