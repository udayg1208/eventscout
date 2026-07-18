"""Phase 3C live verification (not a test).

Runs the real seven providers through the production ingestion pipeline into a fresh
in-memory catalog + provider-state store, then prints the sandbox preview, per-provider
ingestion reports, aggregate, provider state, an incremental re-run, and a catalog
sample. Sequential, one provider at a time — no scheduler, no workers.

Run (from backend/):  PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m spikes.m3c_ingest
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

logging.disable(logging.CRITICAL)

from app.ingestion import build_registry, render_report, run_ingestion, run_sandbox  # noqa: E402
from app.ingestion.sandbox import render_sandbox_report  # noqa: E402
from app.storage.models import SearchCriteria  # noqa: E402
from app.storage.sqlite_provider_state import SQLiteProviderStateStore  # noqa: E402
from app.storage.sqlite_repository import SQLiteEventRepository  # noqa: E402


async def main() -> None:
    now = datetime.now(UTC)
    registry = build_registry()
    repo = SQLiteEventRepository()
    state = SQLiteProviderStateStore()

    print("=== SANDBOX PREVIEW (gdg) — no production storage touched ===")
    print(render_sandbox_report(await run_sandbox(registry.get("gdg"))))

    print("\n=== INGESTION RUN 1 — all 7 providers ===")
    reports = []
    for plugin in registry.all():
        report = await run_ingestion(plugin, repo, state, now=now)
        reports.append(report)
        print(render_report(report))

    catalog = await repo.count(SearchCriteria())
    print(
        f"\nAGGREGATE: fetched={sum(r.fetched for r in reports)} "
        f"accepted={sum(r.accepted for r in reports)} "
        f"duplicates={sum(r.duplicates for r in reports)} "
        f"rejected={sum(r.rejected for r in reports)} -> catalog_active={catalog}"
    )

    print("\n=== PROVIDER STATE ===")
    summary = await state.provider_health_summary()
    print(f"fleet: {summary.total} providers, health={summary.by_health}, "
          f"runs={summary.total_runs} ok={summary.total_successes} fail={summary.total_failures}")
    for pid in registry.ids():
        s = await state.get_provider_state(pid)
        nxt = s.next_run_at.strftime("%H:%M") if s.next_run_at else "-"
        print(
            f"  {pid:12s} runs={s.total_runs} ok={s.total_successes} fail={s.total_failures} "
            f"events~{s.avg_events:.0f} {s.health_status.value:8s} next={nxt} "
            f"checkpoint={'yes' if s.checkpoint else 'no'}"
        )

    print("\n=== INGESTION RUN 2 — incremental (expect all unchanged) ===")
    for plugin in registry.all():
        r = await run_ingestion(plugin, repo, state, now=now)
        print(f"  {r.provider_id:12s} +{r.inserted} new / ~{r.updated} upd / ={r.unchanged} same")

    print("\n=== CATALOG SAMPLE (first 8 by date) ===")
    page = await repo.search(SearchCriteria(limit=8))
    for r in page.items:
        print(f"  [{r.event.category.value:10s}] {r.event.title[:44]:44s} {r.event.city or '-'}")

    await repo.close()
    await state.close()


if __name__ == "__main__":
    asyncio.run(main())
