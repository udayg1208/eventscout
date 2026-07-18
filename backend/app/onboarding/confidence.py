"""Onboarding Confidence Engine (Phase 7A) — explainable, no hidden magic numbers.

Combines eight factors — discovery confidence, sandbox success, extraction quality, provider
health, content quality, duplicate rate, tech relevance, India relevance — into a single 0..1
score whose every term is inspectable (score × weight, with a human-readable detail). The total
falls into an auto / review / reject band by explicit thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.onboarding.models import (
    ConfidenceFactor,
    OnboardingConfidence,
    Recommendation,
    SandboxOutcome,
)

# Weights sum to 1.0 — the single source of truth for how factors combine.
WEIGHTS = {
    "discovery": 0.20,
    "sandbox": 0.18,
    "extraction": 0.12,
    "provider_health": 0.10,
    "content": 0.12,
    "duplicate": 0.08,
    "tech": 0.12,
    "india": 0.08,
}

# Provider-health proxy by discovery feed type: how reliably an ingestion provider could be built.
_PROVIDER_HEALTH = {
    "rss": 0.9,
    "atom": 0.9,
    "ics": 0.9,
    "google_calendar": 0.9,
    "json_feed": 0.9,
    "event_sitemap": 0.85,
    "jsonld_event": 0.85,
    "microdata_event": 0.7,
    "opengraph_event": 0.7,
    "next_data": 0.6,
    "next_flight": 0.6,
    "hydration_state": 0.6,
    "embedded_json": 0.6,
    "json_api": 0.5,
    "graphql": 0.5,
    "ai_extracted": 0.5,
    "search_result": 0.4,
    "unknown": 0.3,
}

_KEY_FIELDS = ("title", "city", "country", "organization", "technologies", "classification")


@dataclass(frozen=True)
class Thresholds:
    auto: float = 0.72  # ≥ auto → AUTO_APPROVE
    review: float = 0.45  # ≥ review (and < auto) → REVIEW; else REJECT


DEFAULT_THRESHOLDS = Thresholds()


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _discovery_score(snap: dict) -> tuple[float, str]:
    dc = snap.get("discovery_confidence")
    if dc is not None:
        return _clamp(float(dc)), f"D4 discovery_confidence={dc:.2f}"
    # proxy for D1/D2/D3 candidates that never ran the D4 confidence engine
    structured = min(1.0, snap.get("structured_data_score", 0) / 4.0)
    proxy = 0.5 * structured + 0.5 * float(snap.get("technology_confidence", 0.0))
    return _clamp(proxy), f"proxy (structured={structured:.2f}, tech)"


def _extraction_quality(snap: dict) -> tuple[float, str]:
    present = [f for f in _KEY_FIELDS if snap.get(f)]
    score = len(present) / len(_KEY_FIELDS)
    return round(score, 3), f"{len(present)}/{len(_KEY_FIELDS)} key fields present"


def _content_quality(snap: dict) -> tuple[float, str]:
    tech_kw = min(1.0, snap.get("tech_keyword_count", 0) / 4.0)
    has_org = 0.2 if snap.get("has_organizer") else 0.0
    has_reg = 0.15 if snap.get("has_registration_link") else 0.0
    events = min(0.25, 0.05 * snap.get("plausible_events", 0))
    score = _clamp(0.4 * tech_kw + has_org + has_reg + events)
    return round(score, 3), f"tech_kw+organizer+registration+events → {score:.2f}"


def score_onboarding(
    snapshot: dict,
    sandbox: SandboxOutcome,
    *,
    duplicate_penalty: float = 0.0,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> OnboardingConfidence:
    """Compute the explainable onboarding confidence and its auto/review/reject band."""
    snap = {**snapshot, "plausible_events": sandbox.plausible_events}

    disc, disc_detail = _discovery_score(snap)
    sand = sandbox.quality if sandbox.passed else 0.0
    extraction, extr_detail = _extraction_quality(snap)
    health = _PROVIDER_HEALTH.get(snap.get("feed_type", "unknown"), 0.3)
    content, content_detail = _content_quality(snap)
    dup = _clamp(1.0 - duplicate_penalty)
    tech = _clamp(float(snap.get("technology_confidence", 0.0)))
    india = _clamp(float(snap.get("india_confidence", 0.0)))

    factors = [
        ConfidenceFactor("discovery", round(disc, 3), WEIGHTS["discovery"], disc_detail),
        ConfidenceFactor(
            "sandbox",
            round(sand, 3),
            WEIGHTS["sandbox"],
            f"sandbox {'passed' if sandbox.passed else 'weak'} quality={sandbox.quality:.2f}",
        ),
        ConfidenceFactor("extraction", extraction, WEIGHTS["extraction"], extr_detail),
        ConfidenceFactor(
            "provider_health",
            round(health, 3),
            WEIGHTS["provider_health"],
            f"feed_type={snap.get('feed_type', 'unknown')}",
        ),
        ConfidenceFactor("content", content, WEIGHTS["content"], content_detail),
        ConfidenceFactor(
            "duplicate",
            round(dup, 3),
            WEIGHTS["duplicate"],
            f"duplicate_penalty={duplicate_penalty:.2f}",
        ),
        ConfidenceFactor("tech", round(tech, 3), WEIGHTS["tech"], "technology relevance"),
        ConfidenceFactor("india", round(india, 3), WEIGHTS["india"], "India relevance"),
    ]
    total = round(sum(f.contribution for f in factors), 4)

    if total >= thresholds.auto:
        band = Recommendation.AUTO_APPROVE
    elif total >= thresholds.review:
        band = Recommendation.REVIEW
    else:
        band = Recommendation.REJECT

    reasons = [f"{f.name}={f.score:.2f}×w{f.weight:.2f}={f.contribution:.3f}" for f in factors]
    reasons.append(
        f"→ total {total:.3f} ⇒ {band.value} (auto≥{thresholds.auto}, review≥{thresholds.review})"
    )
    return OnboardingConfidence(total=total, band=band, factors=factors, reasons=reasons)
