"""Polite, scoped crawler (no JS — raw bytes only).

Respects robots.txt, stays inside configured domains, normalizes + dedups URLs, bounds work
(pages/depth/sitemap-locs), rate-limits per configured interval, and consults the checkpoint
store for incremental crawling. Yields fetched pages; the engine turns them into candidates.
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.discovery.fetch import Fetcher, FetchResult
from app.discovery.links import extract_feed_links, extract_page_links, extract_sitemap_locs
from app.discovery.robots import RobotsCache
from app.discovery.store import CrawlCheckpointStore
from app.discovery.urls import normalize_url, registrable_domain, same_scope

_EVENTISH = re.compile(r"/(events?|e|meetup|conference|talks?|sessions?)/", re.IGNORECASE)


@dataclass(frozen=True)
class CrawlPage:
    url: str
    result: FetchResult
    depth: int
    path: tuple[str, ...]


@dataclass
class CrawlStats:
    fetched: int = 0  # actual network fetches (any status)
    pages: int = 0  # 200-OK pages yielded
    skipped_seen: int = 0
    skipped_scope: int = 0
    skipped_robots: int = 0
    skipped_checkpoint: int = 0
    errors: int = 0


class Crawler:
    def __init__(
        self,
        fetcher: Fetcher,
        robots: RobotsCache,
        *,
        max_pages: int = 40,
        max_depth: int = 2,
        max_sitemap_locs: int = 30,
        checkpoint: CrawlCheckpointStore | None = None,
        incremental_ttl_hours: float = 24.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] | None = None,
        min_interval: float = 0.0,
    ) -> None:
        self._fetcher = fetcher
        self._robots = robots
        self._max_pages = max_pages
        self._max_depth = max_depth
        self._max_sitemap_locs = max_sitemap_locs
        self._checkpoint = checkpoint
        self._ttl = incremental_ttl_hours
        self._clock = clock
        self._sleep = sleep
        self._min_interval = min_interval
        self.stats = CrawlStats()

    async def crawl(self, seed_url: str, allowed_domains: set[str]) -> AsyncIterator[CrawlPage]:
        self.stats = CrawlStats()
        norm_seed = normalize_url(seed_url)
        if not norm_seed:
            return
        frontier: deque[tuple[str, int, tuple[str, ...]]] = deque([(norm_seed, 0, (norm_seed,))])
        visited: set[str] = set()
        since = self._clock() - timedelta(hours=self._ttl)

        # seed the frontier with robots-declared sitemaps
        policy = await self._robots.policy(norm_seed)
        for sitemap in policy.sitemaps:
            n = normalize_url(sitemap)
            if n and same_scope(n, allowed_domains):
                frontier.append((n, 1, (norm_seed, n)))

        while frontier and self.stats.fetched < self._max_pages:
            url, depth, path = frontier.popleft()
            if url in visited:
                self.stats.skipped_seen += 1
                continue
            visited.add(url)
            if not same_scope(url, allowed_domains):
                self.stats.skipped_scope += 1
                continue
            if not await self._robots.allowed(url):
                self.stats.skipped_robots += 1
                continue
            if self._checkpoint and await self._checkpoint.was_crawled_since(url, since):
                self.stats.skipped_checkpoint += 1
                continue
            if self._min_interval and self._sleep:
                await self._sleep(self._min_interval)

            result = await self._fetcher.get(url)
            now = self._clock()
            if self._checkpoint:
                await self._checkpoint.record(
                    url, registrable_domain(url), now, result.status if result else 0
                )
            if result is None:
                self.stats.errors += 1
                continue
            self.stats.fetched += 1
            if result.status != 200:
                continue
            self.stats.pages += 1
            yield CrawlPage(url, result, depth, path)
            self._enqueue_next(result, url, depth, path, allowed_domains, visited, frontier)

    def _enqueue_next(self, result, url, depth, path, allowed_domains, visited, frontier) -> None:
        body = result.text
        lowered = body[:1000].lower()
        if "<urlset" in body or "<sitemapindex" in body:
            locs = extract_sitemap_locs(body)
            locs.sort(key=lambda u: 0 if _EVENTISH.search(u) else 1)  # event pages first
            for loc in locs[: self._max_sitemap_locs]:
                if loc not in visited and same_scope(loc, allowed_domains):
                    frontier.append((loc, depth + 1, path + (loc,)))
        elif "<a " in lowered or "<html" in lowered or "<!doctype html" in lowered:
            for feed_url, _ in extract_feed_links(body, url):
                if feed_url not in visited and same_scope(feed_url, allowed_domains):
                    frontier.append((feed_url, depth + 1, path + (feed_url,)))
            if depth < self._max_depth:
                for link in extract_page_links(body, url):
                    if link not in visited and same_scope(link, allowed_domains):
                        frontier.append((link, depth + 1, path + (link,)))
