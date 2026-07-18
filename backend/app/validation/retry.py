"""Retry policy (Phase 10E) — retry later / cooldown / max retries / abandonment.

INSUFFICIENT_EVIDENCE is treated as transient (the page may appear later, or a different candidate
URL may resolve): the seed is scheduled for a retry after a cooldown, up to `max_retries`, then
abandoned. VERIFIED / PARTIALLY_VERIFIED are terminal successes; REJECTED is a terminal not-found.
Deterministic, run-counter based (no wall clock).
"""

from __future__ import annotations

from app.validation.models import RetryState, VerificationDecision

_RETRYABLE = (VerificationDecision.INSUFFICIENT_EVIDENCE,)


class RetryPolicy:
    def __init__(self, *, max_retries: int = 3, cooldown_runs: int = 1) -> None:
        self.max_retries = max_retries
        self.cooldown_runs = cooldown_runs

    def eligible(self, state: RetryState | None, run: int) -> bool:
        """Is this seed eligible to (re)validate on `run`?"""
        if state is None:
            return True
        if state.abandoned:
            return False
        return run >= state.next_run

    def on_decision(
        self, state: RetryState, decision: VerificationDecision, run: int
    ) -> tuple[bool, RetryState]:
        """Update retry state after a decision. Returns (will_retry, state)."""
        state.last_decision = decision.value
        if decision not in _RETRYABLE:
            return False, state  # terminal (verified/partial/rejected)
        state.attempts += 1
        if state.attempts >= self.max_retries:
            state.abandoned = True
            return False, state
        state.next_run = run + self.cooldown_runs
        return True, state
