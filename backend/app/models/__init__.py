"""Core domain models: the normalized Event and the SearchQuery contract."""

from app.models.event import Event, EventCategory
from app.models.search import SearchQuery

__all__ = ["Event", "EventCategory", "SearchQuery"]
