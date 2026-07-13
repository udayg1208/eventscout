"""M5 live check: real ConfsTechProvider through SearchService (not a test)."""

from __future__ import annotations

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="LOG | %(name)s | %(message)s", force=True)

from app.cache import TTLCache  # noqa: E402
from app.models.search import SearchQuery  # noqa: E402
from app.parsers.keyword import KeywordQueryParser  # noqa: E402
from app.providers.confstech import ConfsTechProvider  # noqa: E402
from app.services.search_service import SearchService  # noqa: E402


async def main() -> None:
    provider = ConfsTechProvider()
    all_india = await provider.search(SearchQuery())
    print(f"\nLive India conferences fetched: {len(all_india)}")
    for e in sorted(all_india, key=lambda x: x.start_date)[:8]:
        print(f"  [{e.start_date}] {e.title} — {e.location}")

    # Requirement 7: SearchService works unchanged with the real provider.
    service = SearchService(
        parser=KeywordQueryParser(),
        provider=provider,  # reuses the provider's warm cache
        parse_cache=TTLCache(300),
        results_cache=TTLCache(300),
    )
    outcome = await service.search("conferences in Bangalore")
    print(f"\nSearchService 'conferences in Bangalore' -> {len(outcome.events)} events")
    for e in outcome.events:
        print(f"  {e.title} — {e.city}")


if __name__ == "__main__":
    asyncio.run(main())
