"""M6 live check: the real multi-provider engine (not a test)."""

from __future__ import annotations

import asyncio
import logging

logging.basicConfig(level=logging.WARNING, format="LOG | %(name)s | %(message)s", force=True)

from app.models.search import SearchQuery  # noqa: E402
from app.providers import get_provider  # noqa: E402
from app.providers.confstech import ConfsTechProvider  # noqa: E402
from app.providers.devfolio import DevfolioProvider  # noqa: E402
from app.providers.composite import CompositeProvider  # noqa: E402


def show(title: str, events) -> None:
    print(f"\n=== {title}: {len(events)} events ===")
    for e in events[:10]:
        print(f"  [{e.start_date}] {e.title[:44]:44} | {e.provider:9} | "
              f"{e.category.value:10} | {e.city or ('online' if e.is_online else '-')}")


async def main() -> None:
    engine = CompositeProvider([ConfsTechProvider(), DevfolioProvider()])

    show("All India events (merged, ranked)", await engine.search(SearchQuery()))

    from app.models.event import EventCategory
    show("Hackathons only", await engine.search(
        SearchQuery(categories=[EventCategory.HACKATHON])))
    show("Bangalore (alias-normalized)", await engine.search(SearchQuery(city="Bangalore")))

    # count events by provider to confirm both sources contributed
    everything = await engine.search(SearchQuery())
    by_provider: dict[str, int] = {}
    for e in everything:
        by_provider[e.provider] = by_provider.get(e.provider, 0) + 1
    print(f"\nProvider contribution: {by_provider}")


if __name__ == "__main__":
    asyncio.run(main())
