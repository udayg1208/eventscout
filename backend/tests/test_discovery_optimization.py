"""Phase 8A — Discovery Optimization tests. Deterministic, no network."""

from __future__ import annotations

import asyncio

from app.discovery.optimization import (
    DiscoveryRecord,
    InMemoryOptimizationStore,
    OptimizationEngine,
    allocate_budget,
    build_analytics,
    build_coverage,
    find_gaps,
    optimize_queries,
    rank_domains,
    recommend_strategies,
    score_domain,
)
from app.discovery.optimization.domain_ranker import WEIGHTS


def run(coro):
    return asyncio.run(coro)


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


def sample() -> list[DiscoveryRecord]:
    return [
        rec(
            "gdg.dev",
            "rss",
            city="Bangalore",
            state="Karnataka",
            techs=["Artificial Intelligence"],
            comm="GDG",
            org="GDG",
            onb="promoted",
            sq=0.9,
            prod="active",
            ec=60,
            fresh=5,
            att=10,
            q="site:meetup.com Bangalore AI",
        ),
        rec(
            "pydata.org",
            "jsonld_event",
            city="Bangalore",
            techs=["Artificial Intelligence", "Python"],
            org="PyData",
            onb="promoted",
            sq=0.8,
            prod="active",
            ec=60,
            fresh=10,
            att=8,
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
            fresh=48,
            by="search",
            q="Rust meetup Bangalore",
        ),
        rec(
            "spam1.com",
            "search_result",
            onb="rejected",
            by="search",
            q="events near me",
            ec=0,
            att=3,
        ),
        rec(
            "spam2.com",
            "search_result",
            onb="rejected",
            by="search",
            q="events near me",
            ec=0,
            att=3,
        ),
        rec("deadfeed.net", "rss", onb="failed_sandbox", ec=0, att=6, fail=5, dup=0.9),
        rec(
            "luma.co",
            "next_data",
            city="Delhi",
            state="Delhi",
            techs=["React"],
            onb="promoted",
            sq=0.7,
            prod="active",
            ec=14,
            fresh=8,
            att=5,
        ),
        rec(
            "blog.io",
            "ai_extracted",
            city="Pune",
            techs=["DevOps"],
            onb="promoted",
            sq=0.6,
            prod="rolled_back",
            ec=3,
            fresh=20,
            by="ai",
            q="DevOps workshop Pune",
        ),
    ]


# --------------------------- coverage ---------------------------


def test_coverage_covered_and_uncovered():
    cov = build_coverage(sample())
    assert "Bangalore" in cov.covered_cities and "Delhi" in cov.covered_cities
    assert "Chennai" in cov.uncovered_cities  # never discovered
    assert "GDG" in cov.covered_communities
    assert cov.distinct_organizers >= 2
    assert 0 < cov.coverage_pct["cities"] < 1


# --------------------------- gap analysis ---------------------------


def test_gap_analysis_flags_thin_tech_in_covered_city():
    gaps = find_gaps(sample())
    blr = [g for g in gaps if g.scope == "city:Bangalore"]
    assert blr  # Bangalore has volume but thin coverage of most techs
    # Rust is present-but-thin (2 events) → flagged as a Bangalore gap
    rust = [g for g in blr if g.technology == "Rust"]
    assert rust and "expand Rust search in Bangalore" in rust[0].recommendation
    # observed-only: a city with no records yields no city gaps
    assert not any(g.scope == "city:Chennai" for g in gaps)


# --------------------------- query optimizer ---------------------------


def test_query_optimizer_boost_retire_zero_and_new():
    gaps = find_gaps(sample())
    opt = optimize_queries(
        sample(),
        queries_run=[
            "site:meetup.com Bangalore AI",
            "events near me",
            "Rust meetup Bangalore",
            "DevOps workshop Pune",
            "unused query",
        ],
        gaps=gaps,
    )
    by_q = {s.query: s for s in opt.stats}
    assert by_q["site:meetup.com Bangalore AI"].recommendation == "boost"
    assert by_q["events near me"].recommendation == "retire"  # spam_rate 1.0
    assert "unused query" in opt.zero_yield  # executed, found nothing
    assert opt.new_queries  # created from gaps


def test_query_optimizer_merges_overlapping_queries():
    recs = [
        rec("a.com", "rss", q="query one", onb="promoted", ec=5),
        rec("b.com", "rss", q="query one", onb="promoted", ec=5),
        rec("a.com", "rss", q="query two", onb="promoted", ec=5),
        rec("b.com", "rss", q="query two", onb="promoted", ec=5),
    ]
    opt = optimize_queries(recs)
    assert ["query one", "query two"] in opt.merges  # identical domain sets → merge


# --------------------------- domain ranker ---------------------------


def test_domain_ranker_scores_and_tiers():
    scores = {s.domain: s for s in rank_domains(sample())}
    assert scores["gdg.dev"].tier == "high" and scores["gdg.dev"].total >= 0.7
    assert scores["deadfeed.net"].tier in ("dead", "low")
    # total is exactly the weighted sum of its factors (explainable, no hidden numbers)
    s = scores["gdg.dev"]
    assert abs(s.total - sum(WEIGHTS[k] * v for k, v in s.factors.items())) < 1e-6


def test_score_domain_rolled_back_lowers_production():
    good = score_domain("x", [rec("x", "rss", prod="active", onb="promoted", sq=0.8, ec=10)])
    bad = score_domain("y", [rec("y", "rss", prod="rolled_back", onb="promoted", sq=0.8, ec=10)])
    assert good.factors["production_success"] == 1.0 and bad.factors["production_success"] == 0.0
    assert good.total > bad.total


# --------------------------- budget ---------------------------


def test_budget_increase_stop_and_weights():
    scores = rank_domains(sample())
    plan = allocate_budget(scores, blacklist={"spam2.com"}, daily_crawls=100)
    by_d = {b.domain: b for b in plan.budgets}
    assert by_d["gdg.dev"].action == "increase" and by_d["gdg.dev"].interval_hours == 6
    assert by_d["spam2.com"].action == "stop" and by_d["spam2.com"].interval_hours is None
    assert by_d["deadfeed.net"].action == "stop"  # dead domain
    # weights of crawlable domains sum to ~1
    total_w = sum(b.weight for b in plan.budgets if b.action != "stop")
    assert abs(total_w - 1.0) < 1e-3


# --------------------------- strategy ---------------------------


def test_strategy_rss_avoids_ai_and_spa_uses_framework():
    strat = {s.domain: s for s in recommend_strategies(sample())}
    assert strat["gdg.dev"].best_strategy == "structured"
    assert "ai" in strat["gdg.dev"].avoid  # never run AI on an RSS domain
    assert strat["luma.co"].best_strategy == "framework"
    assert strat["blog.io"].best_strategy == "ai"


# --------------------------- analytics ---------------------------


def test_analytics_precision_and_efficiency():
    a = build_analytics(sample(), queries_run=["a", "b", "c"])
    assert a.total_records == 8 and a.distinct_domains == 8
    # 3 active (gdg, pydata, luma) of 4 that reached production (+ blog rolled_back)
    assert a.discovery_precision == round(3 / 4, 4)
    assert a.crawl_efficiency > 0 and a.cost_per_discovery > 0


# --------------------------- engine (end-to-end) ---------------------------


def test_engine_produces_full_report_and_persists():
    store = InMemoryOptimizationStore()
    report = run(
        OptimizationEngine(store).run(
            sample(),
            queries_run=["site:meetup.com Bangalore AI", "events near me", "unused query"],
            blacklist={"spam2.com"},
            daily_crawls=100,
        )
    )
    assert report.coverage.coverage_pct["cities"] > 0
    assert report.gaps and report.domains and report.strategies
    assert report.recommendations  # headline recommendations produced
    assert any(r.startswith("QUERY[retire]") for r in report.recommendations)
    assert any(r.startswith("COVERAGE") for r in report.recommendations)
    # persisted (recommendations only — no discovery/catalog change)
    assert run(store.latest()) is not None
    assert len(run(store.history())) == 1
