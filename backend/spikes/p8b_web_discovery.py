"""Phase 8B live demonstration: real web discovery against ONE configured provider.

Section 1 (LIVE): runs the real DuckDuckGo provider (zero-key) over the actual internet — polite:
robots-checked, rate-limited, 24h-cached, budget-capped. Prints queries executed, cache hits on a
second run, new domains discovered, and the Discovery Inbox update. If the sandbox can't reach the
network (or DDG rate-limits/challenges), it says so honestly.

Section 2 (OFFLINE): runs the identical engine with a static fixture provider so the full pipeline
(cache → normalize → dedupe → score → inbox) is demonstrated deterministically regardless of
network. No provider is promoted; output stops at the Discovery Inbox. No browser, no LLM.
"""

from __future__ import annotations

import asyncio
import logging
import os

logging.disable(logging.CRITICAL)

from app.discovery import InMemoryDiscoveryInbox  # noqa: E402
from app.discovery.search import QuerySpec, SearchResult  # noqa: E402
from app.discovery.web import (  # noqa: E402
    BingWebSearchProvider,
    Budget,
    DuckDuckGoProvider,
    GoogleProgrammableSearchProvider,
    PoliteFetcher,
    RateLimiter,
    RobotsGate,
    SearchCache,
    SearchProviderConfig,
    SerpApiSearchProvider,
    WebDiscoveryEngine,
    WebSearchProvider,
)

SPEC = QuerySpec(
    cities=("Bangalore",),
    technologies=("Python", "AI"),
    platforms=("meetup.com",),
    community_sites=("gdg.community.dev",),
    event_types=(),
    universities=(),
    companies=(),
)


def _configured_provider(fetcher):
    """Pick the first provider with credentials in env; default to DuckDuckGo (no key)."""
    if os.getenv("GOOGLE_API_KEY") and os.getenv("GOOGLE_CX"):
        cfg = SearchProviderConfig(
            api_key=os.environ["GOOGLE_API_KEY"], engine_id=os.environ["GOOGLE_CX"]
        )
        return GoogleProgrammableSearchProvider(cfg, fetcher=fetcher)
    if os.getenv("BING_API_KEY"):
        return BingWebSearchProvider(
            SearchProviderConfig(api_key=os.environ["BING_API_KEY"]), fetcher=fetcher
        )
    if os.getenv("SERPAPI_KEY"):
        return SerpApiSearchProvider(
            SearchProviderConfig(api_key=os.environ["SERPAPI_KEY"]), fetcher=fetcher
        )
    return DuckDuckGoProvider(fetcher=fetcher, mode="html", robots=RobotsGate(fetcher))


class StaticProvider(WebSearchProvider):
    """Offline fixture provider — canned SERP results, no network."""

    name = "static"

    def __init__(self, results):
        self._results = results

    async def search(self, query, *, limit=10):
        return list(self._results.get(query, []))[:limit]


FIXTURE = {
    "site:meetup.com Bangalore Python": [
        SearchResult(
            "BangPypers — Bangalore Python User Group",
            "https://www.meetup.com/bangpypers/",
            "Monthly Python meetup in Bangalore, India.",
            1,
            "static",
        ),
        SearchResult(
            "PyData Bangalore",
            "https://www.meetup.com/pydata-bangalore/",
            "Data science and AI meetup, Bangalore.",
            2,
            "static",
        ),
    ],
    "site:meetup.com Bangalore AI": [
        SearchResult(
            "AI Bangalore Meetup",
            "https://www.meetup.com/ai-bangalore/",
            "Artificial Intelligence meetup Bangalore India",
            1,
            "static",
        ),
    ],
    "site:gdg.community.dev India": [
        SearchResult(
            "GDG Cloud Bangalore",
            "https://gdg.community.dev/gdg-cloud-bangalore/",
            "Google Developer Group AI & cloud events, Bangalore India.",
            1,
            "static",
        ),
    ],
}


async def live_section() -> None:
    print("=== SECTION 1 — LIVE (real internet, one configured provider) ===")
    fetcher = PoliteFetcher(timeout=10.0, max_retries=2, sleep=asyncio.sleep)
    provider = _configured_provider(fetcher)
    print(f"provider: {provider.name}  (set GOOGLE_API_KEY+GOOGLE_CX / BING_API_KEY / SERPAPI_KEY)")

    inbox = InMemoryDiscoveryInbox()
    cache = SearchCache()
    rate = RateLimiter(per_minute=12, sleep=asyncio.sleep)  # polite: ≥5s between calls
    engine = WebDiscoveryEngine(
        provider,
        inbox,
        cache=cache,
        rate_limiter=rate,
        budget=Budget(3),
        results_per_query=8,
    )
    try:
        r1 = await engine.run(SPEC)
        print(
            f"  queries_executed={r1.queries_executed}  results_collected={r1.results_collected}  "
            f"provider_errors={r1.provider_errors}"
        )
        print(f"  new domains discovered: {r1.new_domains or '(none)'}")
        print(f"  Discovery Inbox now: {await inbox.count()} candidate(s)")
        r2 = await engine.run(SPEC)  # second run → cache hits, no re-discovery
        print(
            f"  RUN 2 (cache): cache_hits={r2.cache_hits}  inserted={r2.inserted}  "
            f"skipped_known={r2.skipped_known}  cache_hit_rate={cache.stats.hit_rate}"
        )
        if r1.provider_errors and not r1.new_domains:
            print("  NOTE: live provider returned no usable results (blocked or rate-limited).")
    except Exception as exc:  # noqa: BLE001 — spike must stay honest on any network failure
        print(f"  LIVE CALL FAILED: {type(exc).__name__}: {exc}")
        print("  (network unavailable in this environment — see the offline pipeline below)")


async def offline_section() -> None:
    print("\n=== SECTION 2 — OFFLINE PIPELINE (static fixture, deterministic) ===")
    inbox = InMemoryDiscoveryInbox()
    cache = SearchCache()
    engine = WebDiscoveryEngine(StaticProvider(FIXTURE), inbox, cache=cache, budget=Budget(20))
    r1 = await engine.run(SPEC)
    print(
        f"  queries_executed={r1.queries_executed}  results_collected={r1.results_collected}  "
        f"unique={r1.unique_results}"
    )
    print(
        f"  inserted={r1.inserted}  below_threshold={r1.below_threshold}  "
        f"new domains: {r1.new_domains}"
    )
    print(f"  Discovery Inbox: {await inbox.count()} candidates (discovered_by=search, status=NEW)")
    for c in await inbox.list(limit=10):
        title = (c.title or "")[:34]
        print(f"    [{c.feed_type.value}] {c.domain:16s} engine={c.search_engine} :: {title}")
    r2 = await engine.run(SPEC)
    print(
        f"  RUN 2 (cache): cache_hits={r2.cache_hits}  inserted={r2.inserted}  "
        f"skipped_known={r2.skipped_known}  hit_rate={cache.stats.hit_rate}"
    )
    print("\n  ✔ stops at the Discovery Inbox — no onboarding, no promotion, no catalog write")


async def main() -> None:
    print("=== Phase 8B — Real Web Discovery Engine (polite: robots + rate-limit + cache) ===\n")
    await live_section()
    await offline_section()


if __name__ == "__main__":
    asyncio.run(main())
