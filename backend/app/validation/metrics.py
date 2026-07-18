"""Validation metrics (Phase 10E) — the loop's yield dashboard.

Tracks verification rate, acceptance rate, rejection rate, duplicate rate, average confidence, and
average evidence count across validated seeds. Fed one `VerificationResult` at a time.
Deterministic.
"""

from __future__ import annotations

from app.validation.models import VerificationDecision, VerificationResult


class ValidationMetrics:
    def __init__(self) -> None:
        self.total = 0
        self.verified = 0
        self.partial = 0
        self.insufficient = 0
        self.rejected = 0
        self.accepted = 0  # reached the inbox (inserted or updated)
        self.duplicates = 0  # already in the inbox (updated)
        self._conf_sum = 0.0
        self._evi_sum = 0

    def record(self, result: VerificationResult) -> None:
        self.total += 1
        self._conf_sum += result.confidence.total
        self._evi_sum += result.evidence.signal_count()
        d = result.decision
        if d is VerificationDecision.VERIFIED:
            self.verified += 1
        elif d is VerificationDecision.PARTIALLY_VERIFIED:
            self.partial += 1
        elif d is VerificationDecision.INSUFFICIENT_EVIDENCE:
            self.insufficient += 1
        else:
            self.rejected += 1
        if result.inbox_outcome in ("inserted", "updated"):
            self.accepted += 1
        if result.inbox_outcome == "updated":
            self.duplicates += 1

    @staticmethod
    def _rate(n: int, d: int) -> float:
        return round(n / d, 4) if d else 0.0

    def snapshot(self) -> dict:
        return {
            "total": self.total,
            "verification_rate": self._rate(self.verified + self.partial, self.total),
            "acceptance_rate": self._rate(self.accepted, self.total),
            "rejection_rate": self._rate(self.rejected, self.total),
            "duplicate_rate": self._rate(self.duplicates, self.accepted),
            "avg_confidence": round(self._conf_sum / self.total, 4) if self.total else 0.0,
            "avg_evidence_count": self._rate(self._evi_sum, self.total),
            "by_decision": {
                "verified": self.verified,
                "partial": self.partial,
                "insufficient": self.insufficient,
                "rejected": self.rejected,
            },
        }
