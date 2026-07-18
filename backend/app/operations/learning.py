"""Learning engine (Phase 7B) — deterministic confidence calibration. NO ML.

Compares PREDICTED onboarding confidence against OBSERVED production success, bucketed, to see where
the confidence model is over- or under-confident. Produces an **explainable** `LearningReport` with
a per-feed-type suggested adjustment (a `CalibrationModel`). Applying a model is a pure function
(`apply_calibration`) that a future onboarding integration can consume — 7B only *produces* the
report; it does not mutate 7A. No training, no gradients — bucketed arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.operations.feedback import OutcomeRecord

_BUCKETS = ((0.0, 0.45), (0.45, 0.6), (0.6, 0.72), (0.72, 0.85), (0.85, 1.01))


@dataclass(frozen=True)
class CalibrationBucket:
    lower: float
    upper: float
    count: int
    predicted_mean: float
    observed_rate: float  # fraction healthy & not rolled back
    delta: float  # observed − predicted (negative ⇒ over-confident)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class CalibrationModel:
    """Per-feed-type additive confidence nudge (bounded), plus a global fallback."""

    adjustments: dict[str, float] = field(default_factory=dict)
    global_delta: float = 0.0

    def as_dict(self) -> dict:
        return {"adjustments": dict(self.adjustments), "global_delta": self.global_delta}


@dataclass
class LearningReport:
    sample: int
    buckets: list[CalibrationBucket]
    calibration_error: float  # count-weighted mean |delta|
    model: CalibrationModel
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "sample": self.sample,
            "calibration_error": self.calibration_error,
            "buckets": [b.as_dict() for b in self.buckets],
            "model": self.model.as_dict(),
            "reasons": list(self.reasons),
        }


def _observed(o: OutcomeRecord) -> float:
    return 1.0 if (o.observed_healthy and not o.rolled_back) else 0.0


def _clampd(x: float, lo: float = -0.2, hi: float = 0.2) -> float:
    return max(lo, min(hi, x))


def learn(outcomes: list[OutcomeRecord]) -> LearningReport:
    if not outcomes:
        return LearningReport(0, [], 0.0, CalibrationModel(), ["no outcomes yet"])

    buckets: list[CalibrationBucket] = []
    weighted_error = 0.0
    for lo, hi in _BUCKETS:
        members = [o for o in outcomes if lo <= o.predicted_confidence < hi]
        if not members:
            continue
        pred = sum(o.predicted_confidence for o in members) / len(members)
        obs = sum(_observed(o) for o in members) / len(members)
        delta = round(obs - pred, 4)
        buckets.append(
            CalibrationBucket(lo, hi, len(members), round(pred, 4), round(obs, 4), delta)
        )
        weighted_error += abs(delta) * len(members)

    # per-feed-type suggested nudge = mean(observed − predicted), bounded
    by_feed: dict[str, list[float]] = {}
    for o in outcomes:
        by_feed.setdefault(o.feed_type, []).append(_observed(o) - o.predicted_confidence)
    adjustments = {ft: round(_clampd(sum(v) / len(v)), 4) for ft, v in by_feed.items()}
    global_delta = round(
        _clampd(sum(_observed(o) - o.predicted_confidence for o in outcomes) / len(outcomes)), 4
    )

    error = round(weighted_error / len(outcomes), 4)
    reasons = [
        f"{len(outcomes)} outcomes across {len(buckets)} confidence buckets",
        f"count-weighted calibration error {error:.3f} (0 = perfectly calibrated)",
    ]
    over = [b for b in buckets if b.delta < -0.1]
    if over:
        reasons.append(
            "over-confident in bucket(s): "
            + ", ".join(f"[{b.lower:.2f},{b.upper:.2f})Δ{b.delta:+.2f}" for b in over)
        )
    return LearningReport(
        sample=len(outcomes),
        buckets=buckets,
        calibration_error=error,
        model=CalibrationModel(adjustments=adjustments, global_delta=global_delta),
        reasons=reasons,
    )


def apply_calibration(raw_confidence: float, feed_type: str, model: CalibrationModel) -> float:
    """Pure: nudge a raw onboarding confidence by the learned per-feed-type delta (clamped 0..1).

    A future onboarding integration can consume this; 7B does not mutate 7A itself.
    """
    delta = model.adjustments.get(feed_type, model.global_delta)
    return round(max(0.0, min(1.0, raw_confidence + delta)), 4)
