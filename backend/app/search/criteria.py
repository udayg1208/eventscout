"""Translation from the frozen `SearchQuery` to a storage `SearchCriteria`.

Kept in its own module so both the structured retriever and the search provider use one
definition without an import cycle. Search always scopes to ACTIVE + upcoming events.
"""

from __future__ import annotations

from datetime import date

from app.models.search import SearchQuery
from app.storage.models import SearchCriteria


def to_criteria(query: SearchQuery, *, today: date, limit: int) -> SearchCriteria:
    return SearchCriteria(
        keywords=list(query.keywords),
        city=query.city,
        categories=list(query.categories),
        date_from=query.date_from,
        date_to=query.date_to,
        free_only=query.free_only,
        active_only=True,
        upcoming_on_or_after=today,
        limit=limit,
    )
