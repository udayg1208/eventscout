"""Web search-provider contract (Phase 8B).

Every real provider (Google / Bing / SerpAPI / DuckDuckGo) implements `WebSearchProvider` — the D3
`SearchProvider` contract (`async search(query) -> list[SearchResult]`) plus a `configured` flag so
the engine can pick a provider that actually has its credentials. Provider-specific request/response
logic lives ONLY inside each provider; the engine sees `SearchResult`s and nothing else.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass

from app.discovery.search import SearchProvider, SearchResult

__all__ = ["SearchProviderConfig", "WebSearchProvider", "ProviderError", "SearchResult"]


class ProviderError(RuntimeError):
    """A provider failed to return results (network, quota, auth, or parse error)."""


@dataclass(frozen=True)
class SearchProviderConfig:
    """Credentials + tuning for a real provider. Supplied via env/secrets — never hardcoded."""

    api_key: str | None = None
    endpoint: str | None = None
    engine_id: str | None = None  # Google Programmable Search "cx"
    market: str = "en-IN"  # region/locale hint (India-focused)
    max_results: int = 10
    rate_per_minute: float = 10.0  # polite default
    daily_quota: int | None = None
    timeout_seconds: float = 10.0


class WebSearchProvider(SearchProvider):
    """A real web-search backend. Subclasses build the request and parse the response only."""

    name: str = "web"

    @property
    def configured(self) -> bool:
        """True if this provider has everything it needs to run (e.g. an API key)."""
        return True

    @abstractmethod
    async def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        """Return up to `limit` ranked results for `query`. Raise ProviderError on failure."""
