"""AI Metadata Store — enrichment persisted separately from the Event.

Keyed by event key, storage-independent. The `Event` model is never modified; a future
Opportunity model reads enrichment straight from here. In-memory today; a SQLite/Postgres
backend implements the same interface later.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.enrichment.models import EventEnrichment


class EnrichmentStore(ABC):
    @abstractmethod
    def get(self, key: str) -> EventEnrichment | None: ...

    @abstractmethod
    def save(self, enrichment: EventEnrichment) -> None: ...

    @abstractmethod
    def save_many(self, enrichments: list[EventEnrichment]) -> None: ...

    @abstractmethod
    def all(self) -> dict[str, EventEnrichment]: ...

    @abstractmethod
    def count(self) -> int: ...


class InMemoryEnrichmentStore(EnrichmentStore):
    def __init__(self) -> None:
        self._store: dict[str, EventEnrichment] = {}

    def get(self, key: str) -> EventEnrichment | None:
        return self._store.get(key)

    def save(self, enrichment: EventEnrichment) -> None:
        self._store[enrichment.key] = enrichment

    def save_many(self, enrichments: list[EventEnrichment]) -> None:
        for enrichment in enrichments:
            self._store[enrichment.key] = enrichment

    def all(self) -> dict[str, EventEnrichment]:
        return dict(self._store)

    def count(self) -> int:
        return len(self._store)
