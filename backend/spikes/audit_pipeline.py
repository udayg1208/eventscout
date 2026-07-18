"""Data-flow audit (Phase 3G debugging) — count events at each persisted stage.

Reads the SAME catalog.db / provider_state.db the running API reads (config paths), so we
measure the real source of truth, not a throwaway in-memory run. Read-only.
"""

from __future__ import annotations

import asyncio
from collections import Counter

from app.catalog import get_repository, get_state_store
from app.config import get_settings
from app.storage.models import SearchCriteria


async def main() -> None:
    s = get_settings()
    print(f"catalog_db_path       = {s.catalog_db_path}")
    print(f"provider_state_db_path= {s.provider_state_db_path}")

    repo = get_repository()
    total = await repo.count(SearchCriteria())
    active = await repo.count(SearchCriteria(active_only=True))
    print(f"\n[catalog.db] total rows (any status) = {total}")
    print(f"[catalog.db] ACTIVE events            = {active}")

    events = [s async for s in repo.iterate(SearchCriteria(active_only=True))]
    by_provider = Counter(e.event.provider for e in events)
    print(f"[catalog.db] active by provider ({len(by_provider)} providers):")
    for prov, n in by_provider.most_common():
        print(f"    {prov:34s} {n}")

    state = get_state_store()
    summary = await state.provider_health_summary()
    print(f"\n[provider_state.db] providers with state rows = {summary.total}")
    print(f"    total_runs={summary.total_runs} ok={summary.total_successes} fail={summary.total_failures}")

    await repo.close()
    await state.close()


if __name__ == "__main__":
    asyncio.run(main())
