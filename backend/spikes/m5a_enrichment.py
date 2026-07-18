"""Phase 5A live check (not a test): enrich the real catalog and show coverage + similarity."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
import tempfile

logging.disable(logging.CRITICAL)

from app.enrichment import EnrichmentPipeline  # noqa: E402
from app.ingestion.registry import build_registry  # noqa: E402
from app.scheduler import IngestionEngine  # noqa: E402
from app.storage.models import SearchCriteria  # noqa: E402
from app.storage.sqlite_provider_state import SQLiteProviderStateStore  # noqa: E402
from app.storage.sqlite_repository import SQLiteEventRepository  # noqa: E402


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="m5a_"))
    repo = SQLiteEventRepository(str(tmp / "events.db"))
    state = SQLiteProviderStateStore(str(tmp / "state.db"))
    engine = IngestionEngine(build_registry(), repo, state, clock=lambda: datetime.now(UTC), concurrency=4)
    await engine.run_cycle()
    await engine.shutdown()
    total = await repo.count(SearchCriteria())
    print(f"catalog: {total} events")

    pipeline = EnrichmentPipeline()
    enriched = await pipeline.run(repo)
    all_enr = pipeline.store.all()
    print(f"enriched: {enriched}")

    topics = Counter(t for e in all_enr.values() for t in e.topics)
    techs = Counter(t for e in all_enr.values() for t in e.technologies)
    careers = Counter(c for e in all_enr.values() for c in e.careers)
    difficulty = Counter(e.difficulty.value for e in all_enr.values())
    with_topics = sum(1 for e in all_enr.values() if e.topics)

    print(f"events with >=1 topic: {with_topics}/{total}")
    print(f"top topics: {topics.most_common(8)}")
    print(f"top technologies: {techs.most_common(8)}")
    print(f"top careers: {careers.most_common(6)}")
    print(f"difficulty: {dict(difficulty)}")

    # a sample enrichment + its most similar events
    sample_key = next((k for k, e in all_enr.items() if len(e.topics) >= 2), next(iter(all_enr)))
    sample = all_enr[sample_key]
    print("\nsample enrichment:")
    print(f"  summary: {sample.summary}")
    print(f"  topics={sample.topics} tech={sample.technologies} careers={sample.careers}")
    print("  most similar:")
    for k, score in pipeline.similarity().similar_to(sample_key, limit=3):
        s = pipeline.store.get(k)
        print(f"    {score:.3f}  topics={s.topics}")

    await repo.close()
    await state.close()


if __name__ == "__main__":
    asyncio.run(main())
