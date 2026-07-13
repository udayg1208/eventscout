"""Structured event search endpoint.

Takes an already-structured SearchQuery (no AI) and runs it through the shared
SearchService — so it benefits from the same results cache as the NL endpoint,
with no duplicated provider logic. Useful for testing/debugging the provider path.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.models.event import Event
from app.models.search import SearchQuery
from app.services.search_service import get_search_service

router = APIRouter(prefix="/events", tags=["events"])


class SearchResponse(BaseModel):
    query: SearchQuery
    count: int
    events: list[Event]
    cached: bool


@router.post("/search", response_model=SearchResponse)
async def search(query: SearchQuery) -> SearchResponse:
    events, cached = await get_search_service().search_by_query(query)
    return SearchResponse(query=query, count=len(events), events=events, cached=cached)
