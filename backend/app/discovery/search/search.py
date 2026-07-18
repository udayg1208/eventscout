"""SearchProvider abstraction + a deterministic MockSearchProvider (Phase 6F / D3).

A `SearchProvider` is a **web-search engine** seam — given a text query it returns ranked result
rows (title/url/snippet). This is NOT the app's event `SearchService` (frozen); it is how the
Discovery Engine asks "which pages on the web match this query?" so it can discover NEW source
domains it was never seeded with.

No real engine is integrated in D3 (constraint). `MockSearchProvider` matches queries against an
injected in-memory corpus **deterministically** — same corpus + same query → same ranked results —
so tests and the live spike need no network and no API keys. Real Google/Bing/SerpAPI adapters are
sketched (interface only) in `interfaces.py`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class SearchResult:
    """One row from a search engine's result page."""

    title: str
    url: str
    snippet: str = ""
    rank: int = 0  # 1-based position within this query's results
    engine: str = "mock"


class SearchProvider(ABC):
    """Contract every web-search backend implements. Async to match a real HTTP engine."""

    name: str = "search"

    @abstractmethod
    async def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        """Return up to `limit` ranked results for `query` (rank 1 = most relevant)."""


@dataclass(frozen=True)
class MockPage:
    """A page in the mock search index. `tags` are extra keywords it 'ranks for'."""

    url: str
    title: str
    snippet: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def haystack(self) -> str:
        return " ".join((self.url, self.title, self.snippet, *self.tags)).lower()


def parse_query(query: str) -> tuple[str | None, list[str]]:
    """Split a query into an optional `site:` domain filter and the remaining lowercased terms."""
    site: str | None = None
    terms: list[str] = []
    for token in query.split():
        low = token.lower()
        if low.startswith("site:"):
            site = low[len("site:") :].strip().lstrip(".") or None
        elif low:
            terms.append(low)
    return site, terms


class MockSearchProvider(SearchProvider):
    """Deterministic search over an in-memory corpus — no network, no API key.

    Scoring is transparent: a `site:` filter restricts to a domain; the remaining terms score by
    how many appear in the page's haystack (url+title+snippet+tags). Ties break by URL so the
    ordering is fully deterministic. A site-only query returns every page on that domain.
    """

    name = "mock"

    def __init__(self, corpus: list[MockPage]) -> None:
        self._corpus = list(corpus)

    async def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        site, terms = parse_query(query)
        scored: list[tuple[int, MockPage]] = []
        for page in self._corpus:
            host = (urlsplit(page.url).hostname or "").lower()
            # `site:X` matches the host X or any subdomain of X (real search-engine semantics).
            if site and not (host == site or host.endswith("." + site)):
                continue
            hay = page.haystack()
            hits = sum(1 for t in terms if t in hay)
            if terms and hits == 0:
                continue  # a keyword query that matches nothing is not a result
            scored.append((hits, page))
        scored.sort(key=lambda sp: (-sp[0], sp[1].url))
        return [
            SearchResult(
                title=page.title, url=page.url, snippet=page.snippet, rank=i, engine=self.name
            )
            for i, (_, page) in enumerate(scored[:limit], start=1)
        ]
