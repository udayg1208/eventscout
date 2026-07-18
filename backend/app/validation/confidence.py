"""Verification confidence merge (Phase 10E) — four contributions, explained.

Combines the seed's own confidence (10D), a discovery/reachability signal (did a page resolve?),
the universal-extraction confidence (10B), and the organizer confidence (10C) into one verification
confidence. Weights sum to 1.0; every contribution is explained. Deterministic; no ML.
"""

from __future__ import annotations

from app.validation.models import Evidence, VerificationConfidence

WEIGHTS = {
    "seed": 0.20,
    "discovery": 0.20,
    "universal": 0.30,
    "organizer": 0.30,
}


class VerificationConfidenceMerger:
    def merge(self, *, seed_confidence: float, evidence: Evidence) -> VerificationConfidence:
        discovery = 0.7 if evidence.reachable else 0.0
        if evidence.reachable and evidence.pages_fetched > 1:
            discovery = min(1.0, discovery + 0.15)
        comp = {
            "seed": max(0.0, min(1.0, seed_confidence)),
            "discovery": discovery,
            "universal": max(0.0, min(1.0, evidence.universal_confidence)),
            "organizer": max(0.0, min(1.0, evidence.organizer_confidence)),
        }
        reasons = {
            "seed": f"10D seed confidence {comp['seed']:.2f}",
            "discovery": ("page reachable" if evidence.reachable else "no page resolved")
            + f" → {comp['discovery']:.2f}",
            "universal": f"10B extraction {comp['universal']:.2f}; {evidence.events_found} events",
            "organizer": f"10C organizer {comp['organizer']:.2f}"
            + (f" ({evidence.organizer_name})" if evidence.organizer_name else ""),
        }
        total = round(sum(comp[k] * WEIGHTS[k] for k in WEIGHTS), 4)
        return VerificationConfidence(total=total, components=comp, reasons=reasons)
