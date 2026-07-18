"""Polite page fetching (Phase 10A) — the shared real-fetch step for the processor engines.

The social and rendered engines don't fetch; they consume `(url, html)`. This composes the existing
D1 `Fetcher` (real `HttpxFetcher` in prod, `StaticFetcher` in tests) with the existing `RobotsCache`
plus a per-run page cache, so a URL is fetched **once**, robots-gated, and reused by both engines.
Pure glue over existing components — no new fetch abstraction, no browser, no JS execution. Records
the page counts the daily metrics need.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.discovery.fetch import Fetcher
from app.discovery.robots import RobotsCache

_HTMLISH = ("text/html", "application/xhtml+xml", "application/xml", "text/xml", "")


@dataclass
class FetchedPage:
    url: str
    final_url: str
    html: str
    status: int
    from_cache: bool = False


@dataclass
class FetchStats:
    fetched: int = 0
    cache_hits: int = 0
    skipped_robots: int = 0
    skipped_error: int = 0
    bytes: int = 0

    def as_dict(self) -> dict:
        return {
            "fetched": self.fetched,
            "cache_hits": self.cache_hits,
            "skipped_robots": self.skipped_robots,
            "skipped_error": self.skipped_error,
            "bytes": self.bytes,
        }


class PageFetcher:
    def __init__(
        self, fetcher: Fetcher, *, robots: RobotsCache | None = None, respect_robots: bool = True
    ) -> None:
        self._fetcher = fetcher
        self._robots = robots
        self._respect_robots = respect_robots
        self._cache: dict[str, FetchedPage] = {}
        self.stats = FetchStats()

    async def fetch(self, url: str) -> FetchedPage | None:
        cached = self._cache.get(url)
        if cached is not None:
            self.stats.cache_hits += 1
            return cached
        if (
            self._respect_robots
            and self._robots is not None
            and not await self._robots.allowed(url)
        ):
            self.stats.skipped_robots += 1
            return None
        result = await self._fetcher.get(url)
        if result is None or result.status >= 400 or result.content_type not in _HTMLISH:
            self.stats.skipped_error += 1
            return None
        page = FetchedPage(
            url=url, final_url=result.url, html=result.text, status=result.status, from_cache=False
        )
        self._cache[url] = page
        self.stats.fetched += 1
        self.stats.bytes += len(result.text)
        return page

    async def fetch_many(self, urls: list[str]) -> list[FetchedPage]:
        out: list[FetchedPage] = []
        for url in urls:
            page = await self.fetch(url)
            if page is not None:
                out.append(page)
        return out
