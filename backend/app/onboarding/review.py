"""Review Engine (Phase 7A) — build the human-review packet.

A `ReviewPacket` is everything a reviewer needs to decide, with nothing hidden: the discovered URL,
the confidence and its reasons, an extraction summary, sample-event evidence, the sandbox report,
detected technologies, explicit risks, and a recommendation. Deterministic; derived only from the
candidate's discovery evidence.
"""

from __future__ import annotations

from app.onboarding.models import (
    OnboardingConfidence,
    Recommendation,
    ReviewPacket,
    SandboxOutcome,
)

_UNPROVEN = {"search_result", "ai_extracted", "json_api", "graphql"}


def _risks(snap: dict, sandbox: SandboxOutcome) -> list[str]:
    risks: list[str] = []
    feed = snap.get("feed_type", "unknown")
    if feed == "search_result":
        risks.append("unproven: discovered by search, not yet crawled — crawl before ingesting")
    if feed == "ai_extracted":
        risks.append("AI-understood prose: heuristic-extracted fields; verify before ingesting")
    if feed in {"json_api", "graphql"}:
        risks.append(f"{feed}: endpoint must be probed and its schema mapped before ingestion")
    if float(snap.get("india_confidence", 0.0)) < 0.5:
        risks.append("weak India relevance")
    if float(snap.get("technology_confidence", 0.0)) < 0.34:
        risks.append("weak technology relevance")
    if not snap.get("has_organizer"):
        risks.append("no organizer identified")
    if sandbox.plausible_events == 0:
        risks.append("no event evidence found in discovery data")
    if snap.get("structured_data_score", 0) == 0 and feed in _UNPROVEN:
        risks.append("no structured data — ingestion parser undetermined")
    return risks


def _sample_events(snap: dict, sandbox: SandboxOutcome) -> list[str]:
    """Discovery finds SOURCES, not events — so 'samples' are the evidence we actually have."""
    samples: list[str] = []
    title = snap.get("title")
    if title:
        samples.append(f"source title: {title}")
    if sandbox.plausible_events:
        samples.append(f"~{sandbox.plausible_events} plausible events (from discovery evidence)")
    else:
        samples.append("no concrete event samples — source-level discovery only")
    return samples


def build_review_packet(
    snapshot: dict, confidence: OnboardingConfidence, sandbox: SandboxOutcome
) -> ReviewPacket:
    extraction_summary = {
        "organization": snapshot.get("organization"),
        "city": snapshot.get("city"),
        "country": snapshot.get("country"),
        "classification": snapshot.get("classification"),
        "discovered_by": snapshot.get("discovered_by"),
        "feed_type": snapshot.get("feed_type"),
        "structured_data_score": snapshot.get("structured_data_score", 0),
    }
    return ReviewPacket(
        url=snapshot["url"],
        domain=snapshot["domain"],
        confidence=confidence.total,
        confidence_reasons=list(confidence.reasons),
        extraction_summary=extraction_summary,
        sample_events=_sample_events(snapshot, sandbox),
        sandbox=sandbox,
        technologies=list(snapshot.get("technologies", [])),
        risks=_risks(snapshot, sandbox),
        recommendation=confidence.band
        if isinstance(confidence.band, Recommendation)
        else Recommendation.REVIEW,
    )
