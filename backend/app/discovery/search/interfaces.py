"""Future search-integration seams (Phase 6F / D3) — INTERFACES ONLY, no implementations.

D3 ships with `MockSearchProvider` only (constraint: no Google/Bing integration). This module
documents exactly where a real engine plugs in: each class is a `SearchProvider` subclass whose
`search()` raises `NotImplementedError`, so the wiring, config surface, and rate-limit/cache seams
are fixed now and a later phase supplies the HTTP call **without touching the engine**. Nothing
here makes a network request.

Migration path (see SEARCH_DISCOVERY_ENGINE.md): implement one of these, register it in place of
the mock, keep everything downstream (parser → ranking → dedup → frontier → inbox) unchanged.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass

from app.discovery.search.search import SearchProvider, SearchResult


@dataclass(frozen=True)
class SearchProviderConfig:
    """Config a real provider will need (supplied via env/secrets, never hardcoded)."""

    api_key: str | None = None
    endpoint: str | None = None
    engine_id: str | None = None  # e.g. Google Programmable Search "cx"
    max_results: int = 10
    min_interval_seconds: float = 1.0  # polite rate limit
    daily_quota: int | None = None


class RateLimitedSearchProvider(SearchProvider):
    """Wrapper seam: enforce per-engine rate limits / daily quota around any real provider.

    A later phase implements `search()` to await a token from a limiter, delegate to the wrapped
    provider, and surface quota exhaustion — reusing the same limiter shape as the scheduler.
    """

    def __init__(self, inner: SearchProvider, config: SearchProviderConfig) -> None:
        self._inner = inner
        self._config = config
        self.name = f"ratelimited:{inner.name}"

    @abstractmethod
    async def search(
        self, query: str, *, limit: int = 10
    ) -> list[SearchResult]:  # pragma: no cover
        raise NotImplementedError("rate-limiting wrapper is a future seam (D3+)")


class GoogleProgrammableSearchProvider(SearchProvider):
    """Google Programmable Search (Custom Search JSON API) — future adapter.

    Would GET https://www.googleapis.com/customsearch/v1?key=…&cx=…&q=… and map each `items[]`
    entry (title/link/snippet) to a `SearchResult`. Free tier ~100 queries/day → real quota
    management (RateLimitedSearchProvider) is required before enabling.
    """

    name = "google"

    def __init__(self, config: SearchProviderConfig) -> None:
        self._config = config

    async def search(
        self, query: str, *, limit: int = 10
    ) -> list[SearchResult]:  # pragma: no cover
        raise NotImplementedError("Google integration deferred — D3 uses MockSearchProvider only")


class BingWebSearchProvider(SearchProvider):
    """Bing Web Search API — future adapter (maps `webPages.value[]` → SearchResult)."""

    name = "bing"

    def __init__(self, config: SearchProviderConfig) -> None:
        self._config = config

    async def search(
        self, query: str, *, limit: int = 10
    ) -> list[SearchResult]:  # pragma: no cover
        raise NotImplementedError("Bing integration deferred — D3 uses MockSearchProvider only")


class SerpApiSearchProvider(SearchProvider):
    """SerpAPI / third-party SERP scraper — future adapter (aggregates multiple engines)."""

    name = "serpapi"

    def __init__(self, config: SearchProviderConfig) -> None:
        self._config = config

    async def search(
        self, query: str, *, limit: int = 10
    ) -> list[SearchResult]:  # pragma: no cover
        raise NotImplementedError("SerpAPI integration deferred — D3 uses MockSearchProvider only")
