"""Phase 6E / D2 live verification (not a test): framework discovery over real seeds.

Crawls the same 5 seeds as the D1 spike ONCE (polite: robots-respecting, rate-limited, bounded)
and, per page, measures what D1 (`detect_feeds`) finds versus what D2 (`analyze_frameworks`) adds:
frameworks detected, embedded events recovered, client API / GraphQL endpoints, and the net-new
candidate sources D2 contributes. No JavaScript is executed; nothing reaches the catalog.

Metrics reported (as the phase brief asks): pages crawled, framework detected, embedded events
found, new candidate sources, candidate quality, false positives — compared directly against D1.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from collections import Counter
from pathlib import Path

logging.disable(logging.CRITICAL)

from app.discovery import (  # noqa: E402
    HttpxFetcher,
    Seed,
    SQLiteCrawlCheckpointStore,
    SQLiteDiscoveryInbox,
)
from app.discovery.analysis import analyze_frameworks  # noqa: E402
from app.discovery.candidates import build_candidate  # noqa: E402
from app.discovery.crawler import Crawler  # noqa: E402
from app.discovery.engine import _NOT_A_CANDIDATE, _merge_detections  # noqa: E402
from app.discovery.feeds import detect_feeds  # noqa: E402
from app.discovery.links import extract_page_links  # noqa: E402
from app.discovery.models import ENDPOINT_FEEDS, FeedType  # noqa: E402
from app.discovery.robots import RobotsCache  # noqa: E402
from app.discovery.signals import collect_signals  # noqa: E402
from app.discovery.store import utcnow  # noqa: E402

SEEDS = [
    Seed("https://gdg.community.dev/", {"community.dev"}, "GDG"),
    Seed("https://lu.ma/", {"lu.ma"}, "Lu.ma"),
    Seed("https://hasgeek.com/", {"hasgeek.com"}, "Hasgeek"),
    Seed("https://fossunited.org/", {"fossunited.org"}, "FOSS United"),
    Seed("https://community2.cncf.io/", {"community2.cncf.io", "cncf.io"}, "CNCF"),
]


class SeedMetrics:
    def __init__(self, name: str) -> None:
        self.name = name
        self.pages = 0
        self.pages_with_framework = 0
        self.pages_with_events = 0
        self.embedded_events = 0
        self.frameworks: Counter[str] = Counter()
        self.api_endpoints: set[str] = set()
        self.graphql_endpoints: set[str] = set()
        self.d1_keys: set[str] = set()
        self.all_keys: set[str] = set()
        self.d2_feed_types: Counter[str] = Counter()

    @property
    def d2_new(self) -> int:
        return len(self.all_keys - self.d1_keys)


def _candidate_keys(result, detections, analysis) -> set[str]:
    """Keys the inbox would assign to these detections (mirrors the engine's build step)."""
    sig = collect_signals(result, detections, [], analysis)
    keys: set[str] = set()
    for det in detections:
        if det.feed_type in _NOT_A_CANDIDATE:
            continue
        cand = build_candidate(
            result=result,
            detection=det,
            signals=sig,
            discovery_path=[],
            now=utcnow(),
            analysis=analysis,
        )
        keys.add(cand.key)
    return keys


async def _crawl_seed(seed: Seed, crawler: Crawler, inbox: SQLiteDiscoveryInbox) -> SeedMetrics:
    m = SeedMetrics(seed.organization or seed.url)
    async for page in crawler.crawl(seed.url, seed.scope()):
        m.pages += 1
        html_low = page.result.text.lower()
        page_links = extract_page_links(page.result.text, page.url) if "<a " in html_low else []

        d1 = detect_feeds(page.result)
        analysis = analyze_frameworks(page.result)
        merged = _merge_detections(d1, analysis.detections)

        if analysis.framework:
            m.pages_with_framework += 1
            m.frameworks[f"{analysis.framework} {analysis.framework_version or ''}".strip()] += 1
        if analysis.embedded_event_count:
            m.pages_with_events += 1
            m.embedded_events += analysis.embedded_event_count
        m.api_endpoints.update(analysis.api_endpoints)
        m.graphql_endpoints.update(analysis.graphql_endpoints)
        for det in analysis.detections:
            m.d2_feed_types[det.feed_type.value] += 1

        m.d1_keys |= _candidate_keys(page.result, d1, None)
        m.all_keys |= _candidate_keys(page.result, merged, analysis)

        # persist the real (merged) candidates so the inbox reflects D1+D2 together
        sig = collect_signals(page.result, merged, page_links, analysis)
        for det in merged:
            if det.feed_type in _NOT_A_CANDIDATE:
                continue
            cand = build_candidate(
                result=page.result,
                detection=det,
                signals=sig,
                discovery_path=list(page.path),
                now=utcnow(),
                analysis=analysis,
            )
            await inbox.upsert(cand)
    return m


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="d2_"))
    inbox = SQLiteDiscoveryInbox(str(tmp / "candidates.db"))
    checkpoint = SQLiteCrawlCheckpointStore(str(tmp / "crawl.db"))
    fetcher = HttpxFetcher(timeout=12.0)
    robots = RobotsCache(fetcher)

    print("=== D2 live verification — framework discovery over 5 seeds (network, no JS) ===\n")
    metrics: list[SeedMetrics] = []
    for seed in SEEDS:
        crawler = Crawler(
            fetcher,
            robots,
            checkpoint=checkpoint,
            max_pages=18,
            max_depth=2,
            min_interval=0.2,
            sleep=asyncio.sleep,
        )
        m = await _crawl_seed(seed, crawler, inbox)
        metrics.append(m)
        fw = ", ".join(f"{k}×{v}" for k, v in m.frameworks.most_common(3)) or "—"
        print(
            f"  {m.name:12s} pages={m.pages:>3}  framework=[{fw}]  "
            f"embedded_events={m.embedded_events:>4}  "
            f"D1_cands={len(m.d1_keys):>2}  D2_new={m.d2_new:>2}  "
            f"api={len(m.api_endpoints):>2} gql={len(m.graphql_endpoints)}"
        )

    print("\n=== D1 vs D2 AGGREGATE ===")
    tot_pages = sum(m.pages for m in metrics)
    tot_events = sum(m.embedded_events for m in metrics)
    tot_d1 = sum(len(m.d1_keys) for m in metrics)
    tot_d2_new = sum(m.d2_new for m in metrics)
    tot_api = sum(len(m.api_endpoints) for m in metrics)
    tot_gql = sum(len(m.graphql_endpoints) for m in metrics)
    frameworks: Counter[str] = Counter()
    d2_types: Counter[str] = Counter()
    for m in metrics:
        frameworks.update(m.frameworks)
        d2_types.update(m.d2_feed_types)
    print(f"  pages crawled ............ {tot_pages}")
    print(f"  frameworks detected ...... {dict(frameworks)}")
    print(f"  embedded events found .... {tot_events}")
    print(f"  D1 candidate sources ..... {tot_d1}")
    print(f"  D2 NET-NEW candidates .... {tot_d2_new}   (sources D1 alone could not see)")
    print(f"  D2 detection feed types .. {dict(d2_types)}")
    print(f"  API endpoints discovered . {tot_api}")
    print(f"  GraphQL endpoints ........ {tot_gql}")
    print(f"  inbox total (D1+D2) ...... {await inbox.count()}")

    # false-positive lens: framework present but ZERO embedded events (correctly NOT a candidate)
    fp_pages = sum(m.pages_with_framework - m.pages_with_events for m in metrics)
    print(
        f"\n  false-positive guard: {fp_pages} framework page(s) had 0 events → emitted NO "
        "event candidate (endpoint-only pages may still yield a probe candidate)"
    )

    # a candidate's ORIGIN is its detection feed type — D2 owns the framework/embedded/endpoint
    # feed types; everything else came from a D1 detector (even if D2 attached framework metadata).
    d2_origin = {
        FeedType.NEXT_DATA, FeedType.NEXT_FLIGHT, FeedType.HYDRATION_STATE,
        FeedType.EMBEDDED_JSON, *ENDPOINT_FEEDS,
    }
    print("\n=== CANDIDATE SAMPLE (origin = detection feed type; fw = attached page framework) ===")
    for c in await inbox.list(limit=16):
        tag = "D2" if c.feed_type in d2_origin else "D1"
        print(
            f"  [{tag}][{c.feed_type.value:14s}] {c.domain:20s} "
            f"fw={c.framework or '-':16s} ev={c.embedded_event_count:>3} "
            f"api={len(c.api_endpoints)} :: {(c.title or '')[:34]}"
        )

    await inbox.close()
    await checkpoint.close()


if __name__ == "__main__":
    asyncio.run(main())
