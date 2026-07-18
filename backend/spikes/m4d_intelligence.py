"""Phase 4D live verification (not a test).

Ingests the real catalog, then runs the Continuous Event Intelligence engine over it and
prints the analytics it produces (change detection, lifecycle distribution, trending,
organizer/community intelligence). Re-runs to show cross-run change detection.

Run (from backend/):  PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m spikes.m4d_intelligence
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

logging.disable(logging.CRITICAL)

from app.ingestion.registry import build_registry  # noqa: E402
from app.intelligence import IntelligenceEngine  # noqa: E402
from app.scheduler import IngestionEngine  # noqa: E402
from app.storage.models import SearchCriteria  # noqa: E402
from app.storage.sqlite_provider_state import SQLiteProviderStateStore  # noqa: E402
from app.storage.sqlite_repository import SQLiteEventRepository  # noqa: E402


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="m4d_"))
    repo = SQLiteEventRepository(str(tmp / "events.db"))
    state = SQLiteProviderStateStore(str(tmp / "state.db"))
    registry = build_registry()

    print("=== INGEST ===")
    ingest = IngestionEngine(registry, repo, state, clock=lambda: datetime.now(UTC), concurrency=4)
    await ingest.run_cycle()
    await ingest.shutdown()
    print(f"catalog: {await repo.count(SearchCriteria())} active events")

    provider_states = [s for pid in registry.ids() if (s := await state.get_provider_state(pid))]

    print("\n=== INTELLIGENCE RUN 1 ===")
    now = datetime.now(UTC)
    engine = IntelligenceEngine()
    report = await engine.run(repo, provider_states=provider_states, now=now)

    print(f"changes: {report.change_counts}")
    print(f"lifecycle: {report.lifecycle_distribution}")

    print("\n-- trending (top 6) --")
    for t in report.trending[:6]:
        print(f"  {t.score:.3f}  {t.title[:46]}")

    print("\n-- organizer profiles (top 6) --")
    for p in report.organizer_profiles[:6]:
        print(f"  [{p.entity_type:12s}] {p.name[:24]:24s} total={p.total_events:2d} "
              f"active={p.active_events:2d} quality={p.average_quality:.2f} cities={len(p.cities)}")

    print("\n-- community insights --")
    ins = report.community_insights
    print(f"  fastest growing : {[c['name'] for c in ins.fastest_growing]}")
    print(f"  most active cities: {[(c['city'], c['events']) for c in ins.most_active_cities]}")
    print(f"  recurring series : {[s['name'] for s in ins.recurring_series]}")
    print(f"  inactive communities: {[c['name'] for c in ins.inactive_communities]}")

    print("\n-- analytics --")
    print(json.dumps(report.analytics, default=str, indent=1)[:900])

    print("\n=== INTELLIGENCE RUN 2 (no ingestion between) — change detection ===")
    report2 = await engine.run(repo, provider_states=provider_states, now=now)
    print(f"changes: {report2.change_counts}  (new should be 0 — nothing changed)")

    await repo.close()
    await state.close()


if __name__ == "__main__":
    asyncio.run(main())
