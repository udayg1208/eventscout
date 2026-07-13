"""Debug-only observability endpoints.

Registered by the app factory ONLY when not running in production. Purely for
development/testing insight into the search pipeline.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.search_service import get_search_service

router = APIRouter(prefix="/debug", tags=["debug"])


class CacheMetrics(BaseModel):
    lookups: int
    hits: int
    hit_rate: float


class MetricsSnapshot(BaseModel):
    total_requests: int
    parse_cache: CacheMetrics
    results_cache: CacheMetrics
    avg_latency_ms: float
    provider_calls: int
    gemini_calls: int
    fallback_count: int


@router.get("/metrics", response_model=MetricsSnapshot)
def metrics() -> MetricsSnapshot:
    return MetricsSnapshot(**get_search_service().metrics())
