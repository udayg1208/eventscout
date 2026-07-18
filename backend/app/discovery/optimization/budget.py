"""Crawl Budget Optimizer (Phase 8A) — allocate crawl effort by domain trust.

Turns `DomainTrustScore`s into explainable per-domain crawl budgets: increase frequency for
high-value domains, decrease for low/dead ones, stop blacklisted ones entirely. Also distributes a
fixed daily crawl pool proportionally to trust across the domains still worth crawling. Produces
recommendations only — nothing is scheduled.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.discovery.optimization.domain_ranker import DomainTrustScore

# Recommended crawl interval (hours) by trust tier.
_TIER_INTERVAL = {"high": 6, "medium": 12, "low": 48, "dead": 168}


@dataclass
class CrawlBudget:
    domain: str
    action: str  # increase | maintain | decrease | stop
    interval_hours: int | None  # None = stopped
    weight: float  # share of the daily crawl pool (0 if stopped)
    tier: str
    reason: str

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class BudgetPlan:
    budgets: list[CrawlBudget] = field(default_factory=list)
    daily_crawls: int = 0
    allocated: dict = field(default_factory=dict)  # domain → crawls/day

    def as_dict(self) -> dict:
        return {
            "daily_crawls": self.daily_crawls,
            "allocated": self.allocated,
            "budgets": [b.as_dict() for b in self.budgets],
        }


def allocate_budget(
    scores: list[DomainTrustScore],
    *,
    blacklist: set[str] | None = None,
    daily_crawls: int = 100,
) -> BudgetPlan:
    black = blacklist or set()
    budgets: list[CrawlBudget] = []
    crawlable: list[DomainTrustScore] = []

    for s in scores:
        if s.domain in black:
            budgets.append(CrawlBudget(s.domain, "stop", None, 0.0, s.tier, "blacklisted"))
            continue
        if s.tier == "dead":
            budgets.append(
                CrawlBudget(
                    s.domain, "stop", None, 0.0, s.tier, f"dead domain (trust {s.total:.2f})"
                )
            )
            continue
        crawlable.append(s)
        action = {"high": "increase", "medium": "maintain", "low": "decrease"}[s.tier]
        budgets.append(
            CrawlBudget(
                s.domain,
                action,
                _TIER_INTERVAL[s.tier],
                0.0,
                s.tier,
                f"{action} — trust {s.total:.2f} ({s.tier})",
            )
        )

    # distribute the daily pool proportionally to trust among crawlable domains
    trust_total = sum(s.total for s in crawlable)
    allocated: dict[str, float] = {}
    for b in budgets:
        if b.action == "stop":
            continue
        s = next(x for x in crawlable if x.domain == b.domain)
        weight = round(s.total / trust_total, 4) if trust_total else 0.0
        b.weight = weight
        allocated[b.domain] = round(weight * daily_crawls, 2)

    budgets.sort(key=lambda b: (-b.weight, b.domain))
    return BudgetPlan(budgets=budgets, daily_crawls=daily_crawls, allocated=allocated)
