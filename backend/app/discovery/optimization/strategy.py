"""Strategy Engine (Phase 8A) — the best discovery strategy per domain, from what worked.

Each domain was discovered by some strategy (structured D1 / framework D2 / search D3 / AI D4). The
strategy engine looks at which strategy actually *produced events* for a domain and recommends the
cheapest effective one — and flags wasteful strategies to avoid (e.g. "RSS domain → never run AI").
Deterministic mapping from observed feed types + yield. Recommendations only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.discovery.optimization.store import DiscoveryRecord

# feed type → the discovery strategy that produces it.
_STRUCTURED = {
    "rss",
    "atom",
    "ics",
    "google_calendar",
    "json_feed",
    "event_sitemap",
    "jsonld_event",
    "microdata_event",
    "opengraph_event",
}
_FRAMEWORK = {"next_data", "next_flight", "hydration_state", "embedded_json"}
_ENDPOINT = {"json_api", "graphql"}
_SEARCH = {"search_result"}
_AI = {"ai_extracted"}

# cost ordering (cheaper first) — prefer the cheapest strategy that yields events.
_STRATEGY_COST = {"structured": 1, "framework": 2, "search": 3, "ai": 4}
_ALL_STRATEGIES = ("structured", "framework", "search", "ai")


def _strategy_of(feed_type: str) -> str:
    if feed_type in _STRUCTURED:
        return "structured"
    if feed_type in _FRAMEWORK or feed_type in _ENDPOINT:
        return "framework"
    if feed_type in _AI:
        return "ai"
    return "search"


@dataclass
class StrategyRecommendation:
    domain: str
    best_strategy: str
    avoid: list[str]  # strategies that would be wasteful here
    reason: str
    yielded: dict = field(default_factory=dict)  # strategy → events observed

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def recommend_strategies(records: list[DiscoveryRecord]) -> list[StrategyRecommendation]:
    by_domain: dict[str, list[DiscoveryRecord]] = {}
    for r in records:
        by_domain.setdefault(r.domain, []).append(r)

    out: list[StrategyRecommendation] = []
    for domain, recs in by_domain.items():
        yielded: dict[str, int] = {}
        for r in recs:
            strat = _strategy_of(r.feed_type)
            yielded[strat] = yielded.get(strat, 0) + max(r.event_count, 1 if r.approved else 0)

        effective = {s for s, n in yielded.items() if n > 0}
        if effective:
            best = min(effective, key=lambda s: _STRATEGY_COST[s])
            reason = f"cheapest strategy that yielded events: {best}"
        else:
            best = "search"  # nothing worked yet → keep discovering via search
            reason = "no strategy has yielded events yet — keep searching"

        # avoid strategies strictly more expensive than the best effective one (wasteful)
        avoid = [
            s
            for s in _ALL_STRATEGIES
            if _STRATEGY_COST[s] > _STRATEGY_COST[best] and s not in effective
        ]
        out.append(
            StrategyRecommendation(
                domain=domain, best_strategy=best, avoid=avoid, reason=reason, yielded=yielded
            )
        )

    out.sort(key=lambda s: s.domain)
    return out
