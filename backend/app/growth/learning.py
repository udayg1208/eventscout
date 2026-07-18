"""Learning Engine (Phase 10F) — observe outcomes, recommend posture changes. Never auto-apply.

Accumulates the loop's observable outcomes (accepted seeds, rejected seeds, promoted providers,
production failures) and derives *recommendations* about growth posture: expand more when acceptance
is high, explore less when rejection dominates, revisit later when production is failing. It emits
`Recommendation`s only — it never mutates expansion weights, queries, budgets, or the queue. All
weight/query tuning stays a human decision; this engine just surfaces the signal, with its evidence.
Deterministic; no ML, no network.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.growth.models import Recommendation, RecommendationKind, StepOutcome


@dataclass
class _Tally:
    accepted: int = 0
    rejected: int = 0
    promoted: int = 0
    failures: int = 0
    validated: int = 0

    @property
    def decided(self) -> int:
        return self.accepted + self.rejected


class LearningEngine:
    def __init__(
        self,
        *,
        high_acceptance: float = 0.6,
        high_rejection: float = 0.6,
        failure_threshold: int = 3,
        min_sample: int = 5,
    ) -> None:
        self._t = _Tally()
        self._high_acceptance = high_acceptance
        self._high_rejection = high_rejection
        self._failure_threshold = failure_threshold
        self._min_sample = min_sample

    def observe(self, outcome: StepOutcome) -> None:
        self._t.accepted += outcome.accepted
        self._t.rejected += outcome.rejected
        self._t.promoted += outcome.promoted
        self._t.failures += outcome.failures
        self._t.validated += outcome.seeds_validated

    @property
    def acceptance_rate(self) -> float:
        return self._t.accepted / self._t.decided if self._t.decided else 0.0

    @property
    def rejection_rate(self) -> float:
        return self._t.rejected / self._t.decided if self._t.decided else 0.0

    def recommend(self) -> list[Recommendation]:
        recs: list[Recommendation] = []
        ev = {
            "accepted": self._t.accepted,
            "rejected": self._t.rejected,
            "promoted": self._t.promoted,
            "failures": self._t.failures,
        }

        # Production trouble takes precedence — slow down before growing.
        if self._t.failures >= self._failure_threshold:
            recs.append(
                Recommendation(
                    RecommendationKind.REVISIT_LATER,
                    reason=f"{self._t.failures} production failures — pause growth, revisit later",
                    evidence=ev,
                )
            )

        if self._t.decided >= self._min_sample:
            if self.acceptance_rate >= self._high_acceptance:
                recs.append(
                    Recommendation(
                        RecommendationKind.INCREASE_EXPANSION,
                        reason=f"acceptance rate {self.acceptance_rate:.2f} high — expand more",
                        evidence=ev,
                    )
                )
            elif self.rejection_rate >= self._high_rejection:
                recs.append(
                    Recommendation(
                        RecommendationKind.REDUCE_EXPLORATION,
                        reason=f"rejection rate {self.rejection_rate:.2f} high — explore less",
                        evidence=ev,
                    )
                )

        if not recs:
            recs.append(
                Recommendation(
                    RecommendationKind.MAINTAIN,
                    reason="outcomes within normal bounds — maintain current growth posture",
                    evidence=ev,
                )
            )
        return recs

    def tally(self) -> dict:
        return {
            "accepted": self._t.accepted,
            "rejected": self._t.rejected,
            "promoted": self._t.promoted,
            "failures": self._t.failures,
            "validated": self._t.validated,
        }
