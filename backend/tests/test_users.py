"""Phase 5B: User Intelligence Platform — deterministic, network-free.

Covers profile learning, saved events, attendance lifecycle, recommendation ranking +
explanations, preference evolution, and analytics.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.enrichment import EnrichmentPipeline
from app.entities.builder import GraphBuilder
from app.models.event import Event, EventCategory
from app.storage.models import StoredEvent
from app.users import (
    AttendanceHistory,
    AttendanceStatus,
    Interaction,
    InteractionType,
    UserIntelligenceEngine,
)

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def _event(
    title,
    *,
    city="Bangalore",
    provider="seed",
    category=EventCategory.MEETUP,
    description=None,
    start=date(2026, 9, 1),
):
    return Event(
        title=title,
        url=f"https://x.example.com/{title.replace(' ', '-').lower()}",
        city=city,
        provider=provider,
        category=category,
        description=description,
        start_date=start,
    )


def _stored(event):
    return StoredEvent.from_event(event, seen_at=NOW)


def _key(event):
    return _stored(event).key


def _engine(events):
    stored = [_stored(e) for e in events]
    graph = GraphBuilder().build(stored)
    pipeline = EnrichmentPipeline()
    pipeline.enrich_events(stored, graph=graph)
    return UserIntelligenceEngine({s.key: s for s in stored}, pipeline.store.all(), graph)


def _interact(engine, user, type_, *, event=None, query=None):
    return engine.record_interaction(
        Interaction(user, type_, NOW, event_key=_key(event) if event else None, query=query)
    )


# --------------------------- profile learning ---------------------------


def test_profile_learns_from_event_interaction():
    ai = _event("Applied Machine Learning", description="artificial intelligence models")
    engine = _engine([ai])
    profile = _interact(engine, "u1", InteractionType.ATTEND, event=ai)
    assert profile.interaction_count == 1 and profile.attended_count == 1
    assert profile.weight("topic:Artificial Intelligence") == 5.0  # ATTEND weight
    assert dict(profile.top("topic"))  # topics learned


def test_search_interaction_learns_query_features():
    engine = _engine([_event("placeholder")])
    profile = _interact(
        engine, "u1", InteractionType.SEARCH, query="kubernetes and python in Bangalore"
    )
    assert profile.weight("topic:Kubernetes") > 0
    assert profile.weight("tech:Python") > 0
    assert profile.weight("city:Bangalore") > 0


def test_ignore_is_a_negative_signal():
    ai = _event("AI Meetup", description="artificial intelligence")
    engine = _engine([ai])
    profile = _interact(engine, "u1", InteractionType.IGNORE, event=ai)
    assert profile.weight("topic:Artificial Intelligence") == -1.0


def test_preference_learning_accumulates():
    ai = _event("AI Deep Dive", description="artificial intelligence")
    engine = _engine([ai])
    _interact(engine, "u1", InteractionType.ATTEND, event=ai)  # +5
    profile = _interact(engine, "u1", InteractionType.SAVE, event=ai)  # +3
    assert profile.weight("topic:Artificial Intelligence") == 8.0
    assert profile.interaction_count == 2


# --------------------------- saved events ---------------------------


def test_saved_events_and_collections():
    a, b = _event("A"), _event("B")
    engine = _engine([a, b])
    _interact(engine, "u1", InteractionType.SAVE, event=a)
    assert _key(a) in engine.saved_store.saved("u1")
    _interact(engine, "u1", InteractionType.UNSAVE, event=a)
    assert _key(a) not in engine.saved_store.saved("u1")
    engine.saved_store.favorite("u1", _key(b))
    assert _key(b) in engine.saved_store.favorites("u1")


# --------------------------- attendance history ---------------------------


def test_attendance_lifecycle_is_deterministic():
    history = AttendanceHistory()
    future = _event("future", start=date(2026, 9, 1))
    past = _event("past", start=date(2026, 1, 1))
    # registered + upcoming → still registered; registered + ended → missed
    assert history.derive(AttendanceStatus.REGISTERED, future, NOW) is AttendanceStatus.REGISTERED
    assert history.derive(AttendanceStatus.REGISTERED, past, NOW) is AttendanceStatus.MISSED
    # explicit statuses are preserved
    assert history.derive(AttendanceStatus.ATTENDED, past, NOW) is AttendanceStatus.ATTENDED
    history.register("u1", "k")
    history.cancel("u1", "k")
    assert history.raw_status("u1", "k") is AttendanceStatus.CANCELLED


def test_attendance_via_engine():
    e = _event("Workshop")
    engine = _engine([e])
    _interact(engine, "u1", InteractionType.ATTEND, event=e)
    assert _key(e) in engine.attendance.attended_keys("u1")


# --------------------------- recommendations ---------------------------


def test_recommendation_ranking_excludes_engaged_and_matches_interest():
    ai_1 = _event("Machine Learning Intro", description="artificial intelligence")
    ai_2 = _event(
        "Deep Learning Advanced", description="artificial intelligence and machine learning"
    )
    gaming = _event("Indie Game Night", description="gaming", category=EventCategory.CONFERENCE)
    engine = _engine([ai_1, ai_2, gaming])
    _interact(engine, "u1", InteractionType.ATTEND, event=ai_1)  # learn AI interest
    recs = engine.recommend("u1", now=NOW, limit=10)
    keys = [r.event_key for r in recs]
    assert _key(ai_1) not in keys  # attended → excluded
    assert keys[0] == _key(ai_2)  # the other AI event ranks first
    assert recs[0].score >= recs[-1].score


def test_recommendation_explanations():
    gdg_ai_1 = _event("GDG AI Workshop", provider="gdg", description="artificial intelligence")
    gdg_ai_2 = _event("GDG ML Session", provider="gdg", description="machine learning and AI")
    engine = _engine([gdg_ai_1, gdg_ai_2])
    _interact(engine, "u1", InteractionType.ATTEND, event=gdg_ai_1)
    recs = engine.recommend("u1", now=NOW, limit=5)
    reasons = recs[0].reasons
    assert reasons  # every recommendation is explained
    joined = " ".join(reasons)
    assert "Google Developer Groups" in joined or "frequently attend" in joined


def test_recommend_empty_for_unknown_user():
    assert _engine([_event("A")]).recommend("ghost", now=NOW) == []


# --------------------------- analytics ---------------------------


def test_user_analytics():
    ai_1 = _event("AI Intro", description="artificial intelligence")
    ai_2 = _event("AI Advanced", description="artificial intelligence")
    engine = _engine([ai_1, ai_2])
    _interact(engine, "u1", InteractionType.ATTEND, event=ai_1)
    engine.recommend("u1", now=NOW, limit=10)  # ai_2 is shown
    _interact(engine, "u1", InteractionType.SAVE, event=ai_2)  # accepted a shown rec

    analytics = engine.analytics("u1")
    assert analytics["attended_events"] == 1 and analytics["saved_events"] == 1
    assert analytics["favorite_topics"]  # AI learned
    assert analytics["recommendation_acceptance"] > 0  # ai_2 shown then saved
    assert analytics["interaction_counts"]["attend"] == 1
