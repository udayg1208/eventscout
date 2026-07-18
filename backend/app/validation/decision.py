"""Decision engine (Phase 10E) — evidence + confidence + strategy fit → a verdict.

Four states, deterministic, never inventing evidence: - **VERIFIED** — reachable, an event or
organizer found, strong confidence + strategy fit + ≥3 signals. - **PARTIALLY_VERIFIED** —
reachable with some signals but below the strong bar. - **INSUFFICIENT_EVIDENCE** — nothing
resolved, or a reachable page with almost no signal (retryable). - **REJECTED** — a reachable page
that clearly isn't the seed (no relevant signal, zero strategy fit).
"""

from __future__ import annotations

from app.validation.models import Evidence, VerificationConfidence, VerificationDecision

_STRONG_CONF = 0.5
_STRONG_STRATEGY = 0.66
_PARTIAL_CONF = 0.35
_PARTIAL_STRATEGY = 0.5


class DecisionEngine:
    def decide(
        self, evidence: Evidence, confidence: VerificationConfidence, strategy_score: float
    ) -> tuple[VerificationDecision, list[str]]:
        total = confidence.total
        # content signals = everything except mere reachability
        content = evidence.signal_count() - (1 if evidence.reachable else 0)

        if not evidence.reachable:
            return (
                VerificationDecision.INSUFFICIENT_EVIDENCE,
                ["no candidate URL resolved — cannot confirm; retry later"],
            )

        has_core = evidence.events_found > 0 or bool(evidence.organizer_name)
        strong = total >= _STRONG_CONF and strategy_score >= _STRONG_STRATEGY and content >= 2
        if has_core and strong:
            return (
                VerificationDecision.VERIFIED,
                [f"reachable + {content} content signals + strategy {strategy_score:.2f}"
                 f" + conf {total:.2f}"],
            )
        if content >= 1:
            return (
                VerificationDecision.PARTIALLY_VERIFIED,
                [f"reachable with {content} content signal(s) but below the strong bar"
                 f" (conf {total:.2f})"],
            )
        # reachable but the page carries no seed-relevant content → not the claimed seed
        return (
            VerificationDecision.REJECTED,
            ["reachable page carries no relevant evidence — not the claimed seed"],
        )
