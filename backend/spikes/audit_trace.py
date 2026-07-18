"""Data-flow audit — trace counts through EVERY stage on one fresh catalog (real data).

Proves whether any stage between provider and API loses events. Runs a full ingestion into
a temp FILE catalog, then measures: DB active → search-index docs → search results →
platform analytics → homepage. All the post-DB numbers should equal the DB active count.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

logging.disable(logging.CRITICAL)

from app.ingestion import build_registry, run_ingestion  # noqa: E402
from app.models.search import SearchQuery  # noqa: E402
from app.platform import PlatformService  # noqa: E402
from app.search.db_provider import DatabaseSearchProvider  # noqa: E402
from app.storage.models import SearchCriteria  # noqa: E402
from app.storage.sqlite_provider_state import SQLiteProviderStateStore  # noqa: E402
from app.storage.sqlite_repository import SQLiteEventRepository  # noqa: E402


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="audit_"))
    repo = SQLiteEventRepository(str(tmp / "catalog.db"))
    state = SQLiteProviderStateStore(str(tmp / "state.db"))
    now = datetime.now(UTC)
    registry = build_registry()

    # --- STAGE: Provider -> Runner -> normalize/classify/resolve -> bulk_upsert ---
    fetched = accepted = duplicates = rejected = inserted = 0
    for plugin in registry.all():
        r = await run_ingestion(plugin, repo, state, now=now)
        fetched += r.fetched
        accepted += r.accepted
        duplicates += r.duplicates
        rejected += r.rejected
        inserted += r.inserted

    # --- STAGE: Database ---
    db_total = await repo.count(SearchCriteria())
    db_active = await repo.count(SearchCriteria(active_only=True))

    # --- STAGE: Search Index (projection of the catalog) ---
    provider = DatabaseSearchProvider(repo, clock=lambda: now.date())
    await provider.refresh()  # builds FTS index + entity graph from the catalog
    index_docs = await provider._index.count()  # noqa: SLF001 - audit diagnostic

    # --- STAGE: Search Provider (broad query) ---
    broad = await provider.search(SearchQuery())  # empty query = browse/all upcoming

    # --- STAGE: Platform / API ---
    platform = await PlatformService.from_repository(repo, clock=lambda: now)
    analytics_total = platform.analytics().total_events
    discover_all = platform.discover_newest(limit=1000)  # every upcoming event, no display cap

    print("STAGE-BY-STAGE COUNTS (single fresh catalog, real data)")
    print(f"  1 Provider fetch (raw)             : {fetched}")
    print(f"  2 Ingestion accepted (post-filter) : {accepted}   (rejected={rejected} past/invalid, duplicates={duplicates})")
    print(f"  3 Repository bulk_upsert inserted   : {inserted}")
    print(f"  4 Database — total rows             : {db_total}")
    print(f"  5 Database — ACTIVE                 : {db_active}")
    print(f"  6 Search Index — indexed docs       : {index_docs}")
    print(f"  7 Search Provider — broad results   : {len(broad)}  (candidate_limit bounds this)")
    print(f"  8 Platform API — analytics.total    : {analytics_total}")
    print(f"  9 Platform — discover_newest(1000)  : {len(discover_all)}")

    match = db_active == index_docs == analytics_total == len(discover_all)
    print(f"\n  DB active == index == API == discover ?  {'YES ✅' if match else 'NO ❌'}")
    cats = Counter(e.event.category.value for e in [s async for s in repo.iterate(SearchCriteria(active_only=True))])
    print(f"  categories: {dict(cats.most_common())}")

    await repo.close()
    await state.close()


if __name__ == "__main__":
    asyncio.run(main())
