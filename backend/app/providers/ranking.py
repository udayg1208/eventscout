"""Deterministic, explainable ranking (search intelligence).

Each signal is an isolated pure function returning a score in [0, 1]. `score_event`
combines them with a single configurable weight table. No embeddings, no vectors, no
LLM — every number is reproducible and testable.

    40%  query relevance   (keywords / category match)
    20%  date proximity    (sooner upcoming events rank higher)
    15%  location match    (query city vs event city; online = partial)
    10%  source quality    (richer / more reliable providers)
    10%  popularity/richness(content richness — no attendee data in the model)
     5%  completeness      (share of optional fields populated)
"""

from __future__ import annotations

from datetime import date

from app.city import normalize_city
from app.models.event import Event
from app.models.search import SearchQuery

# Single source of truth for the weights (must sum to 1.0).
WEIGHTS: dict[str, float] = {
    "relevance": 0.40,
    "date": 0.20,
    "location": 0.15,
    "source": 0.10,
    "popularity": 0.10,
    "completeness": 0.05,
}

# Per-source quality (data richness + reliability + India relevance); default 0.5.
_SOURCE_QUALITY: dict[str, float] = {
    "fossunited": 1.0,
    "hasgeek": 0.9,
    "devfolio": 0.9,
    "confs.tech": 0.8,
    "luma": 0.7,
    "gdg": 0.6,
    "cncf": 0.6,
}

_MAX_COMPLETENESS = 6
_DATE_HALF_LIFE_DAYS = 30  # score 0.5 at ~30 days out


# --------------------------- component scores (each in [0, 1]) ---------------------------


def score_query_relevance(event: Event, query: SearchQuery) -> float:
    """Topical match: query keywords in title/description, and category match."""
    signals: list[float] = []
    if query.keywords:
        haystack = f"{event.title} {event.description or ''}".casefold()
        title = event.title.casefold()
        body_hits = sum(1 for k in query.keywords if k.casefold() in haystack)
        title_hits = sum(1 for k in query.keywords if k.casefold() in title)
        signals.append(min(1.0, (body_hits + title_hits) / (2 * len(query.keywords))))
    if query.categories:
        signals.append(1.0 if event.category in query.categories else 0.0)
    if not signals:
        return 0.0
    return sum(signals) / len(signals)


def score_date(event: Event, today: date) -> float:
    """Sooner upcoming events score higher; past events score 0."""
    days = (event.start_date - today).days
    if days < 0:
        return 0.0
    return 1.0 / (1.0 + days / _DATE_HALF_LIFE_DAYS)


def score_location(event: Event, query: SearchQuery) -> float:
    """1.0 exact city match, 0.5 for online (location-agnostic), else 0.0.
    Neutral (0.0) when the query has no city."""
    if not query.city:
        return 0.0
    if (
        event.city
        and normalize_city(event.city).casefold() == normalize_city(query.city).casefold()
    ):
        return 1.0
    if event.is_online:
        return 0.5
    return 0.0


def score_source(event: Event) -> float:
    """Provider data-quality prior."""
    return _SOURCE_QUALITY.get(event.provider, 0.5)


def score_popularity(event: Event) -> float:
    """Richness proxy (the Event model carries no attendee/popularity data):
    a substantive description, known pricing, a venue, and multi-day span."""
    score = 0.0
    if event.description:
        score += 0.5 * min(1.0, len(event.description) / 200)
    if event.is_free is not None:
        score += 0.25
    if event.location:
        score += 0.15
    if event.end_date:
        score += 0.10
    return min(1.0, score)


def completeness(event: Event) -> int:
    """Raw count of populated optional fields (0..6). Also used by dedup."""
    score = sum(
        1
        for value in (
            event.description,
            event.city,
            event.location,
            event.end_date,
            event.price,
        )
        if value is not None
    )
    if event.is_free is not None:
        score += 1
    return score


def score_completeness(event: Event) -> float:
    return completeness(event) / _MAX_COMPLETENESS


# --------------------------- aggregate + rank ---------------------------


def component_scores(event: Event, query: SearchQuery, today: date) -> dict[str, float]:
    """Every component score for one event (used by score_event and breakdowns)."""
    return {
        "relevance": score_query_relevance(event, query),
        "date": score_date(event, today),
        "location": score_location(event, query),
        "source": score_source(event),
        "popularity": score_popularity(event),
        "completeness": score_completeness(event),
    }


def score_event(event: Event, query: SearchQuery, today: date) -> float:
    """Weighted aggregate score in [0, 1]."""
    scores = component_scores(event, query, today)
    return sum(WEIGHTS[name] * value for name, value in scores.items())


def rank(events: list[Event], query: SearchQuery, today: date | None = None) -> list[Event]:
    """Return events best-first. Deterministic tie-break: sooner date, then title."""
    today = today or date.today()
    return sorted(events, key=lambda e: (-score_event(e, query, today), e.start_date, e.title))
