"""Discovery Analytics (Phase 8A) — efficiency and yield metrics over historical discovery.

Read-only aggregation: query yield, domain yield, source growth, crawl efficiency, discovery
precision, cost per discovery, coverage %, and discovery velocity. Deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.discovery.optimization.store import DiscoveryRecord


@dataclass
class DiscoveryAnalytics:
    total_records: int = 0
    distinct_domains: int = 0
    distinct_queries: int = 0
    query_yield: float = 0.0  # good domains per query
    domain_yield: float = 0.0  # events per domain
    source_growth: int = 0  # distinct domains discovered
    crawl_efficiency: float = 0.0  # events per crawl attempt
    discovery_precision: float = 0.0  # discovered → active (production)
    cost_per_discovery: float = 0.0  # crawl attempts per distinct domain
    discovery_velocity: int = 0  # records (per run window)
    coverage_pct: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def build_analytics(
    records: list[DiscoveryRecord],
    *,
    coverage_pct: dict | None = None,
    queries_run: list[str] | None = None,
) -> DiscoveryAnalytics:
    if not records:
        return DiscoveryAnalytics(coverage_pct=coverage_pct or {})

    domains = {r.domain for r in records}
    queries = {r.search_query for r in records if r.search_query}
    query_count = len(set(queries_run or [])) or len(queries)
    good = sum(1 for r in records if r.approved or r.active)
    events = sum(r.event_count for r in records)
    attempts = sum(r.crawl_attempts for r in records)
    reached_prod = [r for r in records if r.production_state in ("active", "rolled_back")]
    active = sum(1 for r in records if r.active)

    return DiscoveryAnalytics(
        total_records=len(records),
        distinct_domains=len(domains),
        distinct_queries=len(queries),
        query_yield=round(good / query_count, 4) if query_count else 0.0,
        domain_yield=round(events / len(domains), 4) if domains else 0.0,
        source_growth=len(domains),
        crawl_efficiency=round(events / attempts, 4) if attempts else 0.0,
        discovery_precision=round(active / len(reached_prod), 4) if reached_prod else 0.0,
        cost_per_discovery=round(attempts / len(domains), 4) if domains else 0.0,
        discovery_velocity=len(records),
        coverage_pct=coverage_pct or {},
    )
