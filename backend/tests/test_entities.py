"""Phase 3F: the Event Intelligence Layer (knowledge graph).

Network-free. Builds the graph from hand-made events and checks entity resolution
(organizations, communities, aliases), series detection, entity reuse, graph traversal /
queries, the graph store, venue extraction, the empty-by-design speaker path, and
ecosystem analytics. Deterministic.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.entities import (
    EntityQueries,
    EntityType,
    GraphBuilder,
    InMemoryGraphStore,
    entity_report,
)
from app.entities.extraction import extract_venue, series_name
from app.entities.models import EdgeType, Entity
from app.entities.resolution import normalize_name
from app.models.event import Event, EventCategory
from app.storage.models import StoredEvent

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def _event(
    title,
    *,
    city="Bangalore",
    provider="seed",
    start=date(2026, 9, 1),
    category=EventCategory.MEETUP,
    location=None,
    description=None,
):
    return Event(
        title=title,
        url=f"https://x.example.com/{title.replace(' ', '-').replace('/', '-').lower()}",
        city=city,
        provider=provider,
        start_date=start,
        category=category,
        location=location,
        description=description,
    )


def _build(events):
    return GraphBuilder().build([StoredEvent.from_event(e, seen_at=NOW) for e in events])


# --------------------------- resolution ---------------------------


def test_normalize_name_strips_legal_and_punctuation():
    assert normalize_name("Google LLC") == "google"
    assert normalize_name("FOSS United!") == "foss united"
    assert normalize_name("  GDG   Bangalore ") == "gdg bangalore"


def test_organization_matching_merges_variants():
    graph = _build(
        [
            _event("Google I/O 2026", provider="luma"),
            _event("Google Cloud Summit 2026", provider="luma"),
            _event("Google AI Day 2026", provider="luma"),
        ]
    )
    orgs = graph.entities(EntityType.ORGANIZATION)
    assert len(orgs) == 1
    assert orgs[0].name == "Google" and orgs[0].event_count == 3


def test_community_matching_merges_gdg_chapters():
    graph = _build(
        [
            _event("GDG DevFest", provider="gdg", city="Bangalore"),
            _event("GDG Meetup", provider="gdg", city="Mumbai"),
            _event("GDG Session", provider="gdg", city="Chennai"),
        ]
    )
    communities = graph.entities(EntityType.COMMUNITY)
    assert len(communities) == 1
    gdg = communities[0]
    assert gdg.name == "Google Developer Groups" and gdg.event_count == 3
    chapters = graph.neighbors(gdg.id, type=EdgeType.ACTIVE_IN, direction="out")
    assert set(chapters) == {"city:bangalore", "city:mumbai", "city:chennai"}


def test_false_split_protection_from_title_pattern():
    # community named only in the title, across cities → still one community
    graph = _build(
        [
            _event("GDG Bangalore Meetup", provider="luma", city="Bangalore"),
            _event("Google Developer Group Pune", provider="luma", city="Pune"),
        ]
    )
    communities = graph.entities(EntityType.COMMUNITY)
    assert len(communities) == 1 and communities[0].name == "Google Developer Groups"


def test_graph_reuse_merges_aliases():
    graph = InMemoryGraphStore()
    graph.upsert_entity(
        Entity(
            id="organization:google",
            type=EntityType.ORGANIZATION,
            name="Google",
            aliases={"Google LLC"},
        )
    )
    merged = graph.upsert_entity(
        Entity(
            id="organization:google",
            type=EntityType.ORGANIZATION,
            name="Google",
            aliases={"Google India"},
        )
    )
    assert merged.aliases == {"Google LLC", "Google India"}
    assert len(graph.entities(EntityType.ORGANIZATION)) == 1


# --------------------------- series ---------------------------


def test_series_name_strips_year_and_city():
    assert series_name(_event("PyCon India 2026", city="Hyderabad")) == "PyCon India"
    assert series_name(_event("GDG DevFest Bangalore 2026", city="Bangalore")) == "GDG DevFest"
    assert (
        series_name(_event("The Fifth Elephant 2026 Annual Conference", city="Bangalore"))
        == "The Fifth Elephant Conference"
    )


def test_series_detection_groups_editions():
    graph = _build(
        [
            _event("PyCon India 2025", start=date(2025, 10, 1), provider="luma", city="Hyderabad"),
            _event("PyCon India 2026", start=date(2026, 10, 1), provider="luma", city="Hyderabad"),
        ]
    )
    recurring = [e for e in graph.entities(EntityType.EVENT_SERIES) if e.event_count >= 2]
    assert any(s.name == "PyCon India" and s.event_count == 2 for s in recurring)


# --------------------------- reuse / traversal ---------------------------


def test_entity_reuse_accumulates_event_references():
    graph = _build(
        [
            _event("Google I/O 2026", provider="luma"),
            _event("Google Cloud Next 2026", provider="luma"),
        ]
    )
    google = graph.get_entity("organization:google")
    assert google is not None and google.event_count == 2
    assert len(google.event_keys) == 2  # references, not duplicated event bodies


def test_queries_events_by_organization_and_alias():
    graph = _build(
        [
            _event("Google I/O 2026", provider="luma"),
            _event("Microsoft Build 2026", provider="luma"),
        ]
    )
    queries = EntityQueries(graph)
    google_events = queries.events_by_organization("Google")
    assert len(google_events) == 1
    assert queries.events_by_organization("Google LLC") == google_events  # alias resolves same
    assert queries.events_by_organization("Nonexistent Corp") == []


def test_queries_events_by_community_and_series():
    graph = _build(
        [
            _event("GDG DevFest 2026", provider="gdg", city="Bangalore"),
            _event("PyCon India 2025", start=date(2025, 10, 1), provider="luma", city="Hyderabad"),
            _event("PyCon India 2026", start=date(2026, 10, 1), provider="luma", city="Hyderabad"),
        ]
    )
    queries = EntityQueries(graph)
    assert len(queries.events_by_community("GDG")) == 1
    assert len(queries.events_in_series("PyCon India")) == 2


def test_speaker_queries_are_empty_by_design():
    graph = _build([_event("Some Conf 2026", provider="luma")])
    assert EntityQueries(graph).events_by_speaker("Anyone") == []


# --------------------------- graph store ---------------------------


def test_graph_store_edges_and_neighbors():
    graph = _build([_event("Google I/O 2026", provider="luma", city="Bangalore")])
    google = graph.get_entity("organization:google")
    org_edges = graph.edges(target=google.id, type=EdgeType.ORGANIZED_BY)
    assert len(org_edges) == 1 and org_edges[0].type is EdgeType.ORGANIZED_BY
    # the event is IN_CITY Bangalore
    event_id = org_edges[0].source
    assert graph.neighbors(event_id, type=EdgeType.IN_CITY, direction="out") == ["city:bangalore"]


def test_venue_extraction():
    assert (
        extract_venue(_event("X", location="Bangalore Palace, Bangalore", city="Bangalore"))
        == "Bangalore Palace"
    )
    assert extract_venue(_event("X", location=None)) is None
    assert extract_venue(_event("X", location="Online", city="Bangalore")) is None
    assert extract_venue(_event("X", location="Bangalore", city="Bangalore")) is None


# --------------------------- analytics ---------------------------


def test_entity_report_summarizes_ecosystem():
    graph = _build(
        [
            _event("GDG DevFest 2026", provider="gdg", city="Bangalore"),
            _event("GDG Meetup 2026", provider="gdg", city="Mumbai"),
            _event("Google I/O 2026", provider="luma", city="Bangalore"),
            _event("PyCon India 2025", start=date(2025, 10, 1), provider="luma", city="Hyderabad"),
            _event("PyCon India 2026", start=date(2026, 10, 1), provider="luma", city="Hyderabad"),
        ]
    )
    report = entity_report(graph)
    assert report["counts"]["community"] == 1
    assert report["top_communities"][0]["name"] == "Google Developer Groups"
    assert report["top_communities"][0]["events"] == 2
    assert any(
        s["name"] == "PyCon India" and s["editions"] == 2 for s in report["recurring_series"]
    )
    cities = {c["city"] for c in report["city_ecosystem"]}
    assert {"Bangalore", "Mumbai", "Hyderabad"} <= cities


def test_build_is_deterministic():
    events = [
        _event("Google I/O 2026", provider="luma"),
        _event("GDG DevFest 2026", provider="gdg", city="Mumbai"),
    ]
    first = _build(events).counts()
    second = _build(events).counts()
    assert first == second
