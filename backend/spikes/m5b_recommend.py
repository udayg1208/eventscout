"""Phase 5B live check (not a test): recommend over the real catalog for a simulated user."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

logging.disable(logging.CRITICAL)

from app.ingestion.registry import build_registry  # noqa: E402
from app.scheduler import IngestionEngine  # noqa: E402
from app.storage.models import SearchCriteria  # noqa: E402
from app.storage.sqlite_provider_state import SQLiteProviderStateStore  # noqa: E402
from app.storage.sqlite_repository import SQLiteEventRepository  # noqa: E402
from app.users import Interaction, InteractionType, UserIntelligenceEngine  # noqa: E402


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="m5b_"))
    repo = SQLiteEventRepository(str(tmp / "events.db"))
    state = SQLiteProviderStateStore(str(tmp / "state.db"))
    ingest = IngestionEngine(build_registry(), repo, state, clock=lambda: datetime.now(UTC), concurrency=4)
    await ingest.run_cycle()
    await ingest.shutdown()
    now = datetime.now(UTC)
    print(f"catalog: {await repo.count(SearchCriteria())} events")

    engine = await UserIntelligenceEngine.from_repository(repo)

    # simulate a user: attends 2 AI events, searches kubernetes, saves a GDG event
    events = [s async for s in repo.iterate(SearchCriteria(active_only=True))]
    ai_events = [s for s in events if "ai" in s.event.title.lower() or "gemma" in s.event.title.lower()][:2]
    gdg_events = [s for s in events if s.event.provider == "gdg"][:1]
    for s in ai_events:
        engine.record_interaction(Interaction("u1", InteractionType.ATTEND, now, event_key=s.key))
    for s in gdg_events:
        engine.record_interaction(Interaction("u1", InteractionType.SAVE, now, event_key=s.key))
    engine.record_interaction(Interaction("u1", InteractionType.SEARCH, now, query="kubernetes and cloud"))

    profile = engine.profiles.get("u1")
    print(f"\nprofile after {profile.interaction_count} interactions (attended={profile.attended_count}):")
    print(f"  top topics      : {profile.top('topic', 5)}")
    print(f"  top communities : {profile.top('community', 3)}")
    print(f"  preferred format: {profile.preferred_format}  budget: {profile.budget_preference}")

    print("\ntop recommendations:")
    for rec in engine.recommend("u1", now=now, limit=5):
        stored = next(s for s in events if s.key == rec.event_key)
        print(f"  [{rec.score:.3f}] {stored.event.title[:44]}")
        for reason in rec.reasons:
            print(f"           - {reason}")

    print("\nuser analytics:")
    for k, v in engine.analytics("u1").items():
        print(f"  {k}: {v}")

    await repo.close()
    await state.close()


if __name__ == "__main__":
    asyncio.run(main())
