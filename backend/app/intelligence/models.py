"""Domain models for the Continuous Event Intelligence layer.

This layer is a deterministic **projection over the catalog + provider state + entity
graph**. It reads the frozen Repository / Provider State Store / Entity Graph and produces
intelligence; it mutates none of them. All time is passed in explicitly so every
computation is reproducible.

Honest scope (the frozen `Event` model has no registration-deadline / cancelled / speaker
fields): registration signals are derived from `start_date` (a proxy), "cancelled" maps to
the `withdrawn` status, and cross-provider trending is unavailable post-deduplication.
These are documented, not faked (see EVENT_INTELLIGENCE.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class LifecycleState(StrEnum):
    UPCOMING = "upcoming"
    REGISTRATION_CLOSING = "registration_closing"
    LIVE_TODAY = "live_today"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ChangeType(StrEnum):
    NEW = "new"  # newly discovered
    UPDATED = "updated"  # content changed
    CANCELLED = "cancelled"  # source withdrew it (status → withdrawn)
    EXPIRED = "expired"  # ended (status → expired)
    VENUE_CHANGED = "venue_changed"
    COST_CHANGED = "cost_changed"
    DATE_CHANGED = "date_changed"


@dataclass(frozen=True)
class IntelligenceConfig:
    """Thresholds — all tunable, none hardcoded elsewhere."""

    recently_added_days: int = 7
    registration_closing_days: int = 7
    trending_soon_days: int = 14
    ending_soon_days: int = 7
    archive_after_days: int = 90
    freshness_half_life_days: float = 30.0
    trending_top_n: int = 10
    stale_provider_hours: float = 48.0


@dataclass(frozen=True)
class EventFingerprint:
    """The comparable state of one event, for run-to-run change detection."""

    key: str
    content_hash: str
    status: str
    version: int
    title: str
    location: str | None
    is_free: bool | None
    price: str | None
    start_date: date
    end_date: date | None


@dataclass(frozen=True)
class Change:
    key: str
    type: ChangeType
    detail: str = ""


@dataclass
class ChangeSet:
    new: list[Change] = field(default_factory=list)
    updated: list[Change] = field(default_factory=list)
    cancelled: list[Change] = field(default_factory=list)
    expired: list[Change] = field(default_factory=list)
    venue_changed: list[Change] = field(default_factory=list)
    cost_changed: list[Change] = field(default_factory=list)
    date_changed: list[Change] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "new": len(self.new),
            "updated": len(self.updated),
            "cancelled": len(self.cancelled),
            "expired": len(self.expired),
            "venue_changed": len(self.venue_changed),
            "cost_changed": len(self.cost_changed),
            "date_changed": len(self.date_changed),
        }


@dataclass(frozen=True)
class FreshnessScore:
    key: str
    score: float  # 0..1
    recently_added: bool
    recently_updated: bool
    trending_soon: bool
    ending_soon: bool


@dataclass(frozen=True)
class TrendingEvent:
    key: str
    title: str
    score: float
    signals: dict[str, float]


@dataclass(frozen=True)
class OrganizerProfile:
    entity_id: str
    entity_type: str  # organization | community | event_series
    name: str
    total_events: int
    active_events: int  # upcoming / live
    historical_events: int  # completed / archived
    average_quality: float  # 0..1
    cities: list[str]
    events_per_month: float


@dataclass(frozen=True)
class CommunityInsights:
    fastest_growing: list[dict]
    most_active_cities: list[dict]
    most_active_organizers: list[dict]
    recurring_series: list[dict]
    inactive_communities: list[dict]


@dataclass(frozen=True)
class IntelligenceReport:
    generated_at: datetime
    change_counts: dict[str, int]
    lifecycle_distribution: dict[str, int]
    trending: list[TrendingEvent]
    organizer_profiles: list[OrganizerProfile]
    community_insights: CommunityInsights
    analytics: dict
