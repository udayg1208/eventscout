"""Phase 3G live verification (not a test): ingest all providers, measure coverage.

Runs every registered provider through the production pipeline into a fresh catalog and
reports per-provider yield + aggregate coverage (providers, events, cities, categories,
duplicate rate, health) — the milestone metrics.

Run (from backend/):  PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m spikes.m3g_verify
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import UTC, datetime

logging.disable(logging.CRITICAL)

from app.ingestion import build_registry, run_ingestion  # noqa: E402
from app.storage.models import SearchCriteria  # noqa: E402
from app.storage.sqlite_provider_state import SQLiteProviderStateStore  # noqa: E402
from app.storage.sqlite_repository import SQLiteEventRepository  # noqa: E402

NEW = {"atlassian", "salesforce", "snowflake", "devpost"}


async def main() -> None:
    now = datetime.now(UTC)
    registry = build_registry()
    repo = SQLiteEventRepository()
    state = SQLiteProviderStateStore()

    print(f"=== INGESTION — {len(registry.all())} providers ===")
    print(f"{'provider':14s} {'fetch':>6} {'acc':>5} {'dup':>4} {'rej':>4} {'ins':>5} {'err':>4}  new?")
    reports = []
    for plugin in registry.all():
        r = await run_ingestion(plugin, repo, state, now=now)
        reports.append(r)
        flag = "NEW" if plugin.id in NEW else ""
        print(
            f"{r.provider_id:14s} {r.fetched:>6} {r.accepted:>5} {r.duplicates:>4} "
            f"{r.rejected:>4} {r.inserted:>5} {len(r.errors):>4}  {flag}"
        )

    fetched = sum(r.fetched for r in reports)
    accepted = sum(r.accepted for r in reports)
    duplicates = sum(r.duplicates for r in reports)
    active = await repo.count(SearchCriteria(active_only=True))
    dup_rate = duplicates / accepted if accepted else 0.0
    new_events = sum(r.accepted for r in reports if r.provider_id in NEW)

    print(
        f"\nAGGREGATE: fetched={fetched} accepted={accepted} duplicates={duplicates} "
        f"(dup_rate={dup_rate:.1%}) -> catalog_active={active}"
    )
    print(f"NEW providers contributed accepted={new_events} events")

    events = [s async for s in repo.iterate(SearchCriteria(active_only=True))]
    by_provider = Counter(e.event.provider for e in events)
    by_category = Counter(e.event.category.value for e in events)
    by_city = Counter(e.event.city for e in events if e.event.city)
    online = sum(1 for e in events if e.event.is_online)
    free = sum(1 for e in events if e.event.is_free is True)

    print(f"\nCOVERAGE: providers={len(by_provider)} events={active} "
          f"cities={len(by_city)} categories={len(by_category)} online={online} free={free}")
    print(f"by provider : {dict(by_provider.most_common())}")
    print(f"categories  : {dict(by_category.most_common())}")
    print(f"top cities  : {by_city.most_common(12)}")

    summary = await state.provider_health_summary()
    print(f"\nHEALTH: {summary.total} providers, by_health={summary.by_health}")

    await repo.close()
    await state.close()


if __name__ == "__main__":
    asyncio.run(main())
