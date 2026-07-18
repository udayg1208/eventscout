"""Phase 10A live demonstration: REAL discovery execution against the live internet.

Runs the real pipeline over a small slice of the production seed list: a real HTTP fetcher, the
real search provider (DuckDuckGo by default — set GOOGLE_API_KEY+GOOGLE_CX / BING_API_KEY /
SERPAPI_KEY to use a keyed one), real robots handling, the real Expansion crawler, and the real
Social + Rendered extractors — all driven through the 9A orchestrator into a `VerifyingInbox`.
Prints the stages executed, the discovered candidates, and the daily metrics.

Unlike the tests, this DOES touch the network (politely: robots respected, rate-limited, a small
page budget). Discovery only — nothing is onboarded, the catalog is never touched. No browser.

Run:  cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe spikes/p10a_real_execution.py
"""

from __future__ import annotations

import asyncio
import logging
import sys

logging.disable(logging.CRITICAL)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.discovery.search import QuerySpec  # noqa: E402
from app.execution import (  # noqa: E402
    ProductionSeedList,
    RealDiscoveryPipeline,
    active_provider_name,
)
from app.execution.seeds import PRODUCTION_SEEDS  # noqa: E402

# a small, polite subset of the production seeds (public, event-bearing, robots-friendly)
_SPIKE_URLS = [
    "https://www.python.org/events/",
    "https://confs.tech/",
    "https://fossunited.org/",
    "https://hasgeek.com/",
    "https://www.cncf.io/events/",
]
# a tiny query spec so the keyless provider isn't hammered with the full cross-product
_SPEC = QuerySpec(
    cities=("Bangalore",),
    technologies=("Python",),
    platforms=(),
    community_sites=(),
    event_types=("conference",),
    universities=(),
    companies=(),
)


async def main() -> None:
    print("=== Phase 10A — Real Discovery Execution (LIVE internet, public content only) ===")
    print(f"provider: {active_provider_name()}   (set GOOGLE/BING/SERPAPI keys to change)")
    seeds = ProductionSeedList(
        version="spike", seeds=tuple(s for s in PRODUCTION_SEEDS if s.url in _SPIKE_URLS)
    )
    print(f"seed list: {len(_SPIKE_URLS)} polite seeds from production v{seeds.version}\n")

    pipe = RealDiscoveryPipeline(seeds=seeds, spec=_SPEC, max_pages=8, respect_robots=True)
    print("--- running one real discovery cycle (robots-respected, rate-limited) ---")
    try:
        report = await pipe.run_cycle(max_cycles=25, seed_urls=_SPIKE_URLS)
    except Exception as exc:  # network may be unavailable in a sandbox — report honestly
        print(f"\n[!] real fetch failed ({type(exc).__name__}: {exc}).")
        print("    This spike requires outbound internet; the integration tests cover the pipeline")
        print("    hermetically. Nothing else in the phase depends on network access.")
        return

    print("\nstages executed:", report.orchestrator.stages_run)
    print(f"\n=== DISCOVERY INBOX ({report.inbox_total} candidates, all status=NEW) ===")
    for c in await pipe.inbox.list(limit=40):
        conf = f"{c.discovery_confidence:.2f}" if c.discovery_confidence is not None else " -  "
        print(
            f"  [{(c.discovered_by or '-'):9s}] {c.feed_type.value:12s} conf={conf}  {c.url[:70]}"
        )

    m = report.metrics
    print("\n=== DAILY METRICS ===")
    print(f"  pages crawled       : {m.pages_crawled}")
    print(f"  pages skipped        : {m.pages_skipped}  (robots / non-HTML / errors)")
    print(f"  new domains          : {m.new_domains}")
    print(f"  new sources          : {m.new_sources}")
    print(f"  new inbox candidates : {m.new_inbox_candidates}")
    print(f"  accepted / rejected  : {m.accepted} / {m.rejected}")
    print(f"  duplicate rate       : {m.duplicate_rate:.2%}")
    print(f"  crawl cost           : {m.crawl_cost_bytes:,} bytes")
    print(f"  discovery precision  : {m.discovery_precision:.2%}  (accepted / judged, at the gate)")
    if pipe.metrics.reject_reasons():
        print(f"  reject reasons       : {pipe.metrics.reject_reasons()}")

    print("\n  ✔ real public web → verified candidates → Discovery Inbox; nothing onboarded")


if __name__ == "__main__":
    asyncio.run(main())
