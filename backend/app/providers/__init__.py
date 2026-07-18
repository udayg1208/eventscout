"""Provider registry.

`get_provider()` is the single swap point for the active event source. It returns a
CompositeProvider that fans out to the production sources (Confs.tech + Devfolio),
merges, dedups, and ranks. Because the composite is itself an EventProvider,
SearchService is unchanged. MockProvider remains available for tests.
"""

from functools import lru_cache

from app.providers.base import EventProvider
from app.providers.cncf import CNCFProvider
from app.providers.composite import CompositeProvider
from app.providers.confstech import ConfsTechProvider
from app.providers.devfolio import DevfolioProvider
from app.providers.fossunited import FOSSUnitedProvider
from app.providers.gdg import GDGProvider
from app.providers.hasgeek import HasgeekProvider
from app.providers.luma import LumaProvider
from app.providers.mock import MockProvider

__all__ = [
    "EventProvider",
    "CompositeProvider",
    "ConfsTechProvider",
    "DevfolioProvider",
    "GDGProvider",
    "CNCFProvider",
    "FOSSUnitedProvider",
    "HasgeekProvider",
    "LumaProvider",
    "MockProvider",
    "get_provider",
]


@lru_cache
def get_provider() -> EventProvider:
    """Return the active event source for search.

    Phase 3E cutover: this is now the catalog-backed `DatabaseSearchProvider` — every
    search is served from the Repository, never by fetching live providers. Providers feed
    the catalog through ingestion (scheduler/runner) only.

    `CompositeProvider` (the old search-time fan-out) is DEPRECATED for search: it remains
    a valid `EventProvider` for reference/tests and as a manual warm-up tool, but it is no
    longer wired here. The individual provider implementations are unchanged.
    """
    from app.search import build_search_provider  # lazy import avoids an import cycle

    return build_search_provider()
