"""Phase 3F live verification (not a test).

Ingests the real catalog, projects it into the knowledge graph, and reports the ecosystem:
how many organizations, communities, recurring series, speakers, venues, and cities were
detected — plus sample entity queries.

Run (from backend/):  PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m spikes.m3f_entities
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

logging.disable(logging.CRITICAL)

from app.entities import GraphBuilder, entity_report  # noqa: E402
from app.entities.models import EntityType  # noqa: E402
from app.entities.queries import EntityQueries  # noqa: E402
from app.ingestion.registry import build_registry  # noqa: E402
from app.scheduler import IngestionEngine  # noqa: E402
from app.storage.models import SearchCriteria  # noqa: E402
from app.storage.sqlite_provider_state import SQLiteProviderStateStore  # noqa: E402
from app.storage.sqlite_repository import SQLiteEventRepository  # noqa: E402


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="m3f_"))
    repo = SQLiteEventRepository(str(tmp / "events.db"))
    state = SQLiteProviderStateStore(str(tmp / "state.db"))

    print("=== INGEST ===")
    engine = IngestionEngine(build_registry(), repo, state, clock=lambda: datetime.now(UTC), concurrency=4)
    await engine.run_cycle()
    await engine.shutdown()
    total = await repo.count(SearchCriteria())
    print(f"catalog: {total} active events")

    print("\n=== BUILD KNOWLEDGE GRAPH ===")
    stored = [se async for se in repo.iterate(SearchCriteria(active_only=True))]
    graph = GraphBuilder().build(stored)
    counts = graph.counts()
    print("entities detected:")
    for t in (
        EntityType.ORGANIZATION,
        EntityType.COMMUNITY,
        EntityType.EVENT_SERIES,
        EntityType.SPEAKER,
        EntityType.VENUE,
        EntityType.CITY,
    ):
        print(f"  {t.value:14s}: {counts.get(t.value, 0)}")
    recurring = [e for e in graph.entities(EntityType.EVENT_SERIES) if e.event_count >= 2]
    print(f"  recurring series (>=2 editions): {len(recurring)}")

    report = entity_report(graph)

    print("\n=== TOP COMMUNITIES ===")
    for c in report["top_communities"][:6]:
        print(f"  {c['name']:26s} events={c['events']:2d} chapters={len(c['chapters'])}")

    print("\n=== TOP ORGANIZERS ===")
    for o in report["top_organizers"][:6]:
        print(f"  {o['name']:26s} events={o['events']:2d} cities={len(o['cities'])}")

    print("\n=== RECURRING SERIES ===")
    for s in report["recurring_series"][:8]:
        print(f"  {s['name'][:40]:40s} editions={s['editions']}")

    print("\n=== CITY ECOSYSTEM (top 6) ===")
    for c in report["city_ecosystem"][:6]:
        print(f"  {c['city']:16s} events={c['events']:3d} communities={len(c['communities'])}")

    print("\n=== SAMPLE ENTITY QUERIES (search foundation) ===")
    queries = EntityQueries(graph)
    print(f"  events by community 'GDG'    -> {len(queries.events_by_community('GDG'))}")
    print(f"  events by community 'CNCF'   -> {len(queries.events_by_community('CNCF'))}")
    print(f"  events by organization 'Google' -> {len(queries.events_by_organization('Google'))}")
    print(f"  events by speaker 'anyone'   -> {len(queries.events_by_speaker('anyone'))} (no speaker data yet)")

    await repo.close()
    await state.close()


if __name__ == "__main__":
    asyncio.run(main())
