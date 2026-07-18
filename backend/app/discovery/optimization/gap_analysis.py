"""Discovery Gap Analysis (Phase 8A) — where is coverage thin, per observed data?

Computes, per city, how many events each technology has, and flags technologies that are
under-represented in a city that otherwise has real volume — e.g. "Bangalore: 120 AI events, 2 Rust
events → recommend Rust search expansion". Never guesses: gaps come only from observed per-city /
per-technology counts in the historical records. Output is a recommendation, not an action.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.discovery.optimization.coverage import TARGET_TECHNOLOGIES
from app.discovery.optimization.store import DiscoveryRecord

_MIN_CITY_VOLUME = 20  # a city needs this many events before "thin" tech coverage is meaningful
_THIN_RATIO = 0.05  # a tech below this share of the city's events is under-covered
_GLOBAL_MIN = 3  # global: a target tech with ≤ this many events anywhere is a global gap


@dataclass
class Gap:
    scope: str  # "city:<name>" or "global"
    technology: str
    observed_events: int
    context_total: int  # city total (or global total)
    severity: float  # 0..1 — how thin relative to context
    recommendation: str

    def as_dict(self) -> dict:
        return {
            "scope": self.scope,
            "technology": self.technology,
            "observed_events": self.observed_events,
            "context_total": self.context_total,
            "severity": self.severity,
            "recommendation": self.recommendation,
        }


def _city_tech_counts(records: list[DiscoveryRecord]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for r in records:
        if not r.city:
            continue
        weight = max(1, r.event_count)
        city = counts.setdefault(r.city, {})
        for tech in r.technologies:
            city[tech] = city.get(tech, 0) + weight
    return counts


def find_gaps(records: list[DiscoveryRecord]) -> list[Gap]:
    gaps: list[Gap] = []
    city_tech = _city_tech_counts(records)

    # per-city thin-technology gaps
    for city, techs in city_tech.items():
        total = sum(techs.values())
        if total < _MIN_CITY_VOLUME:
            continue
        for tech in TARGET_TECHNOLOGIES:
            observed = techs.get(tech, 0)
            if observed <= max(2, _THIN_RATIO * total):
                severity = round(1.0 - observed / (total * _THIN_RATIO + 1e-9), 4)
                gaps.append(
                    Gap(
                        scope=f"city:{city}",
                        technology=tech,
                        observed_events=observed,
                        context_total=total,
                        severity=min(1.0, max(0.0, severity)),
                        recommendation=f"expand {tech} search in {city} "
                        f"({observed} events vs {total} total)",
                    )
                )

    # global gaps: target technologies with almost no coverage anywhere
    global_counts: dict[str, int] = {}
    grand_total = 0
    for techs in city_tech.values():
        for tech, n in techs.items():
            global_counts[tech] = global_counts.get(tech, 0) + n
            grand_total += n
    for tech in TARGET_TECHNOLOGIES:
        if global_counts.get(tech, 0) <= _GLOBAL_MIN:
            gaps.append(
                Gap(
                    scope="global",
                    technology=tech,
                    observed_events=global_counts.get(tech, 0),
                    context_total=grand_total,
                    severity=1.0,
                    recommendation=f"add {tech} discovery — nearly absent across all cities",
                )
            )

    # most severe first; stable tiebreak by scope+technology
    gaps.sort(key=lambda g: (-g.severity, g.scope, g.technology))
    return gaps
