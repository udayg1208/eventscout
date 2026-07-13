"""Natural-language search endpoint.

Thin by design: parse the request, delegate to SearchService, shape the response.
All orchestration (parsing, caching, provider) lives in the service.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.models.event import Event
from app.models.search import SearchQuery
from app.services.search_service import get_search_service

router = APIRouter(tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(..., description="Natural-language search text")


class SearchResponse(BaseModel):
    query: SearchQuery  # the structured query the text resolved to
    count: int
    events: list[Event]
    cached: bool  # were results served from cache?


@router.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    outcome = await get_search_service().search(request.query)
    return SearchResponse(
        query=outcome.query,
        count=len(outcome.events),
        events=outcome.events,
        cached=outcome.cached,
    )
