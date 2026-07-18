"""Coverage Engine (Phase 8A) — what has discovery reached, and what is still missing?

Compares the distinct cities / states / technologies / communities / organizers / universities that
appear in historical `DiscoveryRecord`s against curated *target universes*, and reports the gap.
Deterministic and observed-data-only: "covered" is exactly what the records contain; "uncovered" is
targets minus covered. Recommendations-only — nothing here changes discovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.discovery.optimization.store import DiscoveryRecord
from app.enrichment.taxonomy import TECHNOLOGIES, TOPICS

# Curated India-focused target universes (deterministic, self-contained).
TARGET_CITIES = frozenset(
    {
        "Bangalore",
        "Delhi",
        "Mumbai",
        "Hyderabad",
        "Pune",
        "Chennai",
        "Kolkata",
        "Ahmedabad",
        "Jaipur",
        "Chandigarh",
        "Kochi",
        "Goa",
        "Noida",
        "Gurgaon",
        "Thiruvananthapuram",
    }
)
TARGET_STATES = frozenset(
    {
        "Karnataka",
        "Maharashtra",
        "Delhi",
        "Telangana",
        "Tamil Nadu",
        "Kerala",
        "Gujarat",
        "West Bengal",
        "Rajasthan",
        "Haryana",
        "Punjab",
        "Uttar Pradesh",
        "Goa",
    }
)
TARGET_TECHNOLOGIES = frozenset(name for name, _ in list(TOPICS) + list(TECHNOLOGIES))
TARGET_COMMUNITIES = frozenset(
    {
        "GDG",
        "FOSS United",
        "PyData",
        "CNCF",
        "Hasgeek",
        "PyDelhi",
        "BangPypers",
        "Women Who Code",
        "Kubernetes Community",
        "Django Girls",
        "Rust India",
        "GoLang India",
    }
)
TARGET_UNIVERSITIES = frozenset(
    {"IIT", "NIT", "BITS Pilani", "IIIT", "VIT", "Manipal", "DTU", "NSUT"}
)


def _covered(values) -> set[str]:
    return {v for v in values if v}


@dataclass
class CoverageReport:
    covered_cities: list[str] = field(default_factory=list)
    uncovered_cities: list[str] = field(default_factory=list)
    covered_states: list[str] = field(default_factory=list)
    uncovered_states: list[str] = field(default_factory=list)
    covered_technologies: list[str] = field(default_factory=list)
    uncovered_technologies: list[str] = field(default_factory=list)
    covered_communities: list[str] = field(default_factory=list)
    uncovered_communities: list[str] = field(default_factory=list)
    covered_universities: list[str] = field(default_factory=list)
    uncovered_universities: list[str] = field(default_factory=list)
    distinct_organizers: int = 0
    coverage_pct: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "coverage_pct": self.coverage_pct,
            "distinct_organizers": self.distinct_organizers,
            "uncovered_cities": self.uncovered_cities,
            "uncovered_states": self.uncovered_states,
            "uncovered_technologies": self.uncovered_technologies,
            "uncovered_communities": self.uncovered_communities,
            "uncovered_universities": self.uncovered_universities,
            "covered_cities": self.covered_cities,
            "covered_technologies": self.covered_technologies,
            "covered_communities": self.covered_communities,
        }


def _pct(covered: set[str], target: frozenset[str]) -> float:
    hit = len(covered & target)
    return round(hit / len(target), 4) if target else 0.0


def build_coverage(records: list[DiscoveryRecord]) -> CoverageReport:
    cities = _covered(r.city for r in records)
    states = _covered(r.state for r in records)
    techs = _covered(t for r in records for t in r.technologies)
    communities = _covered(r.community for r in records)
    universities = _covered(r.university for r in records)
    organizers = _covered(r.organization for r in records)

    return CoverageReport(
        covered_cities=sorted(cities & TARGET_CITIES),
        uncovered_cities=sorted(TARGET_CITIES - cities),
        covered_states=sorted(states & TARGET_STATES),
        uncovered_states=sorted(TARGET_STATES - states),
        covered_technologies=sorted(techs & TARGET_TECHNOLOGIES),
        uncovered_technologies=sorted(TARGET_TECHNOLOGIES - techs),
        covered_communities=sorted(communities & TARGET_COMMUNITIES),
        uncovered_communities=sorted(TARGET_COMMUNITIES - communities),
        covered_universities=sorted(universities & TARGET_UNIVERSITIES),
        uncovered_universities=sorted(TARGET_UNIVERSITIES - universities),
        distinct_organizers=len(organizers),
        coverage_pct={
            "cities": _pct(cities, TARGET_CITIES),
            "states": _pct(states, TARGET_STATES),
            "technologies": _pct(techs, TARGET_TECHNOLOGIES),
            "communities": _pct(communities, TARGET_COMMUNITIES),
            "universities": _pct(universities, TARGET_UNIVERSITIES),
        },
    )
