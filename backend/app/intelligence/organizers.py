"""Organizer Intelligence — profiles for organizers, communities, and recurring series.

Built from the Entity Graph (Phase 3F) + the catalog events. Each profile accumulates total
/ active / historical event counts, average quality, cities served, and an approximate
event frequency. Deterministic given the graph, events, and `now`.
"""

from __future__ import annotations

from datetime import datetime

from app.entities.graph import GraphStore
from app.entities.models import EntityType
from app.intelligence.lifecycle import lifecycle_state
from app.intelligence.models import IntelligenceConfig, LifecycleState, OrganizerProfile
from app.providers.ranking import completeness
from app.storage.models import StoredEvent

_DEFAULT_CONFIG = IntelligenceConfig()
_PROFILE_TYPES = (EntityType.ORGANIZATION, EntityType.COMMUNITY, EntityType.EVENT_SERIES)
_ACTIVE_STATES = (
    LifecycleState.UPCOMING,
    LifecycleState.REGISTRATION_CLOSING,
    LifecycleState.LIVE_TODAY,
)


def _events_per_month(entity, count: int) -> float:
    if entity.first_seen is None or entity.last_seen is None:
        return float(count)
    span_days = max(1, (entity.last_seen - entity.first_seen).days)
    return count / (span_days / 30.0) if span_days >= 30 else float(count)


def build_organizer_profiles(
    graph: GraphStore,
    events_by_key: dict[str, StoredEvent],
    now: datetime,
    config: IntelligenceConfig = _DEFAULT_CONFIG,
) -> list[OrganizerProfile]:
    profiles: list[OrganizerProfile] = []
    for entity_type in _PROFILE_TYPES:
        for entity in graph.entities(entity_type):
            events = [events_by_key[k] for k in entity.event_keys if k in events_by_key]
            if not events:
                continue
            active = sum(1 for s in events if lifecycle_state(s, now, config) in _ACTIVE_STATES)
            quality = sum(completeness(s.event) for s in events) / (len(events) * 6)
            profiles.append(
                OrganizerProfile(
                    entity_id=entity.id,
                    entity_type=entity_type.value,
                    name=entity.name,
                    total_events=len(events),
                    active_events=active,
                    historical_events=len(events) - active,
                    average_quality=round(quality, 3),
                    cities=sorted(entity.cities),
                    events_per_month=round(_events_per_month(entity, len(events)), 2),
                )
            )
    profiles.sort(key=lambda p: (-p.total_events, p.name))
    return profiles
