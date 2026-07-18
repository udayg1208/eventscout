"""Phase 6A: Public EventScout Platform — deterministic, network-free.

Exercises the `PlatformService` orchestration facade end to end: homepage sections, browse,
discovery, recommendations, entity profiles, analytics, event details, similar events, the
DTO boundary (internal models never leak), and repository-backed search. No live providers,
no network — an in-memory catalog is projected the same way production does.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from app.enrichment import EnrichmentPipeline
from app.entities.builder import GraphBuilder
from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.platform import PlatformService
from app.platform.dto import (
    AnalyticsDTO,
    EventDetailDTO,
    EventDTO,
    HomepageDTO,
    RecommendationDTO,
)
from app.storage.models import StoredEvent
from app.storage.sqlite_repository import SQLiteEventRepository
from app.users.models import Interaction, InteractionType

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)  # a Wednesday


def run(coro):
    return asyncio.run(coro)


def _event(
    title,
    *,
    category=EventCategory.MEETUP,
    city="Bangalore",
    provider="seed",
    description=None,
    start=date(2026, 9, 1),
    is_online=False,
    is_free=None,
    price=None,
):
    return Event(
        title=title,
        url=f"https://x.example.com/{title.replace(' ', '-').lower()}",
        city=city,
        provider=provider,
        category=category,
        description=description,
        start_date=start,
        is_online=is_online,
        is_free=is_free,
        price=price,
    )


def _stored(event, *, seen_at=NOW):
    return StoredEvent.from_event(event, seen_at=seen_at)


def _key(event):
    return _stored(event).key


def _catalog() -> dict[str, Event]:
    return {
        "ai": _event(
            "Applied AI Summit",
            category=EventCategory.AI,
            description="artificial intelligence and machine learning with python",
            is_free=True,
        ),
        "ai2": _event(
            "Deep Learning with PyTorch",
            category=EventCategory.AI,
            description="machine learning and artificial intelligence with pytorch",
        ),
        "hack": _event(
            "Winter Hackathon",
            category=EventCategory.HACKATHON,
            description="build with react and node.js",
        ),
        "conf": _event(
            "Backend Conference",
            category=EventCategory.CONFERENCE,
            city="Pune",
            description="microservices and golang",
            is_free=False,
            price="INR 999",
        ),
        "meetup": _event(
            "Cloud Meetup",
            category=EventCategory.MEETUP,
            description="cloud and kubernetes",
            is_online=True,
            is_free=True,
        ),
        "workshop": _event(
            "Docker Workshop",
            category=EventCategory.WORKSHOP,
            city="Delhi",
            description="hands on docker and kubernetes",
        ),
        "startup": _event(
            "Founder Pitch Day",
            category=EventCategory.STARTUP,
            description="startup founders pitch to investors",
        ),
        "devfest": _event(
            "GDG DevFest Bangalore 2026",
            category=EventCategory.CONFERENCE,
            provider="gdg",
            description="cloud android and google technologies with kubernetes",
        ),
        "gov": _event(
            "Government Digital India Tech Summit",
            category=EventCategory.CONFERENCE,
            city="Delhi",
            description="e-governance and public digital infrastructure",
        ),
        "univ": _event(
            "IIT University Tech Fest",
            category=EventCategory.WORKSHOP,
            description="student innovation and campus projects",
        ),
        "closing": _event(
            "Registration Closing Meetup",
            category=EventCategory.MEETUP,
            start=date(2026, 7, 20),  # within 7 days of NOW → REGISTRATION_CLOSING
        ),
        "weekend": _event(
            "Weekend Data Jam",
            category=EventCategory.MEETUP,
            start=date(2026, 7, 18),  # the coming Saturday → this_weekend
        ),
        "past": _event(
            "Old Conference",
            category=EventCategory.CONFERENCE,
            start=date(2026, 1, 1),  # completed → excluded from upcoming feeds
        ),
    }


def _platform(events, *, clock=lambda: NOW) -> PlatformService:
    stored = [_stored(e) for e in events]
    graph = GraphBuilder().build(stored)
    pipeline = EnrichmentPipeline()
    pipeline.enrich_events(stored, graph=graph)
    return PlatformService(
        None,
        events_by_key={s.key: s for s in stored},
        enrichment=pipeline.store.all(),
        graph=graph,
        clock=clock,
    )


def _keys(dtos):
    return [d.key for d in dtos]


# --------------------------- homepage ---------------------------


def test_homepage_sections_are_populated_from_the_right_engines():
    cat = _catalog()
    hp = _platform(cat.values()).homepage(city="Bangalore")
    assert isinstance(hp, HomepageDTO)
    s = hp.sections

    assert _key(cat["ai"]) in _keys(s["ai_events"])
    assert _key(cat["hack"]) in _keys(s["hackathons"])
    assert _key(cat["conf"]) in _keys(s["conferences"])
    assert _key(cat["meetup"]) in _keys(s["meetups"])
    assert _key(cat["workshop"]) in _keys(s["workshops"])
    assert _key(cat["startup"]) in _keys(s["startup_events"])
    assert _key(cat["devfest"]) in _keys(s["developer_festivals"])
    assert _key(cat["gov"]) in _keys(s["government_tech"])
    assert _key(cat["univ"]) in _keys(s["university_events"])
    assert _key(cat["ai"]) in _keys(s["free_events"])
    assert _key(cat["meetup"]) in _keys(s["online_events"])

    assert s["trending"] and s["upcoming"] and s["recently_added"]
    assert _key(cat["past"]) not in _keys(s["upcoming"])  # completed event excluded
    assert "nearby_events" in s  # city supplied
    assert "recommended" not in s  # no user supplied


def test_homepage_respects_per_section_cap():
    cat = _catalog()
    hp = _platform(cat.values()).homepage(per_section=2)
    assert all(len(section) <= 2 for section in hp.sections.values())


# --------------------------- browse ---------------------------


def test_browse_by_category_city_topic_technology_format():
    cat = _catalog()
    p = _platform(cat.values())
    assert _key(cat["conf"]) in _keys(p.browse_by_category("conference"))
    assert _key(cat["conf"]) in _keys(p.browse_by_city("Pune"))
    assert _key(cat["ai"]) in _keys(p.browse_by_topic("Artificial Intelligence"))
    assert _key(cat["ai"]) in _keys(p.browse_by_technology("Python"))
    assert _key(cat["meetup"]) in _keys(p.browse_by_format(online=True))
    assert _key(cat["past"]) not in _keys(p.browse_by_category("conference"))


def test_browse_by_entity_uses_the_graph():
    cat = _catalog()
    p = _platform(cat.values())
    assert _key(cat["devfest"]) in _keys(p.browse_by_community("Google Developer Groups"))
    assert _key(cat["devfest"]) in _keys(p.browse_by_organizer("Google"))
    assert p.browse_by_organizer("No Such Org") == []


def test_browse_by_difficulty_audience_and_date_round_trip():
    cat = _catalog()
    p = _platform(cat.values())
    detail = p.event_details(_key(cat["ai"]))
    # browse by the event's own derived difficulty/audience → it must appear
    assert _key(cat["ai"]) in _keys(p.browse_by_difficulty(detail.ai.difficulty))
    assert _key(cat["ai"]) in _keys(p.browse_by_audience(detail.ai.audiences[0]))
    weekend = p.browse_by_date(start=date(2026, 7, 18), end=date(2026, 7, 19))
    assert _key(cat["weekend"]) in _keys(weekend)


# --------------------------- discovery ---------------------------


def test_discovery_feeds():
    cat = _catalog()
    p = _platform(cat.values())
    assert p.discover_trending() and p.discover_popular() and p.discover_newest()

    closing = _keys(p.discover_registration_closing())
    assert _key(cat["closing"]) in closing and _key(cat["weekend"]) in closing

    assert _key(cat["weekend"]) in _keys(p.discover_this_weekend())
    assert _key(cat["closing"]) in _keys(p.discover_this_month())
    assert _key(cat["ai"]) in _keys(p.discover_free())
    assert _key(cat["conf"]) in _keys(p.discover_paid())
    assert _key(cat["meetup"]) in _keys(p.discover_online())
    assert all(not e.is_online for e in p.discover_offline())
    assert _key(cat["conf"]) in _keys(p.discover_nearby("Pune"))
    assert _key(cat["past"]) not in _keys(p.discover_newest())


# --------------------------- recommendations ---------------------------


def test_recommendations_are_explained_and_exclude_engaged():
    cat = _catalog()
    p = _platform(cat.values())
    ai_key = _key(cat["ai"])
    p.record_interaction(Interaction("u1", InteractionType.ATTEND, NOW, event_key=ai_key))

    recs = p.recommendations("u1", limit=5)
    assert recs and all(isinstance(r, RecommendationDTO) for r in recs)
    assert recs[0].event.key == _key(cat["ai2"])  # the other AI event ranks first
    assert recs[0].reasons  # every recommendation is explained
    assert ai_key not in [r.event.key for r in recs]  # attended → excluded


def test_recommendations_empty_for_unknown_user():
    assert _platform(_catalog().values()).recommendations("ghost") == []


def test_homepage_includes_recommended_section_for_known_user():
    cat = _catalog()
    p = _platform(cat.values())
    p.record_interaction(Interaction("u1", InteractionType.ATTEND, NOW, event_key=_key(cat["ai"])))
    hp = p.homepage(user_id="u1", per_section=5)
    assert hp.sections.get("recommended")


# --------------------------- entity profiles ---------------------------


def test_entity_profiles():
    cat = _catalog()
    p = _platform(cat.values())

    community = p.community_profile("Google Developer Groups")
    assert community and community.entity_type == "community" and community.total_events >= 1
    assert community.extra["chapters"]  # active-in city ids

    organizer = p.organizer_profile("Google")
    assert organizer and organizer.entity_type == "organization"

    series = p.series_profile("GDG DevFest")
    assert series and series.entity_type == "event_series"

    city = p.city_profile("Bangalore")
    assert city and city.entity_type == "city" and city.total_events >= 1

    assert p.community_profile("Nonexistent Community") is None


# --------------------------- analytics ---------------------------


def test_analytics_are_read_only_counts():
    cat = _catalog()
    a = _platform(cat.values()).analytics()
    assert isinstance(a, AnalyticsDTO)
    assert a.total_events == len(cat)
    assert a.cities >= 3  # Bangalore, Pune, Delhi
    assert a.organizers >= 1 and a.communities >= 1
    assert a.providers >= 2  # seed + gdg
    assert a.top_topics and a.top_technologies
    topics = dict(a.top_topics)
    assert topics.get("Artificial Intelligence", 0) >= 2  # both AI events


# --------------------------- event details + similar ---------------------------


def test_event_details_assembles_the_full_view():
    cat = _catalog()
    p = _platform(cat.values())
    detail = p.event_details(_key(cat["devfest"]))
    assert isinstance(detail, EventDetailDTO)
    assert detail.event.key == _key(cat["devfest"])
    assert detail.ai and detail.ai.topics
    assert detail.lifecycle == "upcoming"
    assert isinstance(detail.trending_score, float)
    assert detail.organizer and detail.organizer.name == "Google"
    assert detail.community and detail.community.name == "Google Developer Groups"
    assert detail.city and detail.city.entity_type == "city"
    assert detail.similar
    assert p.event_details("does:not:exist") is None


def test_similar_events_share_features_and_exclude_self():
    cat = _catalog()
    p = _platform(cat.values())
    similar = p.similar_events(_key(cat["meetup"]), limit=5)  # cloud + kubernetes
    assert all(isinstance(e, EventDTO) for e in similar)
    keys = _keys(similar)
    assert _key(cat["meetup"]) not in keys  # never itself
    assert _key(cat["workshop"]) in keys  # shares Kubernetes


# --------------------------- DTO boundary ---------------------------


def test_platform_never_exposes_internal_models():
    cat = _catalog()
    p = _platform(cat.values())
    hp = p.homepage()
    for section in hp.sections.values():
        assert all(isinstance(e, EventDTO) for e in section)
    detail = p.event_details(_key(cat["ai"]))
    assert isinstance(detail.event, EventDTO)
    assert not isinstance(detail.event, (Event, StoredEvent))


# --------------------------- search (repository-backed) ---------------------------


def test_search_is_served_from_the_repository_as_dtos():
    cat = _catalog()

    async def go():
        repo = SQLiteEventRepository()
        await repo.bulk_upsert([_stored(e) for e in cat.values()])
        platform = await PlatformService.from_repository(repo, clock=lambda: NOW)
        return await platform.search(SearchQuery(keywords=["kubernetes"]))

    results = run(go())
    assert results and all(isinstance(r, EventDTO) for r in results)
    titles = _keys(results)
    assert _key(cat["meetup"]) in titles or _key(cat["workshop"]) in titles
