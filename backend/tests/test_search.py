"""M2 proof: the backend returns normalized events, filtered by a structured query,
independent of the data source."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.cache import TTLCache
from app.main import app
from app.models.search import SearchQuery
from app.parsers.keyword import KeywordQueryParser
from app.providers.mock import MockProvider
from app.services import search_service as _ss
from app.services.search_service import SearchService

client = TestClient(app)


@pytest.fixture(autouse=True)
def _mock_backed_service(monkeypatch):
    """The default provider is now the network-backed ConfsTechProvider; pin the
    endpoint's singleton service to a MockProvider so these HTTP tests stay
    deterministic and network-free."""
    service = SearchService(
        parser=KeywordQueryParser(),
        provider=MockProvider(),
        parse_cache=TTLCache(300),
        results_cache=TTLCache(300),
    )
    monkeypatch.setattr(_ss, "_search_service", service)


def _post(payload: dict) -> dict:
    response = client.post("/events/search", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_query_returns_all_seed_events() -> None:
    body = _post({})
    assert body["count"] == len(body["events"]) > 0
    # Every returned event conforms to the normalized contract.
    for event in body["events"]:
        assert event["title"]
        assert event["url"].startswith("http")
        assert event["category"]
        assert event["provider"] == "mock"


def test_city_filter_is_case_insensitive() -> None:
    body = _post({"city": "bangalore"})
    assert body["count"] > 0
    assert all(e["city"] == "Bangalore" for e in body["events"])


def test_category_filter() -> None:
    body = _post({"categories": ["hackathon"]})
    assert body["count"] > 0
    assert all(e["category"] == "hackathon" for e in body["events"])


def test_free_only_filter() -> None:
    body = _post({"free_only": True})
    assert body["count"] > 0
    assert all(e["is_free"] is True for e in body["events"])


def test_keyword_matches_title_or_description() -> None:
    body = _post({"keywords": ["machine learning"]})
    assert body["count"] > 0
    for e in body["events"]:
        haystack = f"{e['title']} {e['description'] or ''}".casefold()
        assert "machine learning" in haystack


def test_invalid_date_range_is_rejected() -> None:
    response = client.post(
        "/events/search",
        json={"date_from": "2026-08-01", "date_to": "2026-07-01"},
    )
    assert response.status_code == 422


def test_provider_directly_filters_by_city() -> None:
    # Unit-level check of the provider, bypassing the HTTP layer.
    provider = MockProvider()
    events = asyncio.run(provider.search(SearchQuery(city="Pune")))
    assert events
    assert all(e.city == "Pune" for e in events)


def test_narrow_date_window_excludes_far_events() -> None:
    today = date.today()
    soon = (today + timedelta(days=4)).isoformat()
    body = _post({"date_to": soon})
    # Only events starting within the next 4 days should appear.
    assert all(e["start_date"] <= soon for e in body["events"])
