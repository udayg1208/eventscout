"""Ranking of merged events.

Score = weighted sum of three signals, each normalized to [0, 1]:
  - query relevance   (keyword/city/category match quality)   weight 0.50
  - date proximity    (sooner upcoming events rank higher)     weight 0.35
  - source completeness (richer records rank higher)           weight 0.15

Pure and deterministic: `today` is injectable for testing.
"""

from __future__ import annotations

from datetime import date

from app.city import normalize_city
from app.models.event import Event
from app.models.search import SearchQuery

_W_RELEVANCE = 0.50
_W_DATE = 0.35
_W_COMPLETENESS = 0.15
_MAX_COMPLETENESS = 6


def completeness(event: Event) -> int:
    """Count populated optional fields (0..6). Also used by dedup."""
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


def _relevance(event: Event, query: SearchQuery) -> float:
    considered = 0
    matched = 0.0

    if query.keywords:
        considered += 1
        title = event.title.casefold()
        haystack = f"{event.title} {event.description or ''}".casefold()
        body_hits = sum(1 for k in query.keywords if k.casefold() in haystack)
        title_hits = sum(1 for k in query.keywords if k.casefold() in title)
        matched += min(1.0, (body_hits + title_hits) / (2 * len(query.keywords)))

    if query.city:
        considered += 1
        if (
            event.city
            and normalize_city(event.city).casefold() == normalize_city(query.city).casefold()
        ):
            matched += 1.0

    if query.categories:
        considered += 1
        if event.category in query.categories:
            matched += 1.0

    if considered == 0:
        return 0.0
    return matched / considered


def _date_proximity(event: Event, today: date) -> float:
    days = (event.start_date - today).days
    if days < 0:
        return 0.0
    return 1.0 / (1.0 + days / 30.0)


def score(event: Event, query: SearchQuery, today: date) -> float:
    return (
        _W_RELEVANCE * _relevance(event, query)
        + _W_DATE * _date_proximity(event, today)
        + _W_COMPLETENESS * (completeness(event) / _MAX_COMPLETENESS)
    )


def rank(events: list[Event], query: SearchQuery, today: date | None = None) -> list[Event]:
    """Return events sorted best-first. Stable tie-break: sooner date, then title."""
    today = today or date.today()
    return sorted(events, key=lambda e: (-score(e, query, today), e.start_date, e.title))
