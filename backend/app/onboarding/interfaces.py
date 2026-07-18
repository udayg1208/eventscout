"""Future onboarding seams (Phase 7A) — INTERFACES ONLY, no implementations.

7A stops before production. These abstractions mark exactly where later phases plug in; each raises
`NotImplementedError`. In particular `ProductionPromoter` is the hard boundary: turning a
`PromotionPlan` into a live registry/scheduler entry is Phase 7B and must not happen here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.onboarding.models import (
    OnboardingCandidate,
    PromotionPlan,
    ReviewPacket,
    SandboxOutcome,
)


class SandboxExecutor(ABC):
    """FUTURE: a real, fetch-based sandbox that actually pulls events from the candidate URL.

    7A uses a deterministic evidence-based dry-run instead (no network). A later phase implements
    this to fetch + validate + normalize a sample, reusing the ingestion sandbox (Phase 3C).
    """

    @abstractmethod
    async def run(self, snapshot: dict) -> SandboxOutcome:  # pragma: no cover
        raise NotImplementedError("real fetch-based sandbox is deferred (needs network)")


class ProductionPromoter(ABC):
    """FUTURE (Phase 7B): apply a PromotionPlan — register the provider, add a scheduler entry.

    This is the production boundary 7A must NOT cross. Implementing it means writing to the
    registry/scheduler, which is explicitly out of scope until 7B is approved.
    """

    @abstractmethod
    async def promote(
        self, candidate: OnboardingCandidate, plan: PromotionPlan
    ) -> None:  # pragma: no cover
        raise NotImplementedError("production promotion is Phase 7B — requires explicit approval")


class ReviewNotifier(ABC):
    """FUTURE: notify human reviewers (email/Slack/dashboard) that a ReviewPacket is queued."""

    @abstractmethod
    async def notify(self, packet: ReviewPacket) -> None:  # pragma: no cover
        raise NotImplementedError("reviewer notification is a future seam")


class AutoPromotionPolicy(ABC):
    """FUTURE: decide whether an AUTO_APPROVED candidate may promote without a human at all.

    In 7A even AUTO_APPROVED stops at a staged PromotionPlan; autonomous production promotion is a
    later, separately-approved capability.
    """

    @abstractmethod
    def may_auto_promote(self, candidate: OnboardingCandidate) -> bool:  # pragma: no cover
        raise NotImplementedError("autonomous promotion policy is deferred")
