"""Phase 6B: the Platform HTTP surface — deterministic, network-free.

Builds a seeded PlatformService, injects it into the router singleton, and exercises every
endpoint through the FastAPI TestClient. No live providers, no Gemini (the offline keyword
parser resolves NL search), no network.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.routes import platform as platform_routes
from app.enrichment import EnrichmentPipeline
from app.entities.builder import GraphBuilder
from app.main import create_app
from app.models.event import Event, EventCategory
from app.platform import PlatformService
from app.storage.models import StoredEvent
from app.storage.sqlite_repository import SQLiteEventRepository

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


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
    )


def _catalog():
    return [
        _event(
            "Applied AI Summit",
            category=EventCategory.AI,
            description="artificial intelligence and machine learning with python",
            is_free=True,
        ),
        _event(
            "Deep Learning with PyTorch",
            category=EventCategory.AI,
            description="machine learning and artificial intelligence with pytorch",
        ),
        _event(
            "Winter Hackathon", category=EventCategory.HACKATHON, description="build with react"
        ),
        _event(
            "Backend Conference",
            category=EventCategory.CONFERENCE,
            city="Pune",
            description="microservices and golang",
        ),
        _event(
            "Cloud Meetup",
            category=EventCategory.MEETUP,
            description="cloud and kubernetes",
            is_online=True,
            is_free=True,
        ),
        _event(
            "GDG DevFest Bangalore 2026",
            category=EventCategory.CONFERENCE,
            provider="gdg",
            description="cloud android and google technologies",
        ),
    ]


@pytest.fixture
def client():
    events = _catalog()
    stored = [StoredEvent.from_event(e, seen_at=NOW) for e in events]
    graph = GraphBuilder().build(stored)
    pipeline = EnrichmentPipeline()
    pipeline.enrich_events(stored, graph=graph)
    repo = SQLiteEventRepository()
    asyncio.run(repo.bulk_upsert(stored))
    platform = PlatformService(
        repo,
        events_by_key={s.key: s for s in stored},
        enrichment=pipeline.store.all(),
        graph=graph,
        clock=lambda: NOW,
    )
    platform_routes.configure_platform(platform)
    with TestClient(create_app()) as c:
        c.catalog = stored  # attach for key lookups
        yield c
    platform_routes.configure_platform(None)  # reset singleton for other test modules


def _key(client, title_fragment):
    return next(s.key for s in client.catalog if title_fragment in s.event.title)


def test_homepage_returns_sections(client):
    r = client.get("/platform/homepage?city=Bangalore&limit=4")
    assert r.status_code == 200
    sections = r.json()["sections"]
    assert "ai_events" in sections and "trending" in sections and "nearby_events" in sections
    assert any(e["title"] == "Applied AI Summit" for e in sections["ai_events"])
    assert all(len(v) <= 4 for v in sections.values())


def test_discover_feeds(client):
    for feed in ["trending", "newest", "free", "online", "registration-closing", "this-month"]:
        r = client.get(f"/platform/discover/{feed}")
        assert r.status_code == 200 and isinstance(r.json(), list)
    assert client.get("/platform/discover/bogus").status_code == 404
    assert client.get("/platform/discover/nearby").status_code == 400  # needs ?city=
    assert client.get("/platform/discover/nearby?city=Pune").status_code == 200


def test_browse_dimensions(client):
    r = client.get("/platform/browse/category/ai")
    assert r.status_code == 200
    body = r.json()
    assert any(e["category"] == "ai" for e in body["events"])
    assert body["total_count"] >= 1 and body["offset"] == 0 and "has_more" in body
    assert client.get("/platform/browse/topic/Artificial Intelligence").status_code == 200
    assert client.get("/platform/browse/community/Google Developer Groups").json()["events"]
    assert client.get("/platform/browse/bogus/x").status_code == 404


def test_browse_pagination_walks_full_set(client):
    """Offset pagination must expose every event in a dimension, page by page."""
    full = client.get("/platform/browse/category/ai?limit=200").json()
    total = full["total_count"]
    assert total == len(full["events"]) and full["has_more"] is False

    # walk the same set in pages of 1 and confirm we see all of it with no dupes/gaps
    seen, offset = [], 0
    while True:
        page = client.get(f"/platform/browse/category/ai?offset={offset}&limit=1").json()
        assert page["limit"] == 1 and page["total_count"] == total
        seen.extend(e["key"] for e in page["events"])
        if not page["has_more"]:
            break
        offset += 1
    assert seen == [e["key"] for e in full["events"]] and len(seen) == total


def test_event_details_and_similar(client):
    key = _key(client, "GDG DevFest")
    r = client.get(f"/platform/events/{key}")
    assert r.status_code == 200
    body = r.json()
    assert body["event"]["key"] == key and body["lifecycle"] == "upcoming"
    assert body["community"]["name"] == "Google Developer Groups"
    assert client.get(f"/platform/events/{key}/similar").status_code == 200
    assert client.get("/platform/events/nope:nope").status_code == 404


def test_event_details_by_id_token(client):
    """Every event opens via its opaque base64url token, whatever the key contains."""
    import base64

    from app.api.routes.platform import key_from_token

    def token(k: str) -> str:
        return base64.urlsafe_b64encode(k.encode()).rstrip(b"=").decode()

    key = _key(client, "GDG DevFest")
    r = client.get(f"/platform/events/by-id/{token(key)}")
    assert r.status_code == 200 and r.json()["event"]["key"] == key
    assert client.get(f"/platform/events/by-id/{token(key)}/similar").status_code == 200

    # the token round-trips ANY key content — the class of bug this fixes forever
    for k in (
        "foo.devfolio.co#deadbeef1234",  # host#digest (the reported failure)
        "meetup.com/%ef%b8%8fgrp/events/1",  # a literal % in the key
        "a/b/c#d",  # slashes + #
        "x with %20 space+plus?q=1&y=2:z;w@v,u",  # every reserved char
        "юникод-город/событие 🎉",  # unicode
    ):
        assert key_from_token(token(k)) == k


def test_entity_profiles(client):
    assert (
        client.get("/platform/entities/community/Google Developer Groups").json()["total_events"]
        >= 1
    )
    assert client.get("/platform/entities/organizer/Google").status_code == 200
    assert client.get("/platform/entities/city/Bangalore").status_code == 200
    assert client.get("/platform/entities/community/Nope").status_code == 404
    assert client.get("/platform/entities/bogus/x").status_code == 404


def test_analytics(client):
    body = client.get("/platform/analytics").json()
    assert body["total_events"] == 6 and body["providers"] >= 2
    assert any(t[0] == "Artificial Intelligence" for t in body["top_topics"])


def test_directory(client):
    body = client.get("/platform/directory").json()
    assert "communities" in body and "organizers" in body and "cities" in body
    assert any(name == "Google Developer Groups" for name, _ in body["communities"])
    assert any(name == "Bangalore" for name, _ in body["cities"])


def test_search_natural_language(client):
    r = client.post("/platform/search", json={"query": "kubernetes"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert all("key" in e for e in body["events"])


def test_recommendations_seeded_by_saved(client):
    ai_key = _key(client, "Applied AI Summit")
    r = client.post("/platform/recommendations", json={"saved": [ai_key], "limit": 5})
    assert r.status_code == 200
    recs = r.json()
    assert recs and all(rec["reasons"] for rec in recs)
    assert ai_key not in [rec["event"]["key"] for rec in recs]
    # no seeds → empty (frontend falls back to trending)
    assert client.post("/platform/recommendations", json={}).json() == []
