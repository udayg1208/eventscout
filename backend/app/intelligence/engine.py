"""Background Intelligence Pipeline — the Continuous Event Intelligence engine.

Runs after a successful ingestion (invoked by an orchestrator; it never modifies or is known
to the frozen scheduler/providers). One pass:

    Catalog Updated → Detect Changes → Refresh Intelligence → Update Organizer Profiles
    → Update Community Profiles → Update Trending → Update Analytics → Persist Results

Deterministic given the catalog state, provider states, and `now`. Reads the frozen
Repository (and optionally provider states); writes only into its own IntelligenceStore.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime

from app.entities.builder import GraphBuilder
from app.intelligence.analytics import build_intelligence_analytics
from app.intelligence.changes import detect_changes, snapshot
from app.intelligence.community import build_community_insights
from app.intelligence.hooks import IntelligenceHook
from app.intelligence.lifecycle import lifecycle_state
from app.intelligence.models import IntelligenceConfig, IntelligenceReport
from app.intelligence.organizers import build_organizer_profiles
from app.intelligence.store import InMemoryIntelligenceStore, IntelligenceStore
from app.intelligence.trending import TrendingEngine
from app.storage.models import SearchCriteria
from app.storage.provider_state import ProviderState
from app.storage.repository import EventRepository

logger = logging.getLogger("intelligence.engine")

_DEFAULT_CONFIG = IntelligenceConfig()


class IntelligenceEngine:
    def __init__(
        self,
        store: IntelligenceStore | None = None,
        *,
        config: IntelligenceConfig = _DEFAULT_CONFIG,
        hooks: list[IntelligenceHook] | None = None,
    ) -> None:
        self._store = store or InMemoryIntelligenceStore()
        self._config = config
        self._trending = TrendingEngine(config)
        self._hooks = hooks or []

    @property
    def store(self) -> IntelligenceStore:
        return self._store

    async def run(
        self,
        repo: EventRepository,
        *,
        provider_states: list[ProviderState] | None = None,
        now: datetime,
    ) -> IntelligenceReport:
        config = self._config

        # Catalog Updated → load everything (active + expired/archived) for full intelligence.
        stored = [s async for s in repo.iterate(SearchCriteria(active_only=False))]

        # Detect Changes (vs. the previous run's snapshot).
        changes = detect_changes(self._store.get_snapshot(), stored)

        # Refresh Intelligence: entity graph, lifecycle distribution, trending.
        graph = GraphBuilder().build(stored)
        events_by_key = {s.key: s for s in stored}
        lifecycle_distribution = dict(
            Counter(lifecycle_state(s, now, config).value for s in stored)
        )
        trending = self._trending.top(stored, now)

        # Update Organizer + Community profiles.
        profiles = build_organizer_profiles(graph, events_by_key, now, config)
        insights = build_community_insights(graph, profiles)

        # Update Analytics.
        analytics = build_intelligence_analytics(
            changes=changes,
            trending=trending,
            provider_states=provider_states,
            profiles=profiles,
            insights=insights,
            lifecycle_distribution=lifecycle_distribution,
            now=now,
            config=config,
        )

        report = IntelligenceReport(
            generated_at=now,
            change_counts=changes.counts(),
            lifecycle_distribution=lifecycle_distribution,
            trending=trending,
            organizer_profiles=profiles,
            community_insights=insights,
            analytics=analytics,
        )

        # Persist Results (snapshot for next run + the report).
        self._store.save_snapshot(snapshot(stored))
        self._store.save_report(report)
        for hook in self._hooks:
            await hook.on_report(report)

        logger.info(
            "intelligence run: events=%d changes=%s trending=%d organizers=%d",
            len(stored),
            changes.counts(),
            len(trending),
            len(profiles),
        )
        return report
