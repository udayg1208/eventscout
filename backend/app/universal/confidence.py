"""Universal confidence engine (Phase 10B) — explainable, eight components.

Combines eight independent signals into one score, each explained: - **structured** — did the data
come from a structured source (JSON-LD / microdata / hydration / ICS)? - **semantic**   — how rich
is the event (description, venue, multiple fields)? - **temporal**   — is there a real date (start;
end/deadline add a little)? - **location**   — city / venue / country present? - **technology** —
recognised technologies present? - **registration** — a registration URL present? - **organizer**
— an organizer present? - **provenance** — average provenance confidence of the extracted fields.

Weights sum to 1.0; the total is Σ(component × weight). Every component records a one-line reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.universal.models import STRUCTURED_SOURCES, ExtractedField, ExtractionSource

WEIGHTS = {
    "structured": 0.22,
    "temporal": 0.18,
    "provenance": 0.15,
    "location": 0.12,
    "technology": 0.10,
    "registration": 0.08,
    "organizer": 0.08,
    "semantic": 0.07,
}


@dataclass
class ConfidenceScore:
    total: float
    components: dict[str, float] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)


def _known(fields, name) -> bool:
    f = fields.get(name)
    return bool(f and f.is_known)


class UniversalConfidence:
    def score(self, fields: dict[str, ExtractedField], sources: list[str]) -> ConfidenceScore:
        comp: dict[str, float] = {}
        why: dict[str, str] = {}
        structured_names = {s.value for s in STRUCTURED_SOURCES}

        struct = (
            1.0
            if any(s in structured_names for s in sources)
            else (
                0.5
                if ExtractionSource.OPENGRAPH.value in sources
                or ExtractionSource.TABLE.value in sources
                else 0.25
            )
        )
        comp["structured"] = struct
        why["structured"] = f"sources={sources}"

        temporal = 0.0
        if _known(fields, "start_date"):
            temporal = (
                0.8
                + (0.1 if _known(fields, "end_date") else 0.0)
                + (0.1 if _known(fields, "deadline") else 0.0)
            )
        comp["temporal"] = min(1.0, temporal)
        why["temporal"] = "has start_date" if temporal else "no date"

        loc_hits = sum(_known(fields, n) for n in ("city", "venue", "country", "state"))
        comp["location"] = min(1.0, loc_hits / 2.0)
        why["location"] = f"{loc_hits} location field(s)"

        comp["technology"] = 1.0 if _known(fields, "technologies") else 0.0
        why["technology"] = "tech taxonomy match" if comp["technology"] else "no tech"

        comp["registration"] = 1.0 if _known(fields, "registration_url") else 0.0
        why["registration"] = "registration url" if comp["registration"] else "none"

        comp["organizer"] = 1.0 if _known(fields, "organizer") else 0.0
        why["organizer"] = "organizer present" if comp["organizer"] else "none"

        rich = sum(
            _known(fields, n)
            for n in ("description", "speakers", "sponsors", "images", "audience", "fee")
        )
        comp["semantic"] = min(1.0, rich / 3.0)
        why["semantic"] = f"{rich} rich field(s)"

        known = [f for f in fields.values() if f.is_known and f.provenance]
        prov = sum(f.confidence for f in known) / len(known) if known else 0.0
        comp["provenance"] = prov
        why["provenance"] = f"avg field confidence over {len(known)} field(s)"

        total = sum(comp[k] * WEIGHTS[k] for k in WEIGHTS)
        return ConfidenceScore(total=round(total, 4), components=comp, reasons=why)
