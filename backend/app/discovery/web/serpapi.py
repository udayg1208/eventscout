"""SerpAPI provider (Phase 8B).

GET https://serpapi.com/search.json?engine=google&q=…&api_key=… → maps `organic_results[]`
(title/link/snippet) to `SearchResult`. SerpAPI is a paid SERP aggregator (it runs the query
against a real engine and returns structured JSON), so cache + rate limit matter for cost. SerpAPI-
specific logic lives only here.
"""

from __future__ import annotations

from app.discovery.web.fetch import PoliteFetcher
from app.discovery.web.interfaces import (
    ProviderError,
    SearchProviderConfig,
    SearchResult,
    WebSearchProvider,
)


class SerpApiSearchProvider(WebSearchProvider):
    name = "serpapi"
    ENDPOINT = "https://serpapi.com/search.json"

    def __init__(self, config: SearchProviderConfig, *, fetcher: PoliteFetcher) -> None:
        self._config = config
        self._fetcher = fetcher

    @property
    def configured(self) -> bool:
        return bool(self._config.api_key)

    async def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        if not self.configured:
            raise ProviderError("serpapi: missing api_key")
        params = {
            "api_key": self._config.api_key,
            "engine": "google",
            "q": query,
            "num": min(max(1, limit), 20),
            "gl": "in",
            "hl": "en",
        }
        resp = await self._fetcher.get(self.ENDPOINT, params=params)
        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError(f"serpapi: unparseable response ({exc})") from exc
        if data.get("error"):
            raise ProviderError(f"serpapi: {data['error']}")
        items = data.get("organic_results", []) or []
        return [
            SearchResult(
                title=it.get("title", ""),
                url=it.get("link", ""),
                snippet=it.get("snippet", ""),
                rank=it.get("position", i),
                engine=self.name,
            )
            for i, it in enumerate(items, start=1)
            if it.get("link")
        ]
