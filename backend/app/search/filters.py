"""Filter Engine — enforce structured constraints on fused candidates.

Applied *after* fusion and event-loading, so a candidate surfaced by any retriever
(keyword/entity/structured) is dropped unless it satisfies every structured constraint the
query carries: city, category, date range, free/paid, and active+upcoming. It deliberately
does **not** re-check keywords — keyword relevance is the retriever's job (and re-checking
would discard FTS's stemmed matches).
"""

from __future__ import annotations

from datetime import date

from app.city import normalize_city
from app.models.event import Event
from app.models.search import SearchQuery


def passes_structured_filters(event: Event, query: SearchQuery, today: date) -> bool:
    """True if `event` satisfies the query's structured constraints and is upcoming."""
    event_end = event.end_date or event.start_date
    if event_end < today:  # active + upcoming only
        return False
    if query.city:
        if event.city is None:
            return False
        if normalize_city(event.city).casefold() != normalize_city(query.city).casefold():
            return False
    if query.categories and event.category not in query.categories:
        return False
    if query.free_only and event.is_free is not True:
        return False
    if query.date_from and event_end < query.date_from:
        return False
    if query.date_to and event.start_date > query.date_to:
        return False
    return True


def apply_filters(events: list[Event], query: SearchQuery, today: date) -> list[Event]:
    return [e for e in events if passes_structured_filters(e, query, today)]
