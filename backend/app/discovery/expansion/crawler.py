"""Bounded expansion crawler (Phase 8C) — polite fetch with robots + budget + checkpoint.

Wraps D1's `Fetcher` + `RobotsCache`: before fetching a URL it checks the per-domain budget, skips
URLs crawled within the refresh window (incremental crawling via the CheckpointStore), and honors
robots.txt. On fetch it records bandwidth/failure against the budget and writes a checkpoint (with a
content fingerprint as a lightweight ETag). No JavaScript, no browser.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.discovery.expansion.budget import BudgetTracker
from app.discovery.expansion.checkpoint import CheckpointRecord, CheckpointStore
from app.discovery.fetch import Fetcher, FetchResult
from app.discovery.robots import RobotsCache


@dataclass
class CrawlOutcome:
    url: str
    fetched: bool
    result: FetchResult | None
    skip_reason: str | None
    byte_size: int = 0


async def _noop_sleep(_seconds: float) -> None:
    return None


class ExpansionCrawler:
    def __init__(
        self,
        fetcher: Fetcher,
        robots: RobotsCache,
        budget: BudgetTracker,
        checkpoint: CheckpointStore,
        *,
        refresh_after_hours: float = 24.0,
        min_interval: float = 0.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = _noop_sleep,
    ) -> None:
        self._fetcher = fetcher
        self._robots = robots
        self._budget = budget
        self._checkpoint = checkpoint
        self._refresh = timedelta(hours=refresh_after_hours)
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep

    async def fetch(self, url: str, *, domain: str, depth: int) -> CrawlOutcome:
        can, why = self._budget.can_crawl(domain)
        if not can:
            return CrawlOutcome(url, False, None, f"budget: {why}")

        if await self._checkpoint.was_crawled_since(url, self._clock() - self._refresh):
            return CrawlOutcome(url, False, None, "checkpoint: crawled recently")

        if not await self._robots.allowed(url):
            return CrawlOutcome(url, False, None, "robots: disallowed")

        if self._min_interval:
            await self._sleep(self._min_interval)
        result = await self._fetcher.get(url)

        if result is None:
            self._budget.record_fetch(domain, success=False)
            await self._save(url, domain, depth, success=False, result=None)
            return CrawlOutcome(url, False, None, "fetch failed (None)")

        byte_size = len(result.text.encode("utf-8", "ignore"))
        ok = result.status < 400
        self._budget.record_fetch(domain, byte_size=byte_size, success=ok)
        await self._save(url, domain, depth, success=ok, result=result)
        if not ok:
            return CrawlOutcome(url, False, None, f"http {result.status}", byte_size)
        return CrawlOutcome(url, True, result, None, byte_size)

    async def _save(
        self, url: str, domain: str, depth: int, *, success: bool, result: FetchResult | None
    ) -> None:
        now = self._clock()
        prior = await self._checkpoint.get(url)
        fingerprint = (
            hashlib.sha1(result.text.encode("utf-8", "ignore")).hexdigest()[:16]
            if result is not None
            else (prior.etag if prior else None)
        )
        await self._checkpoint.save(
            CheckpointRecord(
                url=url,
                domain=domain,
                depth=depth,
                visited_at=now,
                etag=fingerprint,  # content fingerprint (no header ETag from the D1 fetcher)
                last_modified=None,
                last_crawl=now,
                failure_count=(prior.failure_count if prior else 0) + (0 if success else 1),
                robots_version=None,
            )
        )
