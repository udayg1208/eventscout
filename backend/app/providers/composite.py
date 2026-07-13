"""CompositeProvider — the multi-provider event discovery engine.

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
from app.providers.dedup import deduplicate
from app.providers.ranking import rank

logger = logging.getLogger(__name__)


class CompositeProvider(EventProvider):
    name = "composite"

    def __init__(self, providers: list[EventProvider], *, today: date | None = None) -> None:
        self._providers = list(providers)
        self._today = today  # injectable for deterministic ranking in tests

    async def search(self, query: SearchQuery) -> list[Event]:
        results = await asyncio.gather(
            *(self._safe_search(provider, query) for provider in self._providers)
        )
        merged = [event for result in results for event in result]
        normalized = [self._canonical_city(event) for event in merged]
        deduped = deduplicate(normalized)
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
    def _canonical_city(event: Event) -> Event:
        canonical = normalize_city(event.city)
        if canonical == event.city:
            return event
        return event.model_copy(update={"city": canonical})
