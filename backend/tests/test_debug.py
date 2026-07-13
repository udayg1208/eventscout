"""Debug metrics endpoint. Uses the structured endpoint to generate activity so no
network / Gemini call is made during the test."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.cache import TTLCache
from app.main import app
from app.parsers.keyword import KeywordQueryParser
from app.providers.mock import MockProvider
from app.services import search_service as _ss
from app.services.search_service import SearchService

client = TestClient(app)


@pytest.fixture(autouse=True)
def _mock_backed_service(monkeypatch):
    """Pin the singleton to a MockProvider so the metrics endpoint test is
    deterministic and network-free."""
    service = SearchService(
        parser=KeywordQueryParser(),
        provider=MockProvider(),
        parse_cache=TTLCache(300),
        results_cache=TTLCache(300),
    )
    monkeypatch.setattr(_ss, "_search_service", service)


def test_debug_metrics_endpoint_returns_valid_snapshot():
    client.post("/events/search", json={"city": "Pune"})  # network-free activity
    response = client.get("/debug/metrics")
    assert response.status_code == 200

    body = response.json()
    for key in (
        "total_requests",
        "parse_cache",
        "results_cache",
        "avg_latency_ms",
        "provider_calls",
        "gemini_calls",
        "fallback_count",
    ):
        assert key in body

    assert 0.0 <= body["results_cache"]["hit_rate"] <= 1.0
    assert 0.0 <= body["parse_cache"]["hit_rate"] <= 1.0
    assert body["provider_calls"] >= 0
    assert isinstance(body["total_requests"], int)
