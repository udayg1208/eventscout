"""Provider registry.

`get_provider()` is the single swap point for the active event source. It returns a
CompositeProvider that fans out to the production sources (Confs.tech + Devfolio),
merges, dedups, and ranks. Because the composite is itself an EventProvider,
SearchService is unchanged. MockProvider remains available for tests.
"""

from functools import lru_cache

from app.providers.base import EventProvider
from app.providers.composite import CompositeProvider
from app.providers.confstech import ConfsTechProvider
from app.providers.devfolio import DevfolioProvider
from app.providers.mock import MockProvider

__all__ = [
    "EventProvider",
    "CompositeProvider",
    "ConfsTechProvider",
    "DevfolioProvider",
    "MockProvider",
    "get_provider",
]


@lru_cache
def get_provider() -> EventProvider:
    """Return the active event provider (multi-provider composite)."""
    return CompositeProvider([ConfsTechProvider(), DevfolioProvider()])
