"""Phase 8A live demonstration (not a test): autonomous discovery optimization, deterministic.

Feeds a body of historical discovery outcomes (what got discovered, how it onboarded, how it did in
production) through the optimization pipeline and prints recommendations: coverage report, query
improvements, crawl-budget allocation, top domains, and headline discovery recommendations. It
changes NOTHING — recommendations only. No network, no LLM, no Google API.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

logging.disable(logging.CRITICAL)

from app.discovery.optimization import (  # noqa: E402
    DiscoveryRecord,
    OptimizationEngine,
    SQLiteOptimizationStore,
)


def rec(dom, ft, **kw) -> DiscoveryRecord:
    return DiscoveryRecord(
        url="https://" + dom,
        domain=dom,
        feed_type=ft,
        discovered_by=kw.get("by", "crawl"),
        search_query=kw.get("q"),
        city=kw.get("city"),
        state=kw.get("state"),
        technologies=kw.get("techs", []),
        organization=kw.get("org"),
        community=kw.get("comm"),
        university=kw.get("uni"),
        onboarding_state=kw.get("onb"),
        sandbox_quality=kw.get("sq", 0.0),
        production_state=kw.get("prod"),
        duplicate_rate=kw.get("dup", 0.0),
        event_count=kw.get("ec", 0),
        freshness_hours=kw.get("fresh"),
        crawl_attempts=kw.get("att", 1),
        crawl_failures=kw.get("fail", 0),
    )


RECORDS = [
    # Bangalore: rich in AI, thin elsewhere
    rec(
        "gdg.community.dev",
        "rss",
        city="Bangalore",
        state="Karnataka",
        techs=["Artificial Intelligence"],
        comm="GDG",
        org="GDG",
        onb="promoted",
        sq=0.9,
        prod="active",
        ec=70,
        fresh=5,
        att=12,
        q="site:meetup.com Bangalore AI",
    ),
    rec(
        "pydata.org",
        "jsonld_event",
        city="Bangalore",
        techs=["Artificial Intelligence", "Python"],
        org="PyData",
        comm="PyData",
        onb="promoted",
        sq=0.85,
        prod="active",
        ec=55,
        fresh=10,
        att=9,
        q="site:meetup.com Bangalore AI",
    ),
    rec(
        "rustblr.io",
        "search_result",
        city="Bangalore",
        techs=["Rust"],
        onb="manual_review",
        sq=0.4,
        ec=2,
        fresh=60,
        by="search",
        q="Rust meetup Bangalore",
    ),
    # Delhi framework source
    rec(
        "lu.ma",
        "next_data",
        city="Delhi",
        state="Delhi",
        techs=["React", "Kubernetes"],
        comm="GDG",
        onb="promoted",
        sq=0.7,
        prod="active",
        ec=18,
        fresh=8,
        att=6,
        q="site:lu.ma Delhi",
    ),
    # Pune AI-extracted, rolled back in prod
    rec(
        "blog.pydelhi.org",
        "ai_extracted",
        city="Pune",
        techs=["DevOps"],
        comm="PyDelhi",
        onb="promoted",
        sq=0.6,
        prod="rolled_back",
        ec=3,
        fresh=20,
        by="ai",
        q="DevOps meetup Pune",
    ),
    # Hyderabad conference
    rec(
        "hasgeek.com",
        "jsonld_event",
        city="Hyderabad",
        state="Telangana",
        techs=["Python", "DevOps"],
        org="Hasgeek",
        comm="Hasgeek",
        onb="promoted",
        sq=0.8,
        prod="active",
        ec=12,
        fresh=15,
        att=7,
    ),
    # a spammy query producing rejects
    rec(
        "spamA.net",
        "search_result",
        onb="rejected",
        by="search",
        q="free events near me",
        ec=0,
        att=4,
    ),
    rec(
        "spamB.net",
        "search_result",
        onb="rejected",
        by="search",
        q="free events near me",
        ec=0,
        att=4,
    ),
    # a dead feed (parser failures, all duplicates)
    rec("deadfeed.org", "rss", onb="failed_sandbox", ec=0, att=8, fail=7, dup=0.95),
    # near-duplicate queries hitting the same domains
    rec(
        "commA.dev",
        "rss",
        q="tech meetup india",
        onb="promoted",
        ec=8,
        prod="active",
        sq=0.7,
        fresh=12,
    ),
    rec(
        "commA.dev",
        "rss",
        q="developer meetup india",
        onb="promoted",
        ec=8,
        prod="active",
        sq=0.7,
        fresh=12,
    ),
]

QUERIES_RUN = [
    "site:meetup.com Bangalore AI",
    "Rust meetup Bangalore",
    "site:lu.ma Delhi",
    "DevOps meetup Pune",
    "free events near me",
    "tech meetup india",
    "developer meetup india",
    "site:meetup.com Chennai Go",
    "blockchain summit Kolkata",  # zero-yield
]


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="p8a_"))
    store = SQLiteOptimizationStore(str(tmp / "optimization.db"))
    engine = OptimizationEngine(store)

    print("=== Phase 8A — Autonomous Discovery Optimization (recommendations only) ===\n")
    print(f"Historical discoveries: {len(RECORDS)} records · queries run: {len(QUERIES_RUN)}\n")
    print("PIPELINE  History → Coverage → Gaps → Queries → Budget → Rank → Strategy → Analytics\n")

    r = await engine.run(
        RECORDS, queries_run=QUERIES_RUN, blacklist={"spamB.net"}, daily_crawls=100
    )

    print("=== COVERAGE ===")
    for dim, pct in r.coverage.coverage_pct.items():
        print(f"  {dim:14s} {pct * 100:5.1f}%")
    print(f"  uncovered cities: {r.coverage.uncovered_cities[:6]} …")
    print(f"  uncovered communities: {r.coverage.uncovered_communities[:6]} …")

    print("\n=== GAP ANALYSIS (observed-only) ===")
    for g in r.gaps[:6]:
        print(f"  [sev {g.severity:.2f}] {g.recommendation}")

    print("\n=== QUERY OPTIMIZATION ===")
    for q in r.queries.stats:
        print(
            f"  [{q.recommendation:6s}] {q.query!r:42s} "
            f"yield={q.yield_score:.2f} spam={q.spam_rate:.2f}"
        )
    print(f"  retire (zero-yield): {r.queries.zero_yield}")
    print(f"  merge (overlap): {r.queries.merges}")
    print(f"  create (from gaps): {r.queries.new_queries[:4]}")

    print("\n=== DOMAIN TRUST (top) ===")
    for d in r.domains[:6]:
        print(f"  {d.domain:22s} {d.tier:6s} {d.total:.3f}  ({d.records} rec)")

    print("\n=== CRAWL BUDGET (100 crawls/day) ===")
    for b in r.budget.budgets:
        iv = f"{b.interval_hours}h" if b.interval_hours else "—"
        crawls = r.budget.allocated.get(b.domain, 0)
        print(f"  {b.domain:22s} {b.action:9s} every {iv:4s}  ~{crawls}/day  ({b.reason})")

    print("\n=== BEST DISCOVERY STRATEGY ===")
    for s in r.strategies:
        print(f"  {s.domain:22s} → {s.best_strategy:11s} avoid={s.avoid}")

    print("\n=== DISCOVERY ANALYTICS ===")
    a = r.analytics
    print(f"  query_yield={a.query_yield}  domain_yield={a.domain_yield}  growth={a.source_growth}")
    print(
        f"  crawl_efficiency={a.crawl_efficiency} ev/attempt  "
        f"discovery_precision={a.discovery_precision}"
    )
    print(
        f"  cost_per_discovery={a.cost_per_discovery} attempts/domain  "
        f"velocity={a.discovery_velocity}"
    )

    print("\n=== HEADLINE RECOMMENDATIONS ===")
    for x in r.recommendations:
        print(f"  · {x}")

    print("\n  ✔ recommendations only — no discovery/onboarding/production/catalog change")
    await store.close()


if __name__ == "__main__":
    asyncio.run(main())
