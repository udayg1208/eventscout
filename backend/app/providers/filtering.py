"""Shared, provider-local event filtering.

Extracted from MockProvider now that a second provider (Confs.tech) needs the same
logic. Any provider that fetches broadly and must post-filter locally uses this, so
filtering semantics stay identical across sources.
"""

from __future__ import annotations

from app.city import normalize_city
from app.models.event import Event
from app.models.search import SearchQuery


def matches(event: Event, query: SearchQuery) -> bool:
    """True if `event` satisfies every constraint set on `query`."""
    return (
        _city(event, query)
        and _categories(event, query)
        and _keywords(event, query)
        and _dates(event, query)
        and _free(event, query)
    )


def _city(event: Event, query: SearchQuery) -> bool:
    if query.city is None:
        return True
    if event.city is None:
        return False
    # Normalize both sides so "Bengaluru" matches a "Bangalore" query.
    return normalize_city(event.city).casefold() == normalize_city(query.city).casefold()


def _categories(event: Event, query: SearchQuery) -> bool:
    if not query.categories:
        return True
    return event.category in query.categories


def _keywords(event: Event, query: SearchQuery) -> bool:
    if not query.keywords:
        return True
    haystack = f"{event.title} {event.description or ''}".casefold()
    return any(keyword.casefold() in haystack for keyword in query.keywords)


def _dates(event: Event, query: SearchQuery) -> bool:
    # Treat the event as [start_date, end_date or start_date] and keep it if that
    # interval overlaps the requested [date_from, date_to].
    event_end = event.end_date or event.start_date
    if query.date_from and event_end < query.date_from:
        return False
    if query.date_to and event.start_date > query.date_to:
        return False
    return True


def _free(event: Event, query: SearchQuery) -> bool:
    if not query.free_only:
        return True
    return event.is_free is True
