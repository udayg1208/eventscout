"""Populate the configured catalog.db with one ingestion cycle, so the frontend has data.

Run once before starting the API for a live frontend demo:
    PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m spikes.seed_catalog

Writes to the SAME catalog_db_path / provider_state_db_path the API reads (app/config.py),
i.e. backend/catalog.db + backend/provider_state.db. Hits the network (real providers).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.catalog import get_repository, get_state_store
from app.ingestion.registry import build_registry
from app.scheduler import IngestionEngine
from app.storage.models import SearchCriteria


async def main() -> None:
    repo = get_repository()
    state = get_state_store()
    engine = IngestionEngine(
        build_registry(), repo, state, clock=lambda: datetime.now(UTC), concurrency=4
    )
    print("running one ingestion cycle (network)...")
    await engine.run_cycle()
    await engine.shutdown()
    total = await repo.count(SearchCriteria())
    active = await repo.count(SearchCriteria(active_only=True))
    print(f"catalog seeded: {active} active / {total} total events")
    print("start the API:  uvicorn app.main:app --reload")


if __name__ == "__main__":
    asyncio.run(main())
