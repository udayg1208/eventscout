"""Ecosystem analytics over the knowledge graph.

Aggregates the derived entities into a picture of the event ecosystem: the most active
organizers and communities, recurring event series, and per-city ecosystems. Growth
metrics are approximated from each entity's first/last-seen span and event count — a true
time series needs multiple ingestion snapshots (disclosed).
"""

from __future__ import annotations

from app.entities.graph import GraphStore
from app.entities.models import EdgeType, Entity, EntityType

_RECURRING_MIN_EDITIONS = 2


def _by_event_count(entities: list[Entity], limit: int) -> list[dict]:
    ranked = sorted(entities, key=lambda e: (-e.event_count, e.name))
    return [
        {
            "name": e.name,
            "events": e.event_count,
            "cities": sorted(e.cities),
            "categories": sorted(e.categories),
        }
        for e in ranked[:limit]
    ]


def top_organizers(graph: GraphStore, limit: int = 10) -> list[dict]:
    return _by_event_count(graph.entities(EntityType.ORGANIZATION), limit)


def most_active_companies(graph: GraphStore, limit: int = 10) -> list[dict]:
    # Companies are organizations here; ranked by activity.
    return _by_event_count(graph.entities(EntityType.ORGANIZATION), limit)


def top_communities(graph: GraphStore, limit: int = 10) -> list[dict]:
    communities = graph.entities(EntityType.COMMUNITY)
    ranked = sorted(communities, key=lambda e: (-e.event_count, e.name))
    return [
        {
            "name": e.name,
            "events": e.event_count,
            "chapters": graph.neighbors(e.id, type=EdgeType.ACTIVE_IN, direction="out"),
            "categories": sorted(e.categories),
        }
        for e in ranked[:limit]
    ]


def recurring_series(graph: GraphStore, limit: int = 20) -> list[dict]:
    series = [
        e
        for e in graph.entities(EntityType.EVENT_SERIES)
        if e.event_count >= _RECURRING_MIN_EDITIONS
    ]
    ranked = sorted(series, key=lambda e: (-e.event_count, e.name))
    return [
        {
            "name": e.name,
            "editions": e.event_count,
            "cities": sorted(e.cities),
            "first_seen": e.first_seen.isoformat() if e.first_seen else None,
            "last_seen": e.last_seen.isoformat() if e.last_seen else None,
        }
        for e in ranked[:limit]
    ]


def city_ecosystem(graph: GraphStore, limit: int = 10) -> list[dict]:
    cities = sorted(graph.entities(EntityType.CITY), key=lambda e: (-e.event_count, e.name))
    return [
        {
            "city": e.name,
            "events": e.event_count,
            "communities": graph.neighbors(e.id, type=EdgeType.ACTIVE_IN, direction="in"),
            "categories": sorted(e.categories),
        }
        for e in cities[:limit]
    ]


def entity_report(graph: GraphStore) -> dict:
    """A full ecosystem snapshot for reports / dashboards."""
    return {
        "counts": graph.counts(),
        "top_organizers": top_organizers(graph),
        "top_communities": top_communities(graph),
        "most_active_companies": most_active_companies(graph),
        "recurring_series": recurring_series(graph),
        "city_ecosystem": city_ecosystem(graph),
    }
