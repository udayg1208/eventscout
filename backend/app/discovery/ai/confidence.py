"""Confidence Engine (Phase 6G / D4) — the realized, explainable Discovery Confidence.

Every prior phase deliberately deferred a "final confidence score" (D1/D2 collected only raw
signals). D4 finally computes one, by combining four signal families:

    deterministic  — strength of structured extraction (D1/D2 feeds/JSON-LD/framework)
    ai             — mean confidence of the AI-extracted known fields
    structured     — was structured event data actually present on the page?
    search         — the D3 search ranking (if the source came from search)

Weights are normalized over the components that are actually present (a source not found via
search isn't penalized for lacking a search score). The output carries per-component detail and
human-readable reasons — nothing opaque.
"""

from __future__ import annotations

from app.discovery.ai.models import ConfidenceComponent, DiscoveryConfidence

_WEIGHTS = {"deterministic": 0.30, "ai": 0.30, "structured": 0.25, "search": 0.15}

_DETAIL = {
    "deterministic": "structured extraction strength (D1/D2)",
    "ai": "mean confidence of AI-extracted fields",
    "structured": "structured event data present on page",
    "search": "search ranking of the discovered source (D3)",
}


def search_score_from_rank(rank: int | None) -> float | None:
    """Map a 1-based search rank to a 0..1 score (rank 1 → 1.0, decaying); None if not searched."""
    if rank is None or rank < 1:
        return None
    return round(1.0 / (1.0 + (rank - 1) * 0.3), 3)


def compute_confidence(
    *,
    deterministic: float | None = None,
    ai: float | None = None,
    structured: float | None = None,
    search: float | None = None,
) -> DiscoveryConfidence:
    """Combine the present signal families into a normalized DiscoveryConfidence."""
    present = {
        name: score
        for name, score in (
            ("deterministic", deterministic),
            ("ai", ai),
            ("structured", structured),
            ("search", search),
        )
        if score is not None
    }
    if not present:
        return DiscoveryConfidence(total=0.0, components=[], reasons=["no signals available"])

    weight_total = sum(_WEIGHTS[name] for name in present)
    components: list[ConfidenceComponent] = []
    reasons: list[str] = []
    total = 0.0
    for name, score in present.items():
        weight = _WEIGHTS[name] / weight_total
        total += weight * score
        components.append(
            ConfidenceComponent(
                name=name, score=round(score, 3), weight=round(weight, 3), detail=_DETAIL[name]
            )
        )
        reasons.append(f"{name}={score:.2f} × w{weight:.2f}")

    return DiscoveryConfidence(total=round(total, 3), components=components, reasons=reasons)
