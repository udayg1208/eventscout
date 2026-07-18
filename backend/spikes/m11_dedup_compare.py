"""Dedup old-vs-new comparison on the live merged dataset (not a test)."""

from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict

logging.disable(logging.CRITICAL)

from analytics.provider_analytics import WORKING, collect  # noqa: E402
from app.city import normalize_city  # noqa: E402
from app.providers.dedup import deduplicate, event_similarity  # noqa: E402
from app.providers.ranking import completeness  # noqa: E402

_PUNCT = re.compile(r"[^a-z0-9]+")


def _refine_city(e):
    c = normalize_city(e.city)
    return e if c == e.city else e.model_copy(update={"city": c})


def old_dedup(events):
    """Pre-Phase-2 dedup: exact (normalized_title, start_date), keep most complete."""
    best: dict[tuple, object] = {}
    for e in events:
        key = (_PUNCT.sub(" ", e.title.casefold()).strip(), e.start_date)
        if key not in best or completeness(e) > completeness(best[key]):
            best[key] = e
    return list(best.values())


async def main() -> None:
    samples = await collect(WORKING)
    merged = [_refine_city(e) for s in samples for e in s.events]
    old = old_dedup(merged)
    new = deduplicate(merged)
    print(f"merged (pre-dedup):   {len(merged)}")
    print(f"OLD dedup survivors:  {len(old)}   (removed {len(merged) - len(old)})")
    print(f"NEW dedup survivors:  {len(new)}   (removed {len(merged) - len(new)})")

    print("\ncross-provider duplicates the NEW engine catches:")
    blocks = defaultdict(list)
    for e in merged:
        blocks[e.start_date].append(e)
    shown = 0
    for d, g in blocks.items():
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                s = event_similarity(g[i], g[j])
                if s >= 0.85 and g[i].provider != g[j].provider and shown < 8:
                    print(
                        f"  sim={s:.2f} [{d}] [{g[i].provider}] {g[i].title[:30]!r} "
                        f"~ [{g[j].provider}] {g[j].title[:30]!r}"
                    )
                    shown += 1
    if shown == 0:
        print("  (none this run — sources currently overlap little)")


if __name__ == "__main__":
    asyncio.run(main())
