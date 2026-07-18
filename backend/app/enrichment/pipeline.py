"""Enrichment Pipeline — enrich the catalog and expose similarity.

    Normalized Event → Topic → Technology → Skill → Audience → Difficulty → Career
    → Summary → Metadata Store → Event Similarity

Reads the frozen Repository, enriches each event deterministically, persists enrichment in
the (separate) AI Metadata Store, and builds an `EventSimilarity` over the results. Modifies
nothing frozen; no provider/search/repository is aware of it.
"""

from __future__ import annotations

import logging

from app.enrichment.enricher import DeterministicEnricher, Enricher
from app.enrichment.similarity import EventSimilarity
from app.enrichment.store import EnrichmentStore, InMemoryEnrichmentStore
from app.entities.builder import GraphBuilder
from app.entities.graph import GraphStore
from app.storage.models import SearchCriteria, StoredEvent
from app.storage.repository import EventRepository

logger = logging.getLogger("enrichment.pipeline")


class EnrichmentPipeline:
    def __init__(
        self,
        store: EnrichmentStore | None = None,
        *,
        enricher: Enricher | None = None,
    ) -> None:
        self._store = store or InMemoryEnrichmentStore()
        self._enricher = enricher or DeterministicEnricher()
        self._events: dict[str, StoredEvent] = {}
        self._graph: GraphStore | None = None

    @property
    def store(self) -> EnrichmentStore:
        return self._store

    def enrich_events(self, events: list[StoredEvent], *, graph: GraphStore | None = None) -> int:
        """Enrich a set of stored events and persist the results. Returns the count."""
        self._events = {s.key: s for s in events}
        self._graph = graph if graph is not None else GraphBuilder().build(events)
        enrichments = [self._enricher.enrich(s.key, s.event) for s in events]
        self._store.save_many(enrichments)
        logger.info("enriched %d events", len(enrichments))
        return len(enrichments)

    async def run(self, repo: EventRepository) -> int:
        """Enrich the whole active catalog from the Repository."""
        events = [s async for s in repo.iterate(SearchCriteria(active_only=True))]
        return self.enrich_events(events)

    def similarity(self) -> EventSimilarity:
        """A similarity query engine over the current enrichment + graph."""
        return EventSimilarity(self._store.all(), self._events, graph=self._graph)
