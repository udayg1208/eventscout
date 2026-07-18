"""Feedback engine (Phase 7B) — compare what onboarding PREDICTED with what production OBSERVED.

Pairs each promoted provider's onboarding prediction (confidence, band, sandbox verdict, approval
route) with its real canary/continuous outcome (healthy, duplicate rate, quality, rolled back) and
distills accuracy signals. Pure analytics — no ML, no training. These signals feed the Learning
engine and the operations analytics.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OutcomeRecord:
    """One promoted provider: prediction (onboarding) vs observation (operations)."""

    provider_id: str
    feed_type: str
    discovered_by: str
    predicted_confidence: float
    predicted_band: str  # "auto_approve" | "review"
    sandbox_passed: bool
    was_manual: bool
    observed_healthy: bool
    observed_duplicate_rate: float
    observed_quality: float
    rolled_back: bool

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class FeedbackSignals:
    sample: int = 0
    sandbox_accuracy: float = 0.0  # sandbox-passed → actually healthy
    confidence_accuracy: float = 0.0  # 1 − mean|predicted − observed|
    approval_accuracy: float = 0.0  # approved → not rolled back
    duplicate_accuracy: float = 0.0  # predicted-low-dup held (observed ≤ 0.5)
    provider_quality: float = 0.0  # mean observed quality
    stale_providers: int = 0
    manual_overrides: int = 0
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["reasons"] = list(self.reasons)
        return d


def _frac(n: int, d: int) -> float:
    return round(n / d, 4) if d else 0.0


def collect_feedback(outcomes: list[OutcomeRecord], *, stale_providers: int = 0) -> FeedbackSignals:
    if not outcomes:
        return FeedbackSignals(stale_providers=stale_providers, reasons=["no outcomes yet"])

    sandbox_true = [o for o in outcomes if o.sandbox_passed]
    sandbox_hit = sum(1 for o in sandbox_true if o.observed_healthy)
    conf_err = sum(
        abs(o.predicted_confidence - (1.0 if o.observed_healthy else 0.0)) for o in outcomes
    )
    approved_ok = sum(1 for o in outcomes if not o.rolled_back)
    dup_ok = sum(1 for o in outcomes if o.observed_duplicate_rate <= 0.5)
    quality = sum(o.observed_quality for o in outcomes)
    manual = sum(1 for o in outcomes if o.was_manual)

    signals = FeedbackSignals(
        sample=len(outcomes),
        sandbox_accuracy=_frac(sandbox_hit, len(sandbox_true)),
        confidence_accuracy=round(1.0 - conf_err / len(outcomes), 4),
        approval_accuracy=_frac(approved_ok, len(outcomes)),
        duplicate_accuracy=_frac(dup_ok, len(outcomes)),
        provider_quality=round(quality / len(outcomes), 4),
        stale_providers=stale_providers,
        manual_overrides=manual,
    )
    signals.reasons = [
        f"sandbox: {sandbox_hit}/{len(sandbox_true)} sandbox-passed providers were healthy",
        f"approval: {approved_ok}/{len(outcomes)} promotions survived (not rolled back)",
        f"confidence mean abs error {conf_err / len(outcomes):.2f}",
    ]
    return signals
