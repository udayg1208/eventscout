"""Opportunity Engine (Phase 10F) — detect where the ecosystem should grow next.

Given a deterministic snapshot of the current graph (`OpportunitySignals`), emit `GrowthOpportunity`
objects: cities seen in seeds but not yet covered by an organizer, dormant/inactive ecosystems,
stale organizers, seasonal windows (Hacktoberfest in October, DevFest in November, …), recurring
conferences predicted to return soon, and cities with organizers but no university coverage. Each
opportunity carries an explaining reason + evidence and can become a `GrowthTask`. Pure rules — no
ML, no network, no LLM. The engine only *proposes*; it never acts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.growth.models import GrowthOpportunity, OpportunityKind

# month (1-12) -> (season label, reason) for recurring seasonal tech events in India/globally
SEASONAL_CALENDAR: dict[int, tuple[str, str]] = {
    10: ("Hacktoberfest", "October is Hacktoberfest — open-source sprints peak"),
    11: ("DevFest", "November is DevFest season for Google Developer Groups"),
    2: ("FOSS/Republic hackathons", "February sees campus + FOSS hackathon waves"),
    8: ("Independence-month hackathons", "August campus hackathon season"),
}


@dataclass
class OpportunitySignals:
    """A deterministic read of the current growth graph, supplied by the engine wiring."""

    organizer_cities: set[str] = field(default_factory=set)  # cities with a known organizer
    seed_cities: set[str] = field(default_factory=set)  # cities appearing in generated seeds
    dormant_organizers: list[str] = field(default_factory=list)  # 10C health DORMANT/INACTIVE
    stale_organizers: list[str] = field(default_factory=list)  # from the freshness engine
    recurring_soon: list[str] = field(default_factory=list)  # 10C predicts a recurrence soon
    university_cities: set[str] = field(default_factory=set)  # cities with a university unit
    now: datetime | None = None


def _norm(city: str) -> str:
    return city.strip().lower()


class OpportunityEngine:
    def detect(self, signals: OpportunitySignals) -> list[GrowthOpportunity]:
        out: list[GrowthOpportunity] = []
        seen: set[str] = set()

        def add(op: GrowthOpportunity) -> None:
            if op.dedup_key not in seen:
                seen.add(op.dedup_key)
                out.append(op)

        covered = {_norm(c) for c in signals.organizer_cities}

        # NEW_CITY — a city named by seeds but with no organizer yet
        for city in sorted(signals.seed_cities):
            if _norm(city) and _norm(city) not in covered:
                add(
                    GrowthOpportunity(
                        OpportunityKind.NEW_CITY,
                        target=city,
                        reason=f"seeds reference {city} but no organizer is covered there",
                        priority=75,
                        evidence={"city": city},
                    )
                )

        # INACTIVE_ECOSYSTEM — a dormant/inactive organizer worth re-expanding
        for org in signals.dormant_organizers:
            add(
                GrowthOpportunity(
                    OpportunityKind.INACTIVE_ECOSYSTEM,
                    target=org,
                    reason=f"{org} is dormant/inactive — re-expand for fresh sub-ecosystems",
                    priority=55,
                    evidence={"organizer": org},
                )
            )

        # STALE_ORGANIZER — aged past its freshness TTL
        for org in signals.stale_organizers:
            add(
                GrowthOpportunity(
                    OpportunityKind.STALE_ORGANIZER,
                    target=org,
                    reason=f"{org} has not been refreshed within its TTL",
                    priority=50,
                    evidence={"organizer": org},
                )
            )

        # RECURRING_CONFERENCE — a series predicted to recur soon
        for org in signals.recurring_soon:
            add(
                GrowthOpportunity(
                    OpportunityKind.RECURRING_CONFERENCE,
                    target=org,
                    reason=f"{org} runs on a recurring cadence and a recurrence is predicted soon",
                    priority=80,
                    evidence={"organizer": org},
                )
            )

        # MISSING_UNIVERSITY_COVERAGE — a covered city with no university unit
        uni = {_norm(c) for c in signals.university_cities}
        for city in sorted(signals.organizer_cities):
            if _norm(city) and _norm(city) not in uni:
                add(
                    GrowthOpportunity(
                        OpportunityKind.MISSING_UNIVERSITY_COVERAGE,
                        target=city,
                        reason=f"{city} has organizers but no university/college coverage",
                        priority=45,
                        evidence={"city": city},
                    )
                )

        # SEASONAL_EVENT — the current month matches a known tech-event season
        now = signals.now
        if now is not None and now.month in SEASONAL_CALENDAR:
            label, reason = SEASONAL_CALENDAR[now.month]
            add(
                GrowthOpportunity(
                    OpportunityKind.SEASONAL_EVENT,
                    target=label,
                    reason=reason,
                    priority=85,
                    evidence={"month": now.month, "season": label},
                )
            )

        return out
