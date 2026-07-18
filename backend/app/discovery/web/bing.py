"""Bing Web Search API provider (Phase 8B).

GET https://api.bing.microsoft.com/v7.0/search with an `Ocp-Apim-Subscription-Key` header → maps
`webPages.value[]` (name/url/snippet) to `SearchResult`. Needs a subscription key. Bing-specific
logic lives only here.
"""

from __future__ import annotations

from app.discovery.web.fetch import PoliteFetcher
from app.discovery.web.interfaces import (
    ProviderError,
    SearchProviderConfig,
    SearchResult,
    WebSearchProvider,
)


class BingWebSearchProvider(WebSearchProvider):
    name = "bing"
    ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"

    def __init__(self, config: SearchProviderConfig, *, fetcher: PoliteFetcher) -> None:
        self._config = config
        self._fetcher = fetcher

    @property
    def configured(self) -> bool:
        return bool(self._config.api_key)

    async def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        if not self.configured:
            raise ProviderError("bing: missing api_key")
        headers = {"Ocp-Apim-Subscription-Key": self._config.api_key}
        params = {
            "q": query,
            "count": min(max(1, limit), 50),
            "mkt": self._config.market,
            "responseFilter": "Webpages",
        }
        resp = await self._fetcher.get(self.ENDPOINT, params=params, headers=headers)
        try:
            data = resp.json()
        except ValueError as exc:
            raise ProviderError(f"bing: unparseable response ({exc})") from exc
        items = (data.get("webPages") or {}).get("value", []) or []
        return [
            SearchResult(
                title=it.get("name", ""),
                url=it.get("url", ""),
                snippet=it.get("snippet", ""),
                rank=i,
                engine=self.name,
            )
            for i, it in enumerate(items, start=1)
            if it.get("url")
        ]
