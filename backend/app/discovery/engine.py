"""Discovery Engine orchestrator (D1).

Pipeline: Seed URLs → Crawler → Link Extractor → Feed/Structured Detector → Candidate Builder
→ Confidence Signals → Discovery Inbox. Nothing beyond the inbox — no onboarding, no ingestion.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.discovery.analysis import analyze_frameworks
from app.discovery.candidates import build_candidate
from app.discovery.crawler import Crawler
from app.discovery.feeds import FeedDetection, detect_feeds
from app.discovery.fetch import Fetcher
from app.discovery.links import extract_page_links
from app.discovery.models import FeedType
from app.discovery.robots import RobotsCache
from app.discovery.signals import collect_signals
from app.discovery.store import CrawlCheckpointStore, DiscoveryInbox
from app.discovery.urls import registrable_domain

logger = logging.getLogger("discovery.engine")

# A plain sitemap is a navigation aid (used to enqueue pages), not an ingestible event source.
_NOT_A_CANDIDATE = {FeedType.XML_SITEMAP, FeedType.UNKNOWN}


def _merge_detections(d1: list[FeedDetection], d2: list[FeedDetection]) -> list[FeedDetection]:
    """Union of D1 feed detections and D2 framework detections, deduped by (feed_type, url)."""
    merged: list[FeedDetection] = list(d1)
    seen = {(d.feed_type, d.url) for d in d1}
    for det in d2:
        if (det.feed_type, det.url) not in seen:
            seen.add((det.feed_type, det.url))
            merged.append(det)
    return merged


@dataclass(frozen=True)
class Seed:
    url: str
    domains: set[str] = field(default_factory=set)
    organization: str | None = None

    def scope(self) -> set[str]:
        return self.domains or {registrable_domain(self.url)}


@dataclass
class SeedResult:
    seed: str
    pages_fetched: int
    candidates: int
    by_feed_type: dict[str, int]


@dataclass
class DiscoveryReport:
    seeds: int
    pages_fetched: int
    candidates_found: int
    inserted: int
    updated: int
    by_feed_type: dict[str, int]
    per_seed: list[SeedResult]


class DiscoveryEngine:
    def __init__(
        self,
        fetcher: Fetcher,
        inbox: DiscoveryInbox,
        *,
        checkpoint: CrawlCheckpointStore | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        crawler: Crawler | None = None,
        **crawler_kwargs: object,
    ) -> None:
        self._inbox = inbox
        self._clock = clock
        self._crawler = crawler or Crawler(
            fetcher, RobotsCache(fetcher), checkpoint=checkpoint, clock=clock, **crawler_kwargs
        )

    async def run(self, seeds: list[Seed]) -> DiscoveryReport:
        inserted = updated = found = total_pages = 0
        by_type: Counter[str] = Counter()
        per_seed: list[SeedResult] = []

        for seed in seeds:
            seed_found = 0
            seed_types: Counter[str] = Counter()
            async for page in self._crawler.crawl(seed.url, seed.scope()):
                page_links = (
                    extract_page_links(page.result.text, page.url)
                    if "<a " in page.result.text.lower()
                    else []
                )
                analysis = analyze_frameworks(page.result)
                detections = _merge_detections(detect_feeds(page.result), analysis.detections)
                if not detections:
                    continue
                signals = collect_signals(page.result, detections, page_links, analysis)
                for detection in detections:
                    if detection.feed_type in _NOT_A_CANDIDATE:
                        continue
                    candidate = build_candidate(
                        result=page.result,
                        detection=detection,
                        signals=signals,
                        discovery_path=list(page.path),
                        now=self._clock(),
                        analysis=analysis,
                    )
                    outcome = await self._inbox.upsert(candidate)
                    found += 1
                    seed_found += 1
                    inserted += outcome == "inserted"
                    updated += outcome == "updated"
                    by_type[detection.feed_type.value] += 1
                    seed_types[detection.feed_type.value] += 1

            pages = self._crawler.stats.pages
            total_pages += pages
            per_seed.append(SeedResult(seed.url, pages, seed_found, dict(seed_types)))
            logger.info("discovery: seed=%s pages=%d candidates=%d", seed.url, pages, seed_found)

        return DiscoveryReport(
            seeds=len(seeds),
            pages_fetched=total_pages,
            candidates_found=found,
            inserted=inserted,
            updated=updated,
            by_feed_type=dict(by_type),
            per_seed=per_seed,
        )
