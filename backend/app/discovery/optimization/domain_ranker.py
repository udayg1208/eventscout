"""Domain Ranker (Phase 8A) — score every discovered domain's trustworthiness.

Aggregates a domain's historical records into an explainable `DomainTrustScore` from seven observed
signals: approval rate, sandbox quality, production success, duplicate rate (inverted), freshness,
event richness, and crawl stability. Deterministic weighted scoring — every term is inspectable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.discovery.optimization.store import DiscoveryRecord

WEIGHTS = {
    "approval_rate": 0.20,
    "sandbox_quality": 0.15,
    "production_success": 0.20,
    "duplicate": 0.10,  # inverted (low duplication → high score)
    "freshness": 0.10,
    "event_richness": 0.15,
    "crawl_stability": 0.10,
}


@dataclass
class DomainTrustScore:
    domain: str
    total: float
    tier: str  # high | medium | low | dead
    records: int
    factors: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "domain": self.domain,
            "total": self.total,
            "tier": self.tier,
            "records": self.records,
            "factors": self.factors,
            "reasons": self.reasons,
        }


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _freshness_score(hours: float | None) -> float:
    if hours is None:
        return 0.0
    if hours <= 24:
        return 1.0
    if hours >= 24 * 30:
        return 0.0
    return round(1.0 - (hours - 24) / (24 * 30 - 24), 4)


def score_domain(domain: str, recs: list[DiscoveryRecord]) -> DomainTrustScore:
    n = len(recs)
    approval = _mean([1.0 if r.approved else 0.0 for r in recs])
    sandbox = _mean([r.sandbox_quality for r in recs])
    reached_prod = [r for r in recs if r.production_state in ("active", "rolled_back")]
    production = (
        _mean([1.0 if r.production_state == "active" else 0.0 for r in reached_prod])
        if reached_prod
        else 0.0
    )
    dup = 1.0 - _mean([r.duplicate_rate for r in recs])
    freshness = _mean([_freshness_score(r.freshness_hours) for r in recs])
    richness = _clamp(_mean([min(1.0, r.event_count / 10.0) for r in recs]))
    stability = _mean(
        [1.0 - (r.crawl_failures / r.crawl_attempts if r.crawl_attempts else 0.0) for r in recs]
    )

    factors = {
        "approval_rate": round(approval, 3),
        "sandbox_quality": round(sandbox, 3),
        "production_success": round(production, 3),
        "duplicate": round(_clamp(dup), 3),
        "freshness": round(freshness, 3),
        "event_richness": round(richness, 3),
        "crawl_stability": round(_clamp(stability), 3),
    }
    total = round(sum(WEIGHTS[k] * v for k, v in factors.items()), 4)
    tier = (
        "high" if total >= 0.7 else "medium" if total >= 0.45 else "low" if total >= 0.2 else "dead"
    )
    reasons = [f"{k}={v:.2f}×w{WEIGHTS[k]:.2f}" for k, v in factors.items()]
    return DomainTrustScore(
        domain=domain, total=total, tier=tier, records=n, factors=factors, reasons=reasons
    )


def rank_domains(records: list[DiscoveryRecord]) -> list[DomainTrustScore]:
    by_domain: dict[str, list[DiscoveryRecord]] = {}
    for r in records:
        by_domain.setdefault(r.domain, []).append(r)
    scores = [score_domain(d, recs) for d, recs in by_domain.items()]
    scores.sort(key=lambda s: (-s.total, s.domain))
    return scores
