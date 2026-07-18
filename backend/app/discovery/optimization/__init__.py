"""Autonomous Discovery Optimization (Phase 8A) — recommendations that improve discovery.

Consumes historical discovery outcomes (what got discovered, onboarded, and how it performed in
production) and produces recommendations to make the discovery engine better: coverage gaps, query
retire/boost/split/merge/create, per-domain trust scores, crawl-budget allocation, and best-strategy
picks per source. It **never touches the catalog** and makes **no automatic changes** — output is
recommendations only.

Strictly additive: no LLM, no Google API, no changes to the Discovery Engine, Onboarding,
Production, Search, Repository, Scheduler, providers, frontend, or API.
"""

from app.discovery.optimization.analytics import DiscoveryAnalytics, build_analytics
from app.discovery.optimization.budget import BudgetPlan, CrawlBudget, allocate_budget
from app.discovery.optimization.coverage import CoverageReport, build_coverage
from app.discovery.optimization.domain_ranker import (
    DomainTrustScore,
    rank_domains,
    score_domain,
)
from app.discovery.optimization.engine import OptimizationEngine, OptimizationReport
from app.discovery.optimization.gap_analysis import Gap, find_gaps
from app.discovery.optimization.query_optimizer import (
    QueryOptimization,
    QueryStat,
    optimize_queries,
    suggest_new_queries,
)
from app.discovery.optimization.store import (
    DiscoveryRecord,
    InMemoryOptimizationStore,
    OptimizationStore,
    SQLiteOptimizationStore,
)
from app.discovery.optimization.strategy import StrategyRecommendation, recommend_strategies

__all__ = [
    "DiscoveryRecord",
    "OptimizationEngine",
    "OptimizationReport",
    # coverage / gaps
    "build_coverage",
    "CoverageReport",
    "find_gaps",
    "Gap",
    # queries
    "optimize_queries",
    "QueryOptimization",
    "QueryStat",
    "suggest_new_queries",
    # domains / budget
    "rank_domains",
    "score_domain",
    "DomainTrustScore",
    "allocate_budget",
    "BudgetPlan",
    "CrawlBudget",
    # strategy / analytics
    "recommend_strategies",
    "StrategyRecommendation",
    "build_analytics",
    "DiscoveryAnalytics",
    # store
    "OptimizationStore",
    "InMemoryOptimizationStore",
    "SQLiteOptimizationStore",
]
