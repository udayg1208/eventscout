"""Continuous Event Intelligence — the automation layer that turns the searchable catalog
into a continuously-updating intelligence platform.

A deterministic projection over the frozen catalog + provider state + entity graph:
change detection, freshness, lifecycle, trending, organizer/community intelligence, and
analytics, refreshed after each ingestion. It modifies nothing frozen; no provider knows it
exists. Notification/recommendation/alert hooks are interfaces only.
"""

from app.intelligence.changes import EventFingerprint, detect_changes, fingerprint, snapshot
from app.intelligence.engine import IntelligenceEngine
from app.intelligence.freshness import FreshnessEngine, freshness_score
from app.intelligence.lifecycle import (
    RegistrationDeadlineMonitor,
    lifecycle_state,
)
from app.intelligence.models import (
    ChangeSet,
    ChangeType,
    CommunityInsights,
    IntelligenceConfig,
    IntelligenceReport,
    LifecycleState,
    OrganizerProfile,
    TrendingEvent,
)
from app.intelligence.store import InMemoryIntelligenceStore, IntelligenceStore
from app.intelligence.trending import EngagementSignal, TrendingEngine

__all__ = [
    "IntelligenceEngine",
    "IntelligenceStore",
    "InMemoryIntelligenceStore",
    "IntelligenceConfig",
    "IntelligenceReport",
    "lifecycle_state",
    "LifecycleState",
    "RegistrationDeadlineMonitor",
    "detect_changes",
    "fingerprint",
    "snapshot",
    "EventFingerprint",
    "ChangeSet",
    "ChangeType",
    "FreshnessEngine",
    "freshness_score",
    "TrendingEngine",
    "TrendingEvent",
    "EngagementSignal",
    "OrganizerProfile",
    "CommunityInsights",
]
