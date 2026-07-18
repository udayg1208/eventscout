"""Phase 6A live check (not a test): drive the PlatformService facade over the real catalog."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

logging.disable(logging.CRITICAL)

from app.ingestion.registry import build_registry  # noqa: E402
from app.models.search import SearchQuery  # noqa: E402
from app.platform import PlatformService  # noqa: E402
from app.scheduler import IngestionEngine  # noqa: E402
from app.storage.models import SearchCriteria  # noqa: E402
from app.storage.sqlite_provider_state import SQLiteProviderStateStore  # noqa: E402
from app.storage.sqlite_repository import SQLiteEventRepository  # noqa: E402
from app.users import Interaction, InteractionType  # noqa: E402


def _titles(dtos, n=3):
    return " | ".join(d.title[:34] for d in dtos[:n]) or "(none)"


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="m6a_"))
    repo = SQLiteEventRepository(str(tmp / "events.db"))
    state = SQLiteProviderStateStore(str(tmp / "state.db"))
    ingest = IngestionEngine(build_registry(), repo, state, clock=lambda: datetime.now(UTC), concurrency=4)
    await ingest.run_cycle()
    await ingest.shutdown()
    print(f"catalog: {await repo.count(SearchCriteria())} events\n")

    platform = await PlatformService.from_repository(repo)

    print("=== HOMEPAGE (per_section=3, city=Bangalore) ===")
    hp = platform.homepage(city="Bangalore", per_section=3)
    for name, events in hp.sections.items():
        print(f"  {name:22s} [{len(events)}] {_titles(events)}")

    print("\n=== DISCOVERY ===")
    print(f"  trending      : {_titles(platform.discover_trending())}")
    print(f"  newest        : {_titles(platform.discover_newest())}")
    print(f"  closing soon  : {_titles(platform.discover_registration_closing())}")
    print(f"  free          : {_titles(platform.discover_free())}")
    print(f"  online        : {_titles(platform.discover_online())}")
    print(f"  this weekend  : {_titles(platform.discover_this_weekend())}")

    print("\n=== BROWSE ===")
    print(f"  category=ai   : {_titles(platform.browse_by_category('ai'))}")
    print(f"  city=Bangalore: {_titles(platform.browse_by_city('Bangalore'))}")
    print(f"  community=GDG : {_titles(platform.browse_by_community('Google Developer Groups'))}")

    print("\n=== SEARCH (repository-backed, → DTOs) ===")
    results = await platform.search(SearchQuery(keywords=["ai"]))
    print(f"  'ai' → {len(results)} results: {_titles(results)}")

    print("\n=== EVENT DETAILS (first upcoming event) ===")
    events = [s async for s in repo.iterate(SearchCriteria(active_only=True))]
    upcoming = sorted(events, key=lambda s: s.event.start_date)
    detail = platform.event_details(upcoming[0].key)
    if detail:
        print(f"  {detail.event.title[:50]}")
        print(f"    lifecycle={detail.lifecycle} trending={detail.trending_score}")
        if detail.ai:
            print(f"    topics={detail.ai.topics} tech={detail.ai.technologies} diff={detail.ai.difficulty}")
        print(f"    organizer={detail.organizer.name if detail.organizer else None}"
              f" community={detail.community.name if detail.community else None}"
              f" city={detail.city.name if detail.city else None}")
        print(f"    similar: {_titles(detail.similar)}")

    print("\n=== ENTITY PROFILES ===")
    for name, fn in [("GDG", platform.community_profile), ("Google", platform.organizer_profile)]:
        p = fn("Google Developer Groups" if name == "GDG" else name)
        if p:
            print(f"  {p.entity_type}: {p.name} total={p.total_events} active={p.active_events} extra={p.extra}")

    print("\n=== RECOMMENDATIONS (simulated user: attends 2 AI events) ===")
    now = datetime.now(UTC)
    ai_events = [s for s in events if s.event.category.value == "ai"][:2]
    for s in ai_events:
        platform.record_interaction(Interaction("u1", InteractionType.ATTEND, now, event_key=s.key))
    for rec in platform.recommendations("u1", limit=4):
        print(f"  [{rec.score:.3f}] {rec.event.title[:40]}")
        for reason in rec.reasons:
            print(f"           - {reason}")

    print("\n=== ANALYTICS ===")
    a = platform.analytics()
    print(f"  events={a.total_events} cities={a.cities} communities={a.communities}"
          f" organizers={a.organizers} providers={a.providers} topics={a.topics} tech={a.technologies}")
    print(f"  top topics       : {a.top_topics}")
    print(f"  top technologies : {a.top_technologies}")
    print(f"  top communities  : {a.top_communities}")

    await repo.close()
    await state.close()


if __name__ == "__main__":
    asyncio.run(main())
