"""Retrievers — each turns a query into a bounded `CandidateSet`, independently.

A retriever knows only its own backing store (index / repository / entity graph); it never
knows about other retrievers. All return event keys + scores, never `Event` objects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import date

from app.entities.graph import GraphStore
from app.entities.queries import EntityQueries
from app.entities.resolution import EntityResolver
from app.models.search import SearchQuery
from app.search.candidates import Candidate, CandidateSet
from app.search.criteria import to_criteria
from app.search.index import SearchIndex
from app.storage.repository import EventRepository


class Retriever(ABC):
    name: str = "retriever"

    @abstractmethod
    async def retrieve(self, query: SearchQuery, limit: int) -> CandidateSet:
        """Return up to `limit` candidates, best-first."""


class KeywordRetriever(Retriever):
    """Full-text retrieval over the Search Index (title/description/city/organizer/tags)."""

    name = "keyword"

    def __init__(self, index: SearchIndex) -> None:
        self._index = index

    async def retrieve(self, query: SearchQuery, limit: int) -> CandidateSet:
        if not query.keywords:
            return CandidateSet.empty(self.name)
        text = " ".join(query.keywords)
        hits = await self._index.search(text, limit=limit)
        return CandidateSet(
            source=self.name,
            candidates=[Candidate(key, score, self.name) for key, score in hits],
        )


class StructuredRetriever(Retriever):
    """Filtered retrieval from the Repository (the source of truth), freshness-ordered.
    Supports city / category / date / free today; online / provider are future-safe (not
    expressible on the frozen SearchQuery)."""

    name = "structured"

    def __init__(self, repo: EventRepository, *, clock: Callable[[], date] = date.today) -> None:
        self._repo = repo
        self._clock = clock

    async def retrieve(self, query: SearchQuery, limit: int) -> CandidateSet:
        criteria = to_criteria(query, today=self._clock(), limit=limit)
        page = await self._repo.search(criteria)
        # freshness order (soonest first) → descending score by position for RRF stability
        candidates = [
            Candidate(stored.key, 1.0 / (rank + 1), self.name)
            for rank, stored in enumerate(page.items)
        ]
        return CandidateSet(source=self.name, candidates=candidates)


class EntityRetriever(Retriever):
    """Retrieval via the Entity Graph: keywords that resolve to a known organization /
    community / series / venue return that entity's events ("Google events", "GDG")."""

    name = "entity"

    def __init__(self, graph: GraphStore, resolver: EntityResolver | None = None) -> None:
        self._queries = EntityQueries(graph, resolver or EntityResolver())

    async def retrieve(self, query: SearchQuery, limit: int) -> CandidateSet:
        if not query.keywords:
            return CandidateSet.empty(self.name)
        keys: list[str] = []
        seen: set[str] = set()
        for keyword in query.keywords:
            for lookup in (
                self._queries.events_by_organization,
                self._queries.events_by_community,
                self._queries.events_in_series,
                self._queries.events_at_venue,
            ):
                for key in lookup(keyword):
                    if key not in seen:
                        seen.add(key)
                        keys.append(key)
        candidates = [
            Candidate(key, 1.0 / (rank + 1), self.name) for rank, key in enumerate(keys[:limit])
        ]
        return CandidateSet(source=self.name, candidates=candidates)
