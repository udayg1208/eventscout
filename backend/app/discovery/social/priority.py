"""Social source priority (Phase 8D) — explainable, no magic numbers.

Scores a discovered social source (0..1) from six factors: organizer reputation, tech relevance,
public accessibility, structured data, freshness, and historical yield. Every term is inspectable
(score × weight + reason).
"""

from __future__ import annotations

from app.discovery.social.models import SocialExtraction, SocialPriority

WEIGHTS = {
    "organizer_reputation": 0.20,
    "tech_relevance": 0.25,
    "public_accessibility": 0.15,
    "structured_data": 0.20,
    "freshness": 0.10,
    "historical_yield": 0.10,
}

_KNOWN_ORGS = (
    "gdg",
    "google developer",
    "foss united",
    "fossunited",
    "pydata",
    "cncf",
    "hasgeek",
    "pydelhi",
    "ieee",
    "kubernetes",
    "devfolio",
    "women who code",
    "rust",
    "golang",
)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def score(
    ex: SocialExtraction, *, historical_yield: float = 0.0, public_accessible: bool = True
) -> SocialPriority:
    factors: dict[str, float] = {}
    reasons: list[str] = []

    org_text = " ".join(str(f.value) for f in (ex.organizer, ex.community) if f.is_known).lower()
    if any(k in org_text for k in _KNOWN_ORGS):
        org_rep = 1.0
    elif ex.organizer.is_known or ex.community.is_known:
        org_rep = 0.6
    else:
        org_rep = 0.0
    factors["organizer_reputation"] = round(org_rep, 3)

    n_tech = len(ex.technologies.value) if ex.technologies.is_known else 0  # type: ignore[arg-type]
    factors["tech_relevance"] = round(_clamp(n_tech / 3.0), 3)
    factors["public_accessibility"] = 1.0 if public_accessible else 0.0

    # structured data: title/date from JSON-LD carry ≥0.9 confidence
    structured = (
        1.0
        if (ex.title.confidence >= 0.9 or ex.date.confidence >= 0.9)
        else (0.5 if ex.title.is_known else 0.0)
    )
    factors["structured_data"] = round(structured, 3)
    factors["freshness"] = 0.7 if ex.date.is_known else 0.0
    factors["historical_yield"] = round(_clamp(historical_yield), 3)

    total = round(sum(WEIGHTS[k] * v for k, v in factors.items()), 4)
    reasons = [f"{k}={v:.2f}×w{WEIGHTS[k]:.2f}" for k, v in factors.items()]
    reasons.append(f"→ total {total:.3f}")
    return SocialPriority(total=total, factors=factors, reasons=reasons)
