"""Phase 3E live verification (not a test) — the cutover proof.

1. The scheduler/ingestion engine populates the catalog from the real providers.
2. The engine is SHUT DOWN (providers no longer running).
3. Searches are served entirely from the Repository — no provider is ever touched.
4. A fresh search provider with NO engine and NO providers still answers over the DB.
5. After a restart (reopen the durable catalog), searches still work.

This demonstrates the application is now independent of live provider availability.

Run (from backend/):  PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m spikes.m3e_cutover
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

logging.disable(logging.CRITICAL)

from app.cache import TTLCache  # noqa: E402
from app.ingestion.registry import build_registry  # noqa: E402
from app.models.event import EventCategory  # noqa: E402
from app.models.search import SearchQuery  # noqa: E402
from app.parsers.keyword import KeywordQueryParser  # noqa: E402
from app.scheduler import IngestionEngine  # noqa: E402
from app.search.analytics import SearchAnalytics  # noqa: E402
from app.search.cache import InMemorySearchCache  # noqa: E402
from app.search.db_provider import DatabaseSearchProvider  # noqa: E402
from app.services.search_service import SearchService  # noqa: E402
from app.storage.models import SearchCriteria  # noqa: E402
from app.storage.sqlite_provider_state import SQLiteProviderStateStore  # noqa: E402
from app.storage.sqlite_repository import SQLiteEventRepository  # noqa: E402

QUERIES = [
    ("everything", SearchQuery()),
    ("AI category", SearchQuery(categories=[EventCategory.AI])),
    ("in Bangalore", SearchQuery(city="Bangalore")),
    ("keyword 'ai'", SearchQuery(keywords=["ai"])),
    ("free only", SearchQuery(free_only=True)),
]


async def run_searches(provider: DatabaseSearchProvider, label: str) -> None:
    print(f"\n--- {label} ---")
    for name, query in QUERIES:
        start = time.perf_counter()
        results = await provider.search(query)
        ms = (time.perf_counter() - start) * 1000
        top = results[0].title[:38] if results else "(none)"
        print(f"  {name:14s} -> {len(results):3d} results in {ms:6.2f} ms   top: {top}")


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="m3e_"))
    repo_path, state_path = str(tmp / "events.db"), str(tmp / "state.db")

    print("=== PHASE 1: INGEST (engine populates the catalog from real providers) ===")
    repo = SQLiteEventRepository(repo_path)
    state = SQLiteProviderStateStore(state_path)
    engine = IngestionEngine(build_registry(), repo, state, clock=lambda: datetime.now(UTC), concurrency=4)
    await engine.run_cycle()
    catalog = await repo.count(SearchCriteria())
    print(f"catalog populated: {catalog} active events")

    print("\n=== PHASE 2: STOP the engine — providers are no longer running ===")
    await engine.shutdown()
    print("ingestion engine stopped.")

    print("\n=== PHASE 3: SEARCH — served entirely from the Repository ===")
    analytics = SearchAnalytics()
    provider = DatabaseSearchProvider(repo, cache=InMemorySearchCache(60), analytics=analytics)
    await run_searches(provider, "searches (providers stopped)")
    # repeat one query → cache hit
    await provider.search(SearchQuery(categories=[EventCategory.AI]))
    print(f"\ncache hits so far: {analytics.cache_hits}")

    # natural-language path through the unchanged SearchService (keyword parser, no network)
    service = SearchService(
        parser=KeywordQueryParser(), provider=provider, parse_cache=TTLCache(60), results_cache=TTLCache(60)
    )
    nl = await service.search("ai events in bangalore")
    print(f"NL search 'ai events in bangalore' -> {len(nl.events)} results (via SearchService, unchanged)")

    print("\n=== PHASE 4: PROOF — a fresh search provider with NO engine, NO providers ===")
    bare_provider = DatabaseSearchProvider(repo)  # nothing but the catalog
    results = await bare_provider.search(SearchQuery(categories=[EventCategory.AI]))
    print(f"bare provider (zero provider ecosystem) -> {len(results)} AI events. Independent of live providers.")
    await repo.close()
    await state.close()

    print("\n=== PHASE 5: RESTART — reopen the durable catalog, search again ===")
    repo2 = SQLiteEventRepository(repo_path)
    provider2 = DatabaseSearchProvider(repo2, cache=InMemorySearchCache(60))
    await run_searches(provider2, "searches after restart")
    print(f"\ncatalog after restart: {await repo2.count(SearchCriteria())} active events")
    await repo2.close()

    print("\n=== SEARCH ANALYTICS ===")
    for k, v in analytics.snapshot().items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
