"""Intelligence Analytics — the daily ecosystem snapshot.

Combines change detection, trending, lifecycle distribution, provider health, and organizer/
community profiles into one report dict. Deterministic given its inputs + `now`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.intelligence.models import (
    ChangeSet,
    CommunityInsights,
    IntelligenceConfig,
    OrganizerProfile,
    TrendingEvent,
)
from app.storage.provider_state import CircuitState, ProviderState

_DEFAULT_CONFIG = IntelligenceConfig()


def _classify_providers(
    states: list[ProviderState], now: datetime, config: IntelligenceConfig
) -> tuple[list[str], list[str]]:
    active, stale = [], []
    window = timedelta(hours=config.stale_provider_hours)
    for state in states:
        fresh = state.last_success_at is not None and (now - state.last_success_at) <= window
        if fresh and state.circuit_state is not CircuitState.OPEN:
            active.append(state.provider_id)
        else:
            stale.append(state.provider_id)
    return sorted(active), sorted(stale)


def build_intelligence_analytics(
    *,
    changes: ChangeSet,
    trending: list[TrendingEvent],
    provider_states: list[ProviderState] | None,
    profiles: list[OrganizerProfile],
    insights: CommunityInsights,
    lifecycle_distribution: dict[str, int],
    now: datetime,
    config: IntelligenceConfig = _DEFAULT_CONFIG,
) -> dict:
    counts = changes.counts()
    active_providers, stale_providers = _classify_providers(provider_states or [], now, config)
    return {
        "new_events_today": counts["new"],
        "updated_today": counts["updated"],
        "expired_today": counts["expired"],
        "cancelled_today": counts["cancelled"],
        "venue_changes_today": counts["venue_changed"],
        "trending_events": [{"title": t.title, "score": t.score} for t in trending[:5]],
        "active_providers": active_providers,
        "stale_providers": stale_providers,
        "lifecycle_distribution": lifecycle_distribution,
        "organizer_activity": [
            {"name": p.name, "total": p.total_events, "active": p.active_events}
            for p in profiles[:5]
        ],
        "community_activity": insights.fastest_growing,
    }
