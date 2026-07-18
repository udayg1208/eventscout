"""Phase 4B benchmark (not a test): current search (LIKE window + rank) vs the new
retrieval pipeline (FTS keyword + entity + structured, RRF-fused, then rank).

Synthetic, deterministic, no network. Scales the catalog to show where LIKE degrades and
FTS stays flat. Prints a table used to fill SEARCH_BENCHMARK.md.

Run (from backend/):  PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m spikes.m4b_benchmark
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, date, datetime, timedelta

from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.providers.ranking import rank
from app.search.criteria import to_criteria
from app.search.db_provider import DatabaseSearchProvider
from app.storage.models import StoredEvent
from app.storage.sqlite_repository import SQLiteEventRepository

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
TODAY = date(2026, 7, 15)
LIMIT = 500

TOPICS = ["AI", "Cloud", "Kubernetes", "Python", "Rust", "Golang", "DevOps", "Security",
          "Data", "Frontend", "Blockchain", "Quantum"]
FORMATS = ["Summit", "Meetup", "Workshop", "Conference", "Bootcamp"]
CITIES = ["Bangalore", "Delhi", "Mumbai", "Pune", "Hyderabad", "Chennai"]


def synth(n: int) -> list[Event]:
    events = []
    for i in range(n):
        title = f"{TOPICS[i % len(TOPICS)]} {FORMATS[i % len(FORMATS)]} {i}"
        if i % 200 == 0:  # a *selective* term (~0.5% of events) — the LIKE-scan worst case
            title += " Serverless"
        events.append(
            Event(
                title=title,
                url=f"https://x.example.com/e{i}",
                city=CITIES[i % len(CITIES)],
                provider="synth",
                start_date=TODAY + timedelta(days=1 + i % 300),
                category=EventCategory.MEETUP,
            )
        )
    return events


async def _old_search(repo, query):
    page = await repo.search(to_criteria(query, today=TODAY, limit=LIMIT))
    return rank([s.event for s in page.items], query, TODAY)


async def _bench(fn, iters=25):
    await fn()  # warm up
    start = time.perf_counter()
    for _ in range(iters):
        await fn()
    return (time.perf_counter() - start) / iters * 1000  # ms/query


async def main() -> None:
    print(f"{'N':>7} {'query':<20} {'OLD (LIKE) ms':>14} {'NEW (pipeline) ms':>18} {'results':>8}")
    print("-" * 72)
    for n in (200, 2000, 10000):
        events = synth(n)
        repo = SQLiteEventRepository()
        await repo.bulk_upsert([StoredEvent.from_event(e, seen_at=NOW) for e in events])
        provider = DatabaseSearchProvider(repo, clock=lambda: TODAY, candidate_limit=LIMIT)
        await provider.refresh()  # build FTS + graph projections once

        for label, query in [
            ("keyword 'ai' (common)", SearchQuery(keywords=["ai"])),
            ("keyword 'serverless' (0.5%)", SearchQuery(keywords=["serverless"])),
            ("city Bangalore", SearchQuery(city="Bangalore")),
            ("browse (empty)", SearchQuery()),
        ]:
            old_ms = await _bench(lambda q=query: _old_search(repo, q))
            new_ms = await _bench(lambda q=query: provider.search(q))
            results = len(await provider.search(query))
            print(f"{n:>7} {label:<20} {old_ms:>14.3f} {new_ms:>18.3f} {results:>8}")
        await repo.close()
        print("-" * 72)

    # a detailed single-run view of the pipeline internals at N=10000
    events = synth(10000)
    repo = SQLiteEventRepository()
    await repo.bulk_upsert([StoredEvent.from_event(e, seen_at=NOW) for e in events])
    provider = DatabaseSearchProvider(repo, clock=lambda: TODAY, candidate_limit=LIMIT)
    await provider.refresh()
    for label, query in [
        ("keyword 'kubernetes'", SearchQuery(keywords=["kubernetes"])),
        ("hybrid 'ai' + Bangalore", SearchQuery(keywords=["ai"], city="Bangalore")),
    ]:
        await provider.search(query)
    print("\nPipeline metrics @N=10000:")
    for k, v in provider.metrics.snapshot().items():
        print(f"  {k}: {v}")
    await repo.close()


if __name__ == "__main__":
    asyncio.run(main())
