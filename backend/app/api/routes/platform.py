"""Public Platform HTTP surface (Phase 6B wiring).

Thin, additive exposure of the Phase-6A `PlatformService` over HTTP so the web frontend can
consume it. This module adds **no business logic and no intelligence** — every endpoint
resolves the shared `PlatformService` singleton and returns its DTOs verbatim (FastAPI
serializes the frozen dataclasses to JSON). Nothing frozen is modified; the existing
`/search`, `/events`, `/health` routes are untouched.

The service is built once from the catalog Repository (the source of truth) and cached, so
the graph/enrichment projections are computed a single time per process.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.catalog import get_repository
from app.models.search import SearchQuery
from app.parsers import get_query_parser
from app.platform import PlatformService
from app.platform.dto import EventDTO, RecommendationDTO
from app.users.models import Interaction, InteractionType

router = APIRouter(prefix="/platform", tags=["platform"])

# --- shared singleton (built once from the catalog) ---------------------------

_platform: PlatformService | None = None
_lock = asyncio.Lock()


async def get_platform() -> PlatformService:
    global _platform
    if _platform is None:
        async with _lock:
            if _platform is None:
                _platform = await PlatformService.from_repository(get_repository())
    return _platform


def configure_platform(platform: PlatformService | None) -> None:
    """Inject (or reset) the singleton — used by tests to supply a seeded platform."""
    global _platform
    _platform = platform


# --- feed / dimension dispatch tables (no per-item branching) -----------------


def _discover(platform: PlatformService, feed: str, city: str | None, limit: int) -> list[EventDTO]:
    table = {
        "trending": lambda: platform.discover_trending(limit=limit),
        "popular": lambda: platform.discover_popular(limit=limit),
        "newest": lambda: platform.discover_newest(limit=limit),
        "registration-closing": lambda: platform.discover_registration_closing(limit=limit),
        "this-weekend": lambda: platform.discover_this_weekend(limit=limit),
        "this-month": lambda: platform.discover_this_month(limit=limit),
        "online": lambda: platform.discover_online(limit=limit),
        "offline": lambda: platform.discover_offline(limit=limit),
        "free": lambda: platform.discover_free(limit=limit),
        "paid": lambda: platform.discover_paid(limit=limit),
    }
    if feed == "nearby":
        if not city:
            raise HTTPException(status_code=400, detail="nearby requires a ?city= parameter")
        return platform.discover_nearby(city, limit=limit)
    if feed not in table:
        raise HTTPException(status_code=404, detail=f"unknown feed '{feed}'")
    return table[feed]()


# --- homepage / discovery / browse -------------------------------------------


@router.get("/homepage")
async def homepage(city: str | None = None, limit: int = Query(8, ge=1, le=40)):
    platform = await get_platform()
    return platform.homepage(city=city, per_section=limit)


@router.get("/discover/{feed}")
async def discover(feed: str, city: str | None = None, limit: int = Query(24, ge=1, le=100)):
    platform = await get_platform()
    return _discover(platform, feed, city, limit)


class PagedEvents(BaseModel):
    """Offset-paginated browse result. Scales to a 10,000+ catalog: the client pages with
    `offset`/`limit`, `total_count` drives the header count, `has_more` drives Load More."""

    events: list[EventDTO]
    total_count: int
    offset: int
    limit: int
    has_more: bool


@router.get("/browse/{dimension}/{value}", response_model=PagedEvents)
async def browse(
    dimension: str,
    value: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(48, ge=1, le=200),
) -> PagedEvents:
    platform = await get_platform()
    try:
        events, total = platform.browse_page(dimension, value, offset=offset, limit=limit)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"unknown browse dimension '{dimension}'"
        ) from exc
    return PagedEvents(
        events=events,
        total_count=total,
        offset=offset,
        limit=limit,
        has_more=offset + len(events) < total,
    )


# --- event details / similar --------------------------------------------------
#
# An event `key` can contain any character (host/path, host#digest, %, +, spaces, unicode,
# slashes). The primary, future-proof address is `/events/by-id/{token}`, where the token is a
# base64url encoding of the key — a single URL-safe path segment with no reserved-char hazards.
# The raw `{key:path}` routes are kept for backwards compatibility; the by-id routes are declared
# first so they take precedence over the `{key:path}` catch-all.


def key_from_token(token: str) -> str:
    """Decode a base64url event-id token back into the catalog key (400 on a malformed token)."""
    try:
        padded = token + "=" * (-len(token) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid event id") from exc


async def _detail_or_404(key: str):
    platform = await get_platform()
    detail = platform.event_details(key)
    if detail is None:
        raise HTTPException(status_code=404, detail="event not found")
    return detail


async def _similar(key: str, limit: int):
    platform = await get_platform()
    return platform.similar_events(key, limit=limit)


@router.get("/events/by-id/{token}/similar")
async def similar_by_id(token: str, limit: int = Query(10, ge=1, le=50)):
    return await _similar(key_from_token(token), limit)


@router.get("/events/by-id/{token}")
async def event_details_by_id(token: str):
    return await _detail_or_404(key_from_token(token))


@router.get("/events/{key:path}/similar")
async def similar(key: str, limit: int = Query(10, ge=1, le=50)):
    return await _similar(key, limit)


@router.get("/events/{key:path}")
async def event_details(key: str):
    return await _detail_or_404(key)


# --- entity profiles ----------------------------------------------------------


@router.get("/entities/{entity_type}/{name:path}")
async def entity_profile(entity_type: str, name: str):
    platform = await get_platform()
    table = {
        "community": platform.community_profile,
        "organizer": platform.organizer_profile,
        "city": platform.city_profile,
        "series": platform.series_profile,
    }
    if entity_type not in table:
        raise HTTPException(status_code=404, detail=f"unknown entity type '{entity_type}'")
    profile = table[entity_type](name)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"{entity_type} '{name}' not found")
    return profile


# --- analytics ----------------------------------------------------------------


@router.get("/analytics")
async def analytics():
    platform = await get_platform()
    return platform.analytics()


@router.get("/directory")
async def directory():
    platform = await get_platform()
    return platform.directory()


# --- search (natural language → structured → repository-backed DTOs) ----------


class PlatformSearchRequest(BaseModel):
    query: str = Field(..., description="Natural-language search text")
    limit: int = Field(24, ge=1, le=100)


class PlatformSearchResponse(BaseModel):
    query: SearchQuery  # the structured query the text resolved to
    count: int
    events: list[EventDTO]


@router.post("/search", response_model=PlatformSearchResponse)
async def search(request: PlatformSearchRequest) -> PlatformSearchResponse:
    platform = await get_platform()
    structured = await get_query_parser().parse(request.query)
    events = await platform.search(structured, limit=request.limit)
    return PlatformSearchResponse(query=structured, count=len(events), events=events)


# --- recommendations (stateless: seeded by the client's saved/viewed keys) ----


class RecommendationRequest(BaseModel):
    saved: list[str] = Field(default_factory=list)
    viewed: list[str] = Field(default_factory=list)
    limit: int = Field(12, ge=1, le=50)


@router.post("/recommendations", response_model=list[RecommendationDTO])
async def recommendations(request: RecommendationRequest) -> list[RecommendationDTO]:
    platform = await get_platform()
    if not request.saved and not request.viewed:
        return []
    # A transient, deterministic anonymous user derived from the seed set — no auth, no
    # persistence. Replays the client's engagement into the 5B engine, then reads its recs.
    digest = hashlib.sha1(
        ("|".join(sorted(request.saved)) + "#" + "|".join(sorted(request.viewed))).encode()
    ).hexdigest()[:16]
    user_id = f"anon-{digest}"
    now = datetime.now(UTC)
    for key in request.saved:
        platform.record_interaction(Interaction(user_id, InteractionType.SAVE, now, event_key=key))
    for key in request.viewed:
        platform.record_interaction(Interaction(user_id, InteractionType.VIEW, now, event_key=key))
    return platform.recommendations(user_id, limit=request.limit)
