"""Google Programmable Search (Custom Search JSON API) provider (Phase 8B).

GET https://www.googleapis.com/customsearch/v1?key=…&cx=…&q=… → maps `items[]` (title/link/snippet)
to `SearchResult`. Needs an API key + a Programmable Search Engine id (`cx`); free tier ~100
queries/day, so the engine's cache + rate limit are essential. All Google-specific logic lives here.
"""

from __future__ import annotations

from app.discovery.web.fetch import PoliteFetcher
from app.discovery.web.interfaces import (
    ProviderError,
    SearchProviderConfig,
    SearchResult,
    WebSearchProvider,
)


class GoogleProgrammableSearchProvider(WebSearchProvider):
    name = "google"
    ENDPOINT = "https://www.googleapis.com/customsearch/v1"

    def __init__(self, config: SearchProviderConfig, *, fetcher: PoliteFetcher) -> None:
        self._config = config
        self._fetcher = fetcher

    @property
    def configured(self) -> bool:
        return bool(self._config.api_key and self._config.engine_id)

    async def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        if not self.configured:
            raise ProviderError("google: missing api_key / engine_id (cx)")
        params = {
            "key": self._config.api_key,
            "cx": self._config.engine_id,
            "q": query,
            "num": min(max(1, limit), 10),  # Google caps at 10/page
            "gl": "in",
            "hl": "en",
        }
        resp = await self._fetcher.get(self.ENDPOINT, params=params)
        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError(f"google: unparseable response ({exc})") from exc
        if "error" in data:
            raise ProviderError(f"google: {data['error'].get('message', 'API error')}")
        items = data.get("items", []) or []
        return [
            SearchResult(
                title=it.get("title", ""),
                url=it.get("link", ""),
                snippet=it.get("snippet", ""),
                rank=i,
                engine=self.name,
            )
            for i, it in enumerate(items, start=1)
            if it.get("link")
        ]
