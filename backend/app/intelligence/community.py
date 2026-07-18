"""Community Intelligence — ecosystem insights derived from organizer profiles + the graph.

Growth is approximated from forward activity (a single catalog snapshot has no time series;
a true growth rate needs multiple ingestion snapshots — documented).
"""

from __future__ import annotations

from app.entities.graph import GraphStore
from app.entities.models import EntityType
from app.intelligence.models import CommunityInsights, OrganizerProfile


def build_community_insights(
    graph: GraphStore, profiles: list[OrganizerProfile], *, top: int = 5
) -> CommunityInsights:
    communities = [p for p in profiles if p.entity_type == EntityType.COMMUNITY.value]
    organizations = [p for p in profiles if p.entity_type == EntityType.ORGANIZATION.value]
    series = [p for p in profiles if p.entity_type == EntityType.EVENT_SERIES.value]

    # Proxy for growth: communities with the most *active* (upcoming) events.
    fastest_growing = sorted(communities, key=lambda p: (-p.active_events, p.name))[:top]
    inactive = [p for p in communities if p.active_events == 0]

    cities = sorted(graph.entities(EntityType.CITY), key=lambda e: (-e.event_count, e.name))[:top]

    return CommunityInsights(
        fastest_growing=[
            {"name": p.name, "active_events": p.active_events} for p in fastest_growing
        ],
        most_active_cities=[{"city": e.name, "events": e.event_count} for e in cities],
        most_active_organizers=[
            {"name": p.name, "events": p.total_events} for p in organizations[:top]
        ],
        recurring_series=[
            {"name": p.name, "editions": p.total_events} for p in series if p.total_events >= 2
        ][:top],
        inactive_communities=[{"name": p.name, "total_events": p.total_events} for p in inactive],
    )
