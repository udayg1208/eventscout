"""Phase 6D / D1 live verification (not a test): run structured discovery over real seeds.

Crawls a small curated seed list, persists candidates + crawl checkpoints to SQLite, and
reports discovery stats + a second (incremental) run proving duplicates are prevented.
Polite: robots-respecting, rate-limited, bounded. Nothing reaches the catalog.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

logging.disable(logging.CRITICAL)

from app.discovery import (  # noqa: E402
    DiscoveryEngine,
    HttpxFetcher,
    Seed,
    SQLiteCrawlCheckpointStore,
    SQLiteDiscoveryInbox,
)

SEEDS = [
    Seed("https://hasgeek.com/", {"hasgeek.com"}, "Hasgeek"),
    Seed("https://fossunited.org/", {"fossunited.org"}, "FOSS United"),
    Seed("https://gdg.community.dev/", {"community.dev"}, "GDG"),
    Seed("https://community2.cncf.io/", {"community2.cncf.io", "cncf.io"}, "CNCF"),
    Seed("https://lu.ma/", {"lu.ma"}, "Lu.ma"),
]


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="d1_"))
    inbox = SQLiteDiscoveryInbox(str(tmp / "candidates.db"))
    checkpoint = SQLiteCrawlCheckpointStore(str(tmp / "crawl.db"))
    engine = DiscoveryEngine(
        HttpxFetcher(timeout=12.0),
        inbox,
        checkpoint=checkpoint,
        max_pages=18,
        max_depth=2,
        min_interval=0.2,
        sleep=asyncio.sleep,
    )

    print("=== RUN 1 — structured discovery over 5 seeds (network) ===")
    report = await engine.run(SEEDS)
    print(f"{'seed':22s} {'pages':>6} {'cands':>6}  feed types")
    for s in report.per_seed:
        print(f"  {s.seed:20s} {s.pages_fetched:>6} {s.candidates:>6}  {s.by_feed_type}")
    print(
        f"\nAGGREGATE: pages={report.pages_fetched} candidates_found={report.candidates_found} "
        f"inserted={report.inserted} updated={report.updated} (within-run dedup)"
    )
    print(f"by feed type: {report.by_feed_type}")
    print(f"inbox total candidates: {await inbox.count()}")
    print(f"crawl checkpoints persisted: {await checkpoint.visited_count()}")

    print("\n=== CANDIDATE SAMPLE ===")
    for c in (await inbox.list(limit=12)):
        print(
            f"  [{c.feed_type.value:14s}] {c.domain:22s} sd={c.structured_data_score} "
            f"tech={c.technology_confidence} india={c.india_confidence} "
            f"ev={c.signals.event_count} :: {(c.title or '')[:38]}"
        )

    print("\n=== RUN 2 — same checkpoint (expect incremental skip → no re-crawl, no dup candidates) ===")
    report2 = await engine.run(SEEDS)
    print(
        f"pages={report2.pages_fetched} inserted={report2.inserted} updated={report2.updated} "
        f"-> inbox still {await inbox.count()} candidates (duplicates prevented)"
    )

    await inbox.close()
    await checkpoint.close()


if __name__ == "__main__":
    asyncio.run(main())
