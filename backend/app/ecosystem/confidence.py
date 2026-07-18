"""Expansion confidence (Phase 10D) — explainable, seven signals.

How likely is a generated seed to be a real, worthwhile new ecosystem? Combines graph distance
(closer = stronger), relationship strength (the kind of link), recurring history, and sponsor /
chapter / organizer / technology overlap between the source and the seed. Weights sum to 1.0; every
component is explained. Deterministic; no ML.
"""

from __future__ import annotations

from dataclasses import dataclass, field

WEIGHTS = {
    "relationship_strength": 0.22,
    "graph_distance": 0.20,
    "chapter_overlap": 0.14,
    "organizer_overlap": 0.12,
    "technology_overlap": 0.12,
    "sponsor_overlap": 0.10,
    "recurring_history": 0.10,
}


@dataclass
class ExpansionConfidenceScore:
    total: float
    components: dict[str, float] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


class ExpansionConfidence:
    def score(
        self,
        *,
        depth: int,
        relationship_strength: float,
        recurring: float = 0.0,
        sponsor_overlap: float = 0.0,
        chapter_overlap: float = 0.0,
        organizer_overlap: float = 0.0,
        technology_overlap: float = 0.0,
    ) -> ExpansionConfidenceScore:
        comp = {
            "relationship_strength": _clip(relationship_strength),
            "graph_distance": 1.0 / (1.0 + max(0, depth)),
            "chapter_overlap": _clip(chapter_overlap),
            "organizer_overlap": _clip(organizer_overlap),
            "technology_overlap": _clip(technology_overlap),
            "sponsor_overlap": _clip(sponsor_overlap),
            "recurring_history": _clip(recurring),
        }
        reasons = {
            "relationship_strength": f"link strength {comp['relationship_strength']:.2f}",
            "graph_distance": f"depth {depth} → {comp['graph_distance']:.2f}",
            "chapter_overlap": "same chapter family" if chapter_overlap else "different/none",
            "organizer_overlap": f"organizer overlap {comp['organizer_overlap']:.2f}",
            "technology_overlap": f"tech overlap {comp['technology_overlap']:.2f}",
            "sponsor_overlap": "shared sponsor" if sponsor_overlap else "none",
            "recurring_history": "recurring series" if recurring else "none",
        }
        total = round(sum(comp[k] * WEIGHTS[k] for k in WEIGHTS), 4)
        return ExpansionConfidenceScore(total=total, components=comp, reasons=reasons)
