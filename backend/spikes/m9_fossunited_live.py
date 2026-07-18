"""M9 live check: FOSS United + full 5-provider composite (not a test)."""

from __future__ import annotations

import asyncio
import collections

from app.models.search import SearchQuery  # noqa: E402
from app.providers import get_provider  # noqa: E402
from app.providers.fossunited import FOSSUnitedProvider  # noqa: E402


async def main() -> None:
    foss = await FOSSUnitedProvider().search(SearchQuery())
    print(f"\nFOSS United upcoming events: {len(foss)}")
    cats = collections.Counter(e.category.value for e in foss)
    print(f"categories: {dict(cats)}")
    for e in sorted(foss, key=lambda x: x.start_date)[:6]:
        free = "free" if e.is_free else ("paid" if e.is_free is False else "?")
        print(f"  [{e.start_date}] {e.title[:42]:42} | {e.category.value:10} | {free} | {e.city or '-'}")

    everything = await get_provider().search(SearchQuery())
    by_provider = collections.Counter(e.provider for e in everything)
    by_category = collections.Counter(e.category.value for e in everything)
    print(f"\n5-provider composite total (deduped): {len(everything)}")
    print(f"by provider: {dict(by_provider)}")
    print(f"by category: {dict(by_category)}")


if __name__ == "__main__":
    asyncio.run(main())
