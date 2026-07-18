"""Discovery Optimization Engine (Phase 8A) — the recommendations pipeline.

    Historical Discovery → Coverage → Gap Analysis → Query Optimization → Budget
                         → Domain Ranking → Strategy Recommendation → Analytics

Consumes historical `DiscoveryRecord`s (what discovery already did) and produces an
`OptimizationReport` of **recommendations only** — it makes no automatic changes to discovery,
onboarding, production, or the catalog. Deterministic; no LLM, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.discovery.optimization.analytics import DiscoveryAnalytics, build_analytics
from app.discovery.optimization.budget import BudgetPlan, allocate_budget
from app.discovery.optimization.coverage import CoverageReport, build_coverage
from app.discovery.optimization.domain_ranker import DomainTrustScore, rank_domains
from app.discovery.optimization.gap_analysis import Gap, find_gaps
from app.discovery.optimization.query_optimizer import QueryOptimization, optimize_queries
from app.discovery.optimization.store import DiscoveryRecord, OptimizationStore
from app.discovery.optimization.strategy import StrategyRecommendation, recommend_strategies


@dataclass
class OptimizationReport:
    coverage: CoverageReport
    gaps: list[Gap]
    queries: QueryOptimization
    budget: BudgetPlan
    domains: list[DomainTrustScore]
    strategies: list[StrategyRecommendation]
    analytics: DiscoveryAnalytics
    recommendations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "coverage": self.coverage.as_dict(),
            "gaps": [g.as_dict() for g in self.gaps],
            "queries": self.queries.as_dict(),
            "budget": self.budget.as_dict(),
            "domains": [d.as_dict() for d in self.domains],
            "strategies": [s.as_dict() for s in self.strategies],
            "analytics": self.analytics.as_dict(),
            "recommendations": list(self.recommendations),
        }


def _headline_recommendations(
    gaps: list[Gap], queries: QueryOptimization, budget: BudgetPlan, domains: list[DomainTrustScore]
) -> list[str]:
    recs: list[str] = []
    for g in gaps[:3]:
        recs.append(f"COVERAGE: {g.recommendation}")
    for q in queries.stats:
        if q.recommendation in ("retire", "boost", "split"):
            recs.append(f"QUERY[{q.recommendation}]: '{q.query}' — {q.reason}")
    for q in queries.zero_yield[:3]:
        recs.append(f"QUERY[retire]: '{q}' — found nothing")
    for pair in queries.merges[:3]:
        recs.append(f"QUERY[merge]: {pair[0]!r} + {pair[1]!r} (heavy overlap)")
    for nq in queries.new_queries[:3]:
        recs.append(f"QUERY[create]: '{nq}'")
    stops = [b.domain for b in budget.budgets if b.action == "stop"]
    if stops:
        recs.append(f"BUDGET: stop crawling {len(stops)} dead/blacklisted domain(s): {stops[:5]}")
    top = [d.domain for d in domains if d.tier == "high"][:5]
    if top:
        recs.append(f"BUDGET: increase crawl frequency for top domains: {top}")
    return recs


class OptimizationEngine:
    def __init__(self, store: OptimizationStore | None = None) -> None:
        self._store = store

    async def run(
        self,
        records: list[DiscoveryRecord],
        *,
        queries_run: list[str] | None = None,
        blacklist: set[str] | None = None,
        daily_crawls: int = 100,
    ) -> OptimizationReport:
        coverage = build_coverage(records)
        gaps = find_gaps(records)
        queries = optimize_queries(records, queries_run, gaps=gaps)
        domains = rank_domains(records)
        budget = allocate_budget(domains, blacklist=blacklist, daily_crawls=daily_crawls)
        strategies = recommend_strategies(records)
        analytics = build_analytics(
            records, coverage_pct=coverage.coverage_pct, queries_run=queries_run
        )
        report = OptimizationReport(
            coverage=coverage,
            gaps=gaps,
            queries=queries,
            budget=budget,
            domains=domains,
            strategies=strategies,
            analytics=analytics,
            recommendations=_headline_recommendations(gaps, queries, budget, domains),
        )
        if self._store is not None:
            await self._store.save_report(report.as_dict())
        return report
