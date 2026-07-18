"""Catalog filtering + discovery predicates — orchestration helpers, not business logic.

Each function selects a slice of the catalog by reusing existing outputs (the event fields,
Phase-5A enrichment, Phase-4D lifecycle/freshness). No new rules are invented here; the
platform composes these to build homepage sections, browse results, and discovery feeds.
All are pure functions of (events, …, now) and return events sorted soonest-first.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from app.city import normalize_city
from app.enrichment.models import EventEnrichment
from app.intelligence.lifecycle import lifecycle_state
from app.intelligence.models import LifecycleState
from app.storage.models import StoredEvent


def _sorted(events: Iterable[StoredEvent]) -> list[StoredEvent]:
    return sorted(events, key=lambda s: (s.event.start_date, s.key))


def upcoming(events: Iterable[StoredEvent], now: datetime) -> list[StoredEvent]:
    today = now.date()
    return _sorted(s for s in events if (s.event.end_date or s.event.start_date) >= today)


def browse_order(events: Iterable[StoredEvent], now: datetime) -> list[StoredEvent]:
    """Full browse order over the *entire* catalog for a dimension: upcoming events
    soonest-first, then past events most-recent-first. Lets a browse page page through
    every matching event while still leading with what's still live."""
    today = now.date()
    ev = list(events)
    up = _sorted(s for s in ev if (s.event.end_date or s.event.start_date) >= today)
    past = sorted(
        (s for s in ev if (s.event.end_date or s.event.start_date) < today),
        key=lambda s: (s.event.start_date, s.key),
        reverse=True,
    )
    return up + past


def by_category(events: Iterable[StoredEvent], category: str, now: datetime) -> list[StoredEvent]:
    return [s for s in upcoming(events, now) if s.event.category.value == category]


def by_city(events: Iterable[StoredEvent], city: str, now: datetime) -> list[StoredEvent]:
    target = normalize_city(city).casefold()
    return [
        s
        for s in upcoming(events, now)
        if s.event.city and normalize_city(s.event.city).casefold() == target
    ]


def by_format(events: Iterable[StoredEvent], *, online: bool, now: datetime) -> list[StoredEvent]:
    return [s for s in upcoming(events, now) if s.event.is_online is online]


def by_free(events: Iterable[StoredEvent], *, free: bool, now: datetime) -> list[StoredEvent]:
    return [s for s in upcoming(events, now) if s.event.is_free is free]


def by_date_range(events, *, start, end, now: datetime) -> list[StoredEvent]:
    return [
        s
        for s in upcoming(events, now)
        if s.event.start_date <= end and (s.event.end_date or s.event.start_date) >= start
    ]


def _enriched(events, enrichment, predicate) -> list[StoredEvent]:
    out = []
    for s in events:
        e = enrichment.get(s.key)
        if e is not None and predicate(e):
            out.append(s)
    return out


def by_topic(events, enrichment: dict[str, EventEnrichment], topic: str, now: datetime):
    return _enriched(upcoming(events, now), enrichment, lambda e: topic in e.topics)


def by_technology(events, enrichment, technology: str, now: datetime):
    return _enriched(upcoming(events, now), enrichment, lambda e: technology in e.technologies)


def by_difficulty(events, enrichment, difficulty: str, now: datetime):
    return _enriched(upcoming(events, now), enrichment, lambda e: e.difficulty.value == difficulty)


def by_audience(events, enrichment, audience: str, now: datetime):
    return _enriched(upcoming(events, now), enrichment, lambda e: audience in e.audiences)


def recently_added(events, now: datetime, *, days: int = 7) -> list[StoredEvent]:
    cutoff = now - timedelta(days=days)
    return _sorted(s for s in upcoming(events, now) if s.first_seen_at >= cutoff)


def registration_closing(events, now: datetime) -> list[StoredEvent]:
    return _sorted(
        s for s in events if lifecycle_state(s, now) is LifecycleState.REGISTRATION_CLOSING
    )


def this_weekend(events, now: datetime) -> list[StoredEvent]:
    today = now.date()
    saturday = today + timedelta(days=(5 - today.weekday()) % 7)
    return by_date_range(events, start=saturday, end=saturday + timedelta(days=1), now=now)


def this_month(events, now: datetime) -> list[StoredEvent]:
    today = now.date()
    return [
        s
        for s in upcoming(events, now)
        if s.event.start_date.month == today.month and s.event.start_date.year == today.year
    ]
