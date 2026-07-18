"""Community similarity (Phase 10C) — how alike are two organizers.

An explainable score over eight signals (same organizer, same chapter, same series, same
university, same city, same technologies, same venue, same sponsors), weighted to sum to 1.0. Used
to connect the community graph (SAME_COMMUNITY / SAME_SERIES edges). Deterministic; no ML.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.organizers.identity import canonical_key
from app.organizers.models import OrganizerProfile

WEIGHTS = {
    "same_organizer": 0.30,
    "same_chapter": 0.18,
    "same_series": 0.14,
    "same_university": 0.10,
    "same_city": 0.10,
    "same_technologies": 0.08,
    "same_venue": 0.06,
    "same_sponsors": 0.04,
}


@dataclass
class SimilarityScore:
    total: float
    components: dict[str, float] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)


def _jaccard(a, b) -> float:
    sa, sb = {str(x).lower() for x in (a or [])}, {str(x).lower() for x in (b or [])}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _eq(a, b) -> float:
    return 1.0 if a and b and str(a).lower() == str(b).lower() else 0.0


class CommunitySimilarity:
    def score(self, a: OrganizerProfile, b: OrganizerProfile) -> SimilarityScore:
        comp: dict[str, float] = {}
        why: dict[str, str] = {}

        na, nb = a.get("name"), b.get("name")
        comp["same_organizer"] = (
            1.0 if (na and nb and canonical_key(na) == canonical_key(nb)) else 0.0
        )
        why["same_organizer"] = (
            "identity key match" if comp["same_organizer"] else "different identity"
        )

        comp["same_chapter"] = _eq(a.get("chapter"), b.get("chapter"))
        why["same_chapter"] = f"{a.get('chapter')} vs {b.get('chapter')}"

        comp["same_series"] = _jaccard(a.get("series"), b.get("series"))
        why["same_series"] = f"series overlap {comp['same_series']:.2f}"

        comp["same_university"] = _eq(a.get("university"), b.get("university"))
        why["same_university"] = f"{a.get('university')} vs {b.get('university')}"

        comp["same_city"] = _eq(a.get("city"), b.get("city"))
        why["same_city"] = f"{a.get('city')} vs {b.get('city')}"

        comp["same_technologies"] = _jaccard(a.get("technologies"), b.get("technologies"))
        why["same_technologies"] = f"tech overlap {comp['same_technologies']:.2f}"

        comp["same_venue"] = _eq(a.get("venue"), b.get("venue"))
        why["same_venue"] = f"{a.get('venue')} vs {b.get('venue')}"

        comp["same_sponsors"] = _jaccard(a.get("sponsors"), b.get("sponsors"))
        why["same_sponsors"] = f"sponsor overlap {comp['same_sponsors']:.2f}"

        total = round(sum(comp[k] * WEIGHTS[k] for k in WEIGHTS), 4)
        return SimilarityScore(total=total, components=comp, reasons=why)
