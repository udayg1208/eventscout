"""M9 live check: GDGProvider + 3-provider composite (not a test)."""

from __future__ import annotations

import asyncio
import collections
import logging

logging.basicConfig(level=logging.INFO, format="LOG | %(name)s | %(message)s", force=True)

from app.models.search import SearchQuery  # noqa: E402
from app.providers.composite import CompositeProvider  # noqa: E402
from app.providers.confstech import ConfsTechProvider  # noqa: E402
from app.providers.devfolio import DevfolioProvider  # noqa: E402
from app.providers.gdg import GDGProvider  # noqa: E402


async def main() -> None:
    gdg = await GDGProvider().search(SearchQuery())
    print(f"\nGDG upcoming India events: {len(gdg)}")
    for e in sorted(gdg, key=lambda x: x.start_date)[:8]:
        print(f"  [{e.start_date}] {e.title[:48]:48} | {e.city or '-'}")

    engine = CompositeProvider(
        [ConfsTechProvider(), DevfolioProvider(), GDGProvider()]
    )
    everything = await engine.search(SearchQuery())
    by_provider = collections.Counter(e.provider for e in everything)
    print(f"\n3-provider composite total: {len(everything)}")
    print(f"by provider: {dict(by_provider)}")


if __name__ == "__main__":
    asyncio.run(main())
