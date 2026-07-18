"""Phase 4D: Continuous Event Intelligence — deterministic, network-free.

Covers lifecycle transitions, change detection, freshness, trending, organizer/community
intelligence, analytics generation, and the end-to-end background pipeline.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

from app.entities.builder import GraphBuilder
from app.intelligence import (
    FreshnessEngine,
    IntelligenceEngine,
    LifecycleState,
    RegistrationDeadlineMonitor,
    TrendingEngine,
    detect_changes,
    lifecycle_state,
    snapshot,
)
from app.intelligence.analytics import build_intelligence_analytics
from app.intelligence.community import build_community_insights
from app.intelligence.organizers import build_organizer_profiles
from app.models.event import Event, EventCategory
from app.storage.models import EventStatus, StoredEvent, content_hash, event_key
from app.storage.provider_state import CircuitState, ProviderState
from app.storage.sqlite_repository import SQLiteEventRepository


def run(coro):
    return asyncio.run(coro)


NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
TODAY = date(2026, 7, 15)


def _event(
    title,
    *,
    city="Bangalore",
    provider="seed",
    start=date(2026, 9, 1),
    end=None,
    location=None,
    is_free=None,
    price=None,
    category=EventCategory.MEETUP,
    description=None,
):
    return Event(
        title=title,
        url=f"https://x.example.com/{title.replace(' ', '-').lower()}",
        city=city,
        provider=provider,
        start_date=start,
        end_date=end,
        location=location,
        is_free=is_free,
        price=price,
        category=category,
        description=description,
    )


def _stored(event, *, status=EventStatus.ACTIVE, version=1, first_seen=NOW, last_seen=NOW):
    return StoredEvent(
        event=event,
        key=event_key(event),
        content_hash=content_hash(event),
        first_seen_at=first_seen,
        last_seen_at=last_seen,
        status=status,
        version=version,
    )


# --------------------------- lifecycle ---------------------------


def test_lifecycle_transitions():
    assert (
        lifecycle_state(_stored(_event("u", start=date(2026, 9, 1))), NOW)
        is LifecycleState.UPCOMING
    )
    assert (
        lifecycle_state(_stored(_event("c", start=date(2026, 7, 18))), NOW)
        is LifecycleState.REGISTRATION_CLOSING
    )
    assert (
        lifecycle_state(_stored(_event("l", start=date(2026, 7, 14), end=date(2026, 7, 16))), NOW)
        is LifecycleState.LIVE_TODAY
    )
    assert (
        lifecycle_state(_stored(_event("done", start=date(2026, 6, 1), end=date(2026, 6, 2))), NOW)
        is LifecycleState.COMPLETED
    )
    assert (
        lifecycle_state(_stored(_event("old", start=date(2026, 1, 1))), NOW)
        is LifecycleState.ARCHIVED
    )
    archived = _stored(_event("a", start=date(2026, 9, 1)), status=EventStatus.ARCHIVED)
    assert lifecycle_state(archived, NOW) is LifecycleState.ARCHIVED


def test_registration_deadline_monitor():
    monitor = RegistrationDeadlineMonitor()
    closing = monitor.status(_stored(_event("c", start=date(2026, 7, 18))), NOW)
    assert closing.closing_soon and not closing.closed
    started = monitor.status(
        _stored(_event("s", start=date(2026, 7, 14), end=date(2026, 7, 20))), NOW
    )
    assert started.closed and started.event_started
    ended = monitor.status(_stored(_event("e", start=date(2026, 6, 1), end=date(2026, 6, 2))), NOW)
    assert ended.event_ended


# --------------------------- change detection ---------------------------


def test_change_detection_new():
    cs = detect_changes({}, [_stored(_event("A"))])
    assert len(cs.new) == 1 and cs.counts()["new"] == 1


def test_change_detection_updated_venue_cost_date():
    v1 = _stored(_event("A", location="Hall 1", is_free=True, start=date(2026, 9, 1)))
    prev = snapshot([v1])
    v2 = _stored(_event("A", location="Hall 2", is_free=False, start=date(2026, 9, 2)), version=2)
    cs = detect_changes(prev, [v2])
    assert len(cs.updated) == 1
    assert len(cs.venue_changed) == 1 and len(cs.cost_changed) == 1 and len(cs.date_changed) == 1


def test_change_detection_cancelled_and_expired():
    a = _stored(_event("A"))
    b = _stored(_event("B"))
    prev = snapshot([a, b])
    cancelled = _stored(_event("A"), status=EventStatus.WITHDRAWN)
    expired = _stored(_event("B"), status=EventStatus.EXPIRED)
    cs = detect_changes(prev, [cancelled, expired])
    assert len(cs.cancelled) == 1 and len(cs.expired) == 1


def test_change_detection_no_change():
    a = _stored(_event("A"))
    cs = detect_changes(snapshot([a]), [a])
    assert cs.counts() == {
        "new": 0,
        "updated": 0,
        "cancelled": 0,
        "expired": 0,
        "venue_changed": 0,
        "cost_changed": 0,
        "date_changed": 0,
    }


# --------------------------- freshness + trending ---------------------------


def test_freshness_signals():
    engine = FreshnessEngine()
    recent = _stored(_event("soon", start=date(2026, 7, 20)), first_seen=NOW - timedelta(days=2))
    fs = engine.evaluate(recent, NOW)
    assert fs.recently_added and fs.trending_soon
    assert 0.0 <= fs.score <= 1.0
    old = _stored(_event("later", start=date(2026, 12, 1)), first_seen=NOW - timedelta(days=200))
    assert not engine.evaluate(old, NOW).recently_added


def test_trending_ranks_by_signals():
    rich = _stored(
        _event(
            "Rich Soon",
            provider="fossunited",
            start=date(2026, 7, 20),
            description="x" * 300,
            is_free=True,
            price="Free",
            location="Hall",
        )
    )
    sparse = _stored(_event("Sparse Far", provider="gdg", start=date(2026, 12, 1)))
    trending = TrendingEngine().top([rich, sparse], NOW)
    assert [t.title for t in trending] == ["Rich Soon", "Sparse Far"]
    assert trending[0].score > trending[1].score
    # past events excluded from trending
    past = _stored(_event("Past", start=date(2026, 1, 1)))
    assert all(t.title != "Past" for t in TrendingEngine().top([rich, past], NOW))


# --------------------------- organizer + community ---------------------------


def _graph_and_events(events):
    stored = [_stored(e) for e in events]
    graph = GraphBuilder().build(stored)
    return graph, {s.key: s for s in stored}


def test_organizer_profiles():
    graph, events_by_key = _graph_and_events(
        [
            _event("GDG DevFest", provider="gdg", city="Bangalore", start=date(2026, 9, 1)),
            _event(
                "GDG Meetup",
                provider="gdg",
                city="Mumbai",
                start=date(2026, 6, 1),
                end=date(2026, 6, 1),
            ),
        ]
    )
    profiles = build_organizer_profiles(graph, events_by_key, NOW)
    gdg = next(p for p in profiles if p.name == "Google Developer Groups")
    assert gdg.total_events == 2 and gdg.active_events == 1 and gdg.historical_events == 1
    assert set(gdg.cities) == {"Bangalore", "Mumbai"}
    assert 0.0 <= gdg.average_quality <= 1.0


def test_community_insights():
    graph, events_by_key = _graph_and_events(
        [
            _event("GDG A", provider="gdg", city="Bangalore", start=date(2026, 9, 1)),
            _event(
                "FOSS B",
                provider="fossunited",
                city="Delhi",
                start=date(2026, 6, 1),
                end=date(2026, 6, 1),
            ),
        ]
    )
    profiles = build_organizer_profiles(graph, events_by_key, NOW)
    insights = build_community_insights(graph, profiles)
    assert (
        insights.fastest_growing[0]["name"] == "Google Developer Groups"
    )  # only one with upcoming
    assert any(c["city"] == "Bangalore" for c in insights.most_active_cities)
    assert any(
        comm["name"] == "FOSS United" for comm in insights.inactive_communities
    )  # only past event


# --------------------------- analytics ---------------------------


def test_analytics_generation():
    graph, events_by_key = _graph_and_events(
        [_event("GDG A", provider="gdg", start=date(2026, 9, 1))]
    )
    profiles = build_organizer_profiles(graph, events_by_key, NOW)
    insights = build_community_insights(graph, profiles)
    changes = detect_changes({}, list(events_by_key.values()))
    states = [
        ProviderState("gdg", last_success_at=NOW - timedelta(hours=1)),  # active
        ProviderState("dead", last_success_at=NOW - timedelta(hours=100)),  # stale
        ProviderState(
            "broken", last_success_at=NOW, circuit_state=CircuitState.OPEN
        ),  # stale (open)
    ]
    analytics = build_intelligence_analytics(
        changes=changes,
        trending=TrendingEngine().top(list(events_by_key.values()), NOW),
        provider_states=states,
        profiles=profiles,
        insights=insights,
        lifecycle_distribution={"upcoming": 1},
        now=NOW,
    )
    assert analytics["new_events_today"] == 1
    assert analytics["active_providers"] == ["gdg"]
    assert set(analytics["stale_providers"]) == {"dead", "broken"}


# --------------------------- end-to-end pipeline ---------------------------


def test_intelligence_engine_run_and_change_detection_across_runs():
    repo = SQLiteEventRepository()
    run(
        repo.bulk_upsert(
            [
                _stored(_event("A", start=date(2026, 9, 1))),
                _stored(_event("B", start=date(2026, 9, 2))),
            ]
        )
    )
    engine = IntelligenceEngine()

    first = run(engine.run(repo, now=NOW))
    assert first.change_counts["new"] == 2  # all new on first run
    assert first.lifecycle_distribution.get("upcoming") == 2
    assert len(first.trending) == 2

    second = run(engine.run(repo, now=NOW))
    assert second.change_counts["new"] == 0  # nothing new the second time

    run(repo.bulk_upsert([_stored(_event("C", start=date(2026, 9, 3)))]))
    third = run(engine.run(repo, now=NOW))
    assert third.change_counts["new"] == 1  # C detected
