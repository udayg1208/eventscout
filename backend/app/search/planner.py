"""Query Planner — deterministic choice of which retrievers run.

No AI, no LLM, no external services: the plan is a pure function of the `SearchQuery`
shape and (deterministic) entity presence in the graph.

- keywords present, a keyword resolves to a known entity  -> **hybrid** (keyword + entity)
- keywords present, no entity match                       -> **keyword**
- no keywords, structured filters present                 -> **structured**
- no keywords, no filters                                 -> **browse**

The Semantic Retriever is never emitted in Phase 4B (interface only).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.entities.models import EntityType
from app.entities.queries import EntityQueries
from app.models.search import SearchQuery
from app.search.retrievers import Retriever

_ENTITY_TYPES = (
    EntityType.ORGANIZATION,
    EntityType.COMMUNITY,
    EntityType.EVENT_SERIES,
    EntityType.VENUE,
)


@dataclass(frozen=True)
class QueryPlan:
    strategy: str  # "hybrid" | "keyword" | "structured" | "browse"
    retrievers: list[Retriever]


class QueryPlanner:
    def __init__(
        self,
        *,
        keyword: Retriever,
        structured: Retriever,
        entity: Retriever,
        entity_queries: EntityQueries,
    ) -> None:
        self._keyword = keyword
        self._structured = structured
        self._entity = entity
        self._entity_queries = entity_queries

    def plan(self, query: SearchQuery) -> QueryPlan:
        if query.keywords:
            if self._has_entity(query):
                return QueryPlan("hybrid", [self._keyword, self._entity])
            return QueryPlan("keyword", [self._keyword])

        has_filters = bool(
            query.city or query.categories or query.date_from or query.date_to or query.free_only
        )
        return QueryPlan("structured" if has_filters else "browse", [self._structured])

    def _has_entity(self, query: SearchQuery) -> bool:
        return any(
            self._entity_queries.find_entity(keyword, entity_type) is not None
            for keyword in query.keywords
            for entity_type in _ENTITY_TYPES
        )
