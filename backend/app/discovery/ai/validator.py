"""Validator (Phase 6G / D4) — the safety gate before anything becomes a Candidate Source.

Two duties:
1. **Reject off-topic sources.** Entertainment, tourism, shopping, travel, weddings, concerts,
   sports, festivals, politics, religion, pornography, gambling. Most are HARD rejects (always);
   a few that legitimately co-occur with tech events (entertainment/concert/sports/festival — e.g.
   a "sports-tech hackathon", a "Python festival") are SOFT: rejected only when there is no strong
   technology signal to justify them. This realizes "require explicit supporting evidence".
2. **Require positive evidence.** A page with no technology, event-type, or community signal is
   rejected as *insufficient evidence* — D4 returns UNKNOWN rather than admitting a guess.

Rejected pages never become candidates; the reasons are explainable and returned for audit.
"""

from __future__ import annotations

import re

from app.discovery.ai.extractor import ExtractionInput
from app.discovery.ai.models import AIExtraction, ValidationResult

# Always reject on any hit — these are never professional-tech-event sources.
_HARD_REJECT = {
    "tourism": r"\btourism\b|\btourist\b|sightseeing",
    "travel": r"\btravel\b|\bflights?\b|\bhotels?\b|\bholiday\b|\bvacation\b|trip package",
    "shopping": r"\bshopping\b|\bsale\b|\bdiscount\b|\bcoupon\b|add to cart|buy now|\bdeals?\b",
    "weddings": r"\bwedding\b|\bmatrimony\b|\bbridal\b|\bmarriage\b",
    "politics": r"\bpolitical\b|\bpolitics\b|\belection\b|\brally\b|\bcampaign rally\b",
    "religion": r"\breligious\b|\btemple\b|\bchurch\b|\bmosque\b|\bpuja\b|\bprayer meeting\b",
    "pornography": r"\bporn\b|\bxxx\b|\badult content\b|\bescort\b",
    "gambling": r"\bcasino\b|\bbetting\b|\bgambling\b|\bpoker\b|\blottery\b",
}
# Reject only when the page has no strong tech signal (tech events may mention these in passing).
_SOFT_REJECT = {
    "entertainment": r"\bmovies?\b|\bcinema\b|\bfilm\b|box office|\bcomedy\b|stand-?up",
    "concerts": r"\bconcerts?\b|\bgig\b|\blive music\b|\bmusic festival\b",
    "sports": r"\bcricket\b|\bfootball\b|\bmatch tickets?\b|\btournament\b(?!.*hack)",
    "festivals": r"\bfestival\b|\bfair\b|\bcarnival\b",
}
_STRONG_TECH = 0.33  # tech_relevance at/above this (≈ ≥1 taxonomy tech) overrides SOFT rejects


def validate(page: ExtractionInput, extraction: AIExtraction) -> ValidationResult:
    body = f"{page.title or ''}\n{page.text}".lower()

    # positive supporting evidence
    evidence: list[str] = []
    if extraction.technologies.is_known:
        evidence.append(f"technologies={extraction.technologies.value}")
    if extraction.event_types.is_known:
        evidence.append(f"event_types={extraction.event_types.value}")
    if extraction.community.is_known:
        evidence.append(f"community={extraction.community.value}")
    tech_strong = (
        extraction.tech_relevance.is_known
        and float(extraction.tech_relevance.value) >= _STRONG_TECH  # type: ignore[arg-type]
    )

    reasons: list[str] = []
    for category, pat in _HARD_REJECT.items():
        m = re.search(pat, body)
        if m:
            reasons.append(f"{category}: '{m.group(0)}'")
    for category, pat in _SOFT_REJECT.items():
        m = re.search(pat, body)
        if m and not tech_strong:
            reasons.append(f"{category} (no overriding tech signal): '{m.group(0)}'")

    if reasons:
        return ValidationResult(passed=False, rejected_reasons=reasons, evidence=evidence)
    if not evidence:
        return ValidationResult(
            passed=False,
            rejected_reasons=[
                "insufficient evidence — no technology, event-type, or community signal"
            ],
            evidence=[],
        )
    return ValidationResult(passed=True, rejected_reasons=[], evidence=evidence)
