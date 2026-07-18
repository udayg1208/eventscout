"""Provider lifecycle — a deterministic state machine (Phase 7A).

Encodes exactly which transitions are legal. `transition()` mutates the candidate, bumps its
version, stamps `updated_at`, and returns an `AuditEntry` — so every state change is explainable and
recorded. Illegal transitions raise, making the pipeline's guarantees enforceable in code.

7A's automatic pipeline drives DISCOVERED → … → PROMOTED (plan staged) / MANUAL_REVIEW / a rejection
state. PROMOTED → MONITORING → ACTIVE are declared for the full lifecycle but are **7B territory**:
the engine never auto-enters them (that would mean touching production).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.onboarding.models import AuditEntry, OnboardingCandidate, OnboardingState

_S = OnboardingState

_TRANSITIONS: dict[OnboardingState, frozenset[OnboardingState]] = {
    _S.DISCOVERED: frozenset({_S.ANALYZED, _S.DUPLICATE, _S.BLACKLISTED}),
    _S.ANALYZED: frozenset({_S.SANDBOXED, _S.REJECTED, _S.DUPLICATE}),
    _S.SANDBOXED: frozenset({_S.SCORED, _S.FAILED_SANDBOX}),
    _S.SCORED: frozenset({_S.AUTO_APPROVED, _S.MANUAL_REVIEW, _S.REJECTED}),
    _S.AUTO_APPROVED: frozenset({_S.APPROVED}),
    _S.MANUAL_REVIEW: frozenset({_S.APPROVED, _S.REJECTED, _S.BLACKLISTED}),
    _S.APPROVED: frozenset({_S.PROMOTED}),
    _S.PROMOTED: frozenset({_S.MONITORING}),  # 7B only
    _S.MONITORING: frozenset({_S.ACTIVE, _S.REJECTED}),  # 7B only
    _S.ACTIVE: frozenset(),
    # terminals
    _S.REJECTED: frozenset(),
    _S.BLACKLISTED: frozenset(),
    _S.DUPLICATE: frozenset(),
    _S.FAILED_SANDBOX: frozenset(),
}


def allowed_transitions(state: OnboardingState) -> frozenset[OnboardingState]:
    return _TRANSITIONS.get(state, frozenset())


def can_transition(src: OnboardingState, dst: OnboardingState) -> bool:
    return dst in _TRANSITIONS.get(src, frozenset())


def is_terminal(state: OnboardingState) -> bool:
    return not _TRANSITIONS.get(state, frozenset())


class IllegalTransition(ValueError):
    pass


def transition(
    candidate: OnboardingCandidate,
    to: OnboardingState,
    *,
    actor: str,
    reason: str,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> AuditEntry:
    """Move `candidate` to `to` if legal (else raise). Returns the AuditEntry to persist."""
    src = candidate.state
    if not can_transition(src, to):
        raise IllegalTransition(f"{src.value} → {to.value} is not a legal onboarding transition")
    now = clock()
    entry = AuditEntry(
        key=candidate.key,
        timestamp=now,
        from_state=src.value,
        to_state=to.value,
        actor=actor,
        reason=reason,
    )
    candidate.state = to
    candidate.updated_at = now
    candidate.version += 1
    return entry
