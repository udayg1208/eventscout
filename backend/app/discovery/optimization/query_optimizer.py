"""Query Optimizer (Phase 8A) — learn which search queries are worth running.

Analyzes historical discovery grouped by search query: which produced good domains (approved/
active), which produced spam (rejected), which produced duplicates, which found nothing. Scores
each deterministically (no LLM) and recommends retire / boost / split / merge, plus create-new
queries derived from coverage gaps. Recommendations only — the discovery engine is untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.discovery.optimization.gap_analysis import Gap
from app.discovery.optimization.store import DiscoveryRecord

_SPAM_RATE_RETIRE = 0.5
_BOOST_YIELD = 0.5
_SPLIT_DOMAINS = 8
_SPLIT_YIELD = 0.4
_MERGE_JACCARD = 0.6


@dataclass
class QueryStat:
    query: str
    domains: int
    good: int  # approved / active
    spam: int  # rejected
    duplicates: int
    yield_score: float
    spam_rate: float
    recommendation: str  # retire / boost / split / keep
    reason: str

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class QueryOptimization:
    stats: list[QueryStat] = field(default_factory=list)
    zero_yield: list[str] = field(default_factory=list)  # queries that found nothing → retire
    merges: list[list[str]] = field(default_factory=list)  # near-duplicate query pairs → merge
    new_queries: list[str] = field(default_factory=list)  # create-new (from gaps)

    def as_dict(self) -> dict:
        return {
            "stats": [s.as_dict() for s in self.stats],
            "zero_yield": self.zero_yield,
            "merges": self.merges,
            "new_queries": self.new_queries,
        }


def suggest_new_queries(gaps: list[Gap], *, limit: int = 10) -> list[str]:
    """Turn coverage gaps into concrete new query templates (deterministic)."""
    out: list[str] = []
    for g in gaps:
        if g.scope.startswith("city:"):
            city = g.scope.split(":", 1)[1]
            out.append(f"site:meetup.com {city} {g.technology}")
        else:
            out.append(f"{g.technology} conference India")
    # de-dupe, stable
    seen: set[str] = set()
    deduped = [q for q in out if not (q in seen or seen.add(q))]
    return deduped[:limit]


def optimize_queries(
    records: list[DiscoveryRecord],
    queries_run: list[str] | None = None,
    *,
    gaps: list[Gap] | None = None,
) -> QueryOptimization:
    by_query: dict[str, list[DiscoveryRecord]] = {}
    for r in records:
        if r.search_query:
            by_query.setdefault(r.search_query, []).append(r)

    stats: list[QueryStat] = []
    domain_sets: dict[str, set[str]] = {}
    for query, recs in by_query.items():
        domains = {r.domain for r in recs}
        domain_sets[query] = domains
        good = sum(1 for r in recs if r.approved or r.active)
        spam = sum(1 for r in recs if r.rejected and r.onboarding_state == "rejected")
        dups = sum(1 for r in recs if r.onboarding_state == "duplicate")
        yield_score = round(good / len(domains), 4) if domains else 0.0
        spam_rate = round(spam / len(domains), 4) if domains else 0.0

        if spam_rate >= _SPAM_RATE_RETIRE:
            rec, reason = "retire", f"spam_rate {spam_rate:.2f} too high"
        elif yield_score >= _BOOST_YIELD and len(domains) >= 2:
            rec, reason = "boost", f"strong yield {yield_score:.2f} over {len(domains)} domains"
        elif len(domains) >= _SPLIT_DOMAINS and yield_score < _SPLIT_YIELD:
            rec, reason = (
                "split",
                f"broad ({len(domains)} domains) but weak yield {yield_score:.2f}",
            )
        else:
            rec, reason = "keep", f"yield {yield_score:.2f}, spam {spam_rate:.2f}"
        stats.append(
            QueryStat(query, len(domains), good, spam, dups, yield_score, spam_rate, rec, reason)
        )

    # zero-yield queries: executed but produced no records at all
    zero_yield = sorted(set(queries_run or []) - set(by_query))

    # merge near-duplicate queries (heavy domain-set overlap)
    merges: list[list[str]] = []
    qs = sorted(domain_sets)
    for i, a in enumerate(qs):
        for b in qs[i + 1 :]:
            sa, sb = domain_sets[a], domain_sets[b]
            if not sa or not sb:
                continue
            jac = len(sa & sb) / len(sa | sb)
            if jac >= _MERGE_JACCARD:
                merges.append([a, b])

    stats.sort(key=lambda s: (s.recommendation, -s.yield_score, s.query))
    return QueryOptimization(
        stats=stats,
        zero_yield=zero_yield,
        merges=merges,
        new_queries=suggest_new_queries(gaps or []),
    )
