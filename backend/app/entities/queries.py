"""Entity-based query foundation.

Lets the backend answer "events by Google", "events from GDG", "events in the PyCon India
series", "events where X speaks" — by resolving a name to a canonical entity and traversing
the graph to the event keys. Returns **event keys** (references into the Repository), so a
caller can fetch full events without this layer duplicating event data.

This is foundation only: it is intentionally NOT wired into SearchService yet.
"""

from __future__ import annotations

from app.entities.graph import GraphStore
from app.entities.models import EdgeType, Entity, EntityType
from app.entities.resolution import EntityResolver

# Which edge connects an entity type to its events (events are the edge source).
_EVENT_EDGE = {
    EntityType.ORGANIZATION: EdgeType.ORGANIZED_BY,
    EntityType.COMMUNITY: EdgeType.HOSTED_BY,
    EntityType.EVENT_SERIES: EdgeType.PART_OF_SERIES,
    EntityType.VENUE: EdgeType.AT_VENUE,
    EntityType.CITY: EdgeType.IN_CITY,
}


class EntityQueries:
    def __init__(self, graph: GraphStore, resolver: EntityResolver | None = None) -> None:
        self._graph = graph
        self._resolver = resolver or EntityResolver()

    def find_entity(self, name: str, entity_type: EntityType) -> Entity | None:
        resolved = self._resolver.resolve(name, entity_type)
        if resolved is None:
            return None
        return self._graph.get_entity(resolved[0])

    def _event_keys(self, name: str, entity_type: EntityType) -> list[str]:
        entity = self.find_entity(name, entity_type)
        if entity is None:
            return []
        edge_type = _EVENT_EDGE[entity_type]
        event_ids = self._graph.neighbors(entity.id, type=edge_type, direction="in")
        return sorted(eid.removeprefix("event:") for eid in event_ids)

    def events_by_organization(self, name: str) -> list[str]:
        return self._event_keys(name, EntityType.ORGANIZATION)

    def events_by_community(self, name: str) -> list[str]:
        return self._event_keys(name, EntityType.COMMUNITY)

    def events_in_series(self, name: str) -> list[str]:
        return self._event_keys(name, EntityType.EVENT_SERIES)

    def events_at_venue(self, name: str) -> list[str]:
        return self._event_keys(name, EntityType.VENUE)

    def events_in_city(self, name: str) -> list[str]:
        return self._event_keys(name, EntityType.CITY)

    def events_by_speaker(self, name: str) -> list[str]:
        # Speakers have no data in the current model — returns empty by design (Phase 5).
        entity = self.find_entity(name, EntityType.SPEAKER)
        if entity is None:
            return []
        return sorted(
            eid.removeprefix("event:")
            for eid in self._graph.neighbors(entity.id, type=EdgeType.SPEAKS_AT, direction="out")
        )
