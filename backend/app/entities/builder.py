"""GraphBuilder — project the event catalog into the knowledge graph.

Reads events (from the frozen Repository) and, for each, resolves the entities it implies
and wires the relationships. The graph is a **rebuildable projection**: run it again and you
get the same graph (deterministic, given a stable input order). It never mutates events or
the Repository.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.entities.extraction import (
    extract_communities,
    extract_organizations,
    extract_venue,
    series_name,
)
from app.entities.graph import GraphStore, InMemoryGraphStore
from app.entities.models import Edge, EdgeType, Entity, EntityType
from app.entities.resolution import EntityResolver
from app.storage.models import StoredEvent


class GraphBuilder:
    def __init__(
        self, graph: GraphStore | None = None, resolver: EntityResolver | None = None
    ) -> None:
        self._graph = graph or InMemoryGraphStore()
        self._resolver = resolver or EntityResolver()

    def build(self, events: Iterable[StoredEvent]) -> GraphStore:
        # Stable order → deterministic resolution (fuzzy matching learns as it goes).
        for stored in sorted(events, key=lambda s: s.key):
            self._add_event(stored)
        return self._graph

    def _add_event(self, stored: StoredEvent) -> None:
        event = stored.event
        key = stored.key
        facts = {
            "event_key": key,
            "city": event.city,
            "category": event.category.value,
            "start_date": event.start_date,
        }

        event_node = self._graph.upsert_entity(
            Entity(id=f"event:{key}", type=EntityType.EVENT, name=event.title)
        )
        event_node.observe(**facts)

        city = self._entity(EntityType.CITY, event.city, facts)
        organizations = [
            self._entity(EntityType.ORGANIZATION, name, facts)
            for name in extract_organizations(event)
        ]
        communities = [
            self._entity(EntityType.COMMUNITY, name, facts) for name in extract_communities(event)
        ]
        series = self._entity(EntityType.EVENT_SERIES, series_name(event), facts)
        venue = self._entity(EntityType.VENUE, extract_venue(event), facts)

        # --- relationships from the event ---
        if city:
            self._graph.add_edge(Edge(event_node.id, EdgeType.IN_CITY, city.id))
        for org in filter(None, organizations):
            self._graph.add_edge(Edge(event_node.id, EdgeType.ORGANIZED_BY, org.id))
        for community in filter(None, communities):
            self._graph.add_edge(Edge(event_node.id, EdgeType.HOSTED_BY, community.id))
        if series:
            self._graph.add_edge(Edge(event_node.id, EdgeType.PART_OF_SERIES, series.id))
        if venue:
            self._graph.add_edge(Edge(event_node.id, EdgeType.AT_VENUE, venue.id))
            if city:
                self._graph.add_edge(Edge(venue.id, EdgeType.IN_CITY, city.id))

        # --- derived entity-to-entity relationships ---
        if series:
            for org in filter(None, organizations):
                self._graph.add_edge(Edge(org.id, EdgeType.HOSTS_SERIES, series.id))
        if city:
            for community in filter(None, communities):
                self._graph.add_edge(Edge(community.id, EdgeType.ACTIVE_IN, city.id))

    def _entity(self, entity_type: EntityType, raw: str | None, facts: dict) -> Entity | None:
        """Resolve a raw name to a canonical entity, create-or-reuse it, and fold in facts."""
        if not raw:
            return None
        resolved = self._resolver.resolve(raw, entity_type)
        if resolved is None:
            return None
        entity_id, display = resolved
        entity = self._graph.upsert_entity(
            Entity(id=entity_id, type=entity_type, name=display, aliases={raw.strip()})
        )
        entity.observe(**facts)
        return entity
