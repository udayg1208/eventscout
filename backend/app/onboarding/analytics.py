"""Analytics (Phase 7A) — reporting over the onboarding pipeline.

Deterministic aggregation: inbox size, review-queue depth, auto vs human approvals, rejections,
promotion candidates, average confidence, and discovery trends (by state / feed type / discovery
method). Read-only over the onboarding candidates.
"""

from __future__ import annotations

from app.onboarding.models import (
    OnboardingAnalytics,
    OnboardingCandidate,
    OnboardingState,
)

_S = OnboardingState


def build_analytics(
    candidates: list[OnboardingCandidate], *, inbox_size: int | None = None
) -> OnboardingAnalytics:
    a = OnboardingAnalytics()
    a.inbox_size = inbox_size if inbox_size is not None else len(candidates)

    confidences: list[float] = []
    for c in candidates:
        a.by_state[c.state.value] = a.by_state.get(c.state.value, 0) + 1
        a.by_feed_type[c.feed_type] = a.by_feed_type.get(c.feed_type, 0) + 1
        a.by_discovered_by[c.discovered_by] = a.by_discovered_by.get(c.discovered_by, 0) + 1
        if c.confidence is not None:
            confidences.append(c.confidence.total)
        # human approval = APPROVED reached via a recorded review note (vs auto)
        if c.state in (_S.APPROVED, _S.PROMOTED) and c.review_notes:
            a.human_approvals += 1

    a.review_queue = a.by_state.get(_S.MANUAL_REVIEW.value, 0)
    a.auto_approvals = a.by_state.get(_S.AUTO_APPROVED.value, 0)
    a.rejections = sum(
        a.by_state.get(s.value, 0)
        for s in (_S.REJECTED, _S.BLACKLISTED, _S.DUPLICATE, _S.FAILED_SANDBOX)
    )
    a.promotion_candidates = a.by_state.get(_S.PROMOTED.value, 0)
    a.average_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
    return a
