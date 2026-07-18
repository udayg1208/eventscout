"""Lightweight graph abstraction — nodes, edges, traversal.

Storage-independent by design: `GraphStore` is the contract; `InMemoryGraphStore` is the
implementation used today. A persisted backend (SQLite `nodes`/`edges` tables, Postgres, or
eventually a real graph database) implements the same interface with **no change to
builders, queries, or analytics**. No graph database is required now.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict

from app.entities.models import Edge, EdgeType, Entity, EntityType


class GraphStore(ABC):
    @abstractmethod
    def upsert_entity(self, entity: Entity) -> Entity:
        """Add an entity, or return the existing one with the same id (reuse)."""

    @abstractmethod
    def get_entity(self, entity_id: str) -> Entity | None: ...

    @abstractmethod
    def entities(self, entity_type: EntityType | None = None) -> list[Entity]: ...

    @abstractmethod
    def add_edge(self, edge: Edge) -> None: ...

    @abstractmethod
    def edges(
        self,
        *,
        source: str | None = None,
        target: str | None = None,
        type: EdgeType | None = None,
    ) -> list[Edge]: ...

    @abstractmethod
    def neighbors(self, entity_id: str, *, type: EdgeType, direction: str = "out") -> list[str]:
        """Entity ids reachable from `entity_id` along `type` ('out' = as source, 'in' = target)."""

    @abstractmethod
    def counts(self) -> dict[str, int]:
        """Entity counts per type (for analytics / reports)."""


class InMemoryGraphStore(GraphStore):
    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}
        self._edges: set[Edge] = set()
        self._out: dict[str, set[Edge]] = defaultdict(set)
        self._in: dict[str, set[Edge]] = defaultdict(set)

    def upsert_entity(self, entity: Entity) -> Entity:
        existing = self._entities.get(entity.id)
        if existing is not None:
            existing.aliases |= entity.aliases
            return existing
        self._entities[entity.id] = entity
        return entity

    def get_entity(self, entity_id: str) -> Entity | None:
        return self._entities.get(entity_id)

    def entities(self, entity_type: EntityType | None = None) -> list[Entity]:
        values = self._entities.values()
        return [e for e in values if entity_type is None or e.type is entity_type]

    def add_edge(self, edge: Edge) -> None:
        if edge in self._edges:
            return
        self._edges.add(edge)
        self._out[edge.source].add(edge)
        self._in[edge.target].add(edge)

    def edges(
        self,
        *,
        source: str | None = None,
        target: str | None = None,
        type: EdgeType | None = None,
    ) -> list[Edge]:
        if source is not None:
            candidates: set[Edge] = self._out.get(source, set())
        elif target is not None:
            candidates = self._in.get(target, set())
        else:
            candidates = self._edges
        result = [
            e
            for e in candidates
            if (target is None or e.target == target)
            and (source is None or e.source == source)
            and (type is None or e.type is type)
        ]
        # Stable order for deterministic output.
        return sorted(result, key=lambda e: (e.source, e.type.value, e.target))

    def neighbors(self, entity_id: str, *, type: EdgeType, direction: str = "out") -> list[str]:
        if direction == "out":
            return sorted(e.target for e in self._out.get(entity_id, set()) if e.type is type)
        return sorted(e.source for e in self._in.get(entity_id, set()) if e.type is type)

    def counts(self) -> dict[str, int]:
        result: dict[str, int] = defaultdict(int)
        for entity in self._entities.values():
            result[entity.type.value] += 1
        return dict(result)
