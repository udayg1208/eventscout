"""Monitoring (Phase 7A) — health metrics over the onboarding pipeline.

Computed deterministically from the onboarding candidates (no live providers are touched — 7A never
reaches production). Tracks approval/rejection/duplicate/sandbox-failure/promotion rates, average
confidence and sandbox quality, stale review items, and a conservative false-positive estimate.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.onboarding.models import (
    MonitoringSnapshot,
    OnboardingCandidate,
    OnboardingState,
)

_S = OnboardingState
_APPROVED_TRACK = {_S.AUTO_APPROVED, _S.APPROVED, _S.PROMOTED, _S.MONITORING, _S.ACTIVE}
_REJECTED = {_S.REJECTED, _S.BLACKLISTED, _S.DUPLICATE, _S.FAILED_SANDBOX}


def _rate(n: int, total: int) -> float:
    return round(n / total, 4) if total else 0.0


def build_monitoring(
    candidates: list[OnboardingCandidate],
    *,
    stale_after_hours: float = 72.0,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> MonitoringSnapshot:
    total = len(candidates)
    snap = MonitoringSnapshot(total=total)
    if not total:
        return snap

    counts: dict[OnboardingState, int] = {}
    confidences: list[float] = []
    qualities: list[float] = []
    now = clock()
    stale_cutoff = now - timedelta(hours=stale_after_hours)

    for c in candidates:
        counts[c.state] = counts.get(c.state, 0) + 1
        if c.confidence is not None:
            confidences.append(c.confidence.total)
        if c.sandbox is not None and c.sandbox.tested:
            qualities.append(c.sandbox.quality)
        if c.state is _S.MANUAL_REVIEW and c.updated_at and c.updated_at < stale_cutoff:
            snap.stale_review += 1
        # false-positive proxy: promoted despite weak confidence/quality → likely to underperform
        if c.state is _S.PROMOTED and (
            (c.confidence and c.confidence.total < 0.6) or (c.sandbox and c.sandbox.quality < 0.5)
        ):
            snap.false_positive_estimate += 1

    snap.auto_approved = counts.get(_S.AUTO_APPROVED, 0)
    snap.manual_review = counts.get(_S.MANUAL_REVIEW, 0)
    snap.approved = counts.get(_S.APPROVED, 0)
    snap.promoted = counts.get(_S.PROMOTED, 0)
    snap.rejected = counts.get(_S.REJECTED, 0)
    snap.duplicate = counts.get(_S.DUPLICATE, 0)
    snap.failed_sandbox = counts.get(_S.FAILED_SANDBOX, 0)
    snap.blacklisted = counts.get(_S.BLACKLISTED, 0)

    approved_track = sum(counts.get(s, 0) for s in _APPROVED_TRACK)
    rejected_track = sum(counts.get(s, 0) for s in _REJECTED)
    snap.approval_rate = _rate(approved_track, total)
    snap.rejection_rate = _rate(rejected_track, total)
    snap.duplicate_rate = _rate(snap.duplicate, total)
    snap.sandbox_failure_rate = _rate(snap.failed_sandbox, total)
    snap.promotion_success_rate = _rate(snap.promoted, approved_track)
    snap.avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
    snap.avg_quality = round(sum(qualities) / len(qualities), 4) if qualities else 0.0
    return snap
