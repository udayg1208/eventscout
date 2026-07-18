"""Growth future seams (Phase 10F) — deferred integrations, explicitly not built here.

10F drives the growth loop *cycle by cycle* on demand (`GrowthEngine.run_cycle` / `run`). The
always-on daemon and the live human-gated bridges to 7A/7B are deliberately left as seams: turning
them on is an operational decision, and every safety rule (no auto provider changes, no auto weight
edits) must be enforced at that boundary. Each raises `NotImplementedError` so the intent is on
record without shipping an unattended actuator.
"""

from __future__ import annotations


class ContinuousDaemon:
    """An always-on driver that would call `GrowthEngine.run_cycle` on a wall-clock tick.

    Deferred: 10F is tick/`run`-driven and deterministic. A real daemon needs supervised scheduling,
    back-pressure, and an operator kill-switch before it runs unattended.
    """

    def __init__(self, *_args, **_kwargs) -> None:
        raise NotImplementedError(
            "ContinuousDaemon is a Phase 10F seam; drive GrowthEngine.run_cycle/run explicitly."
        )


class LiveOnboardingBridge:
    """Would forward accepted inbox candidates into the real, human-gated 7A onboarding.

    Deferred: onboarding creates providers, which this phase must never do automatically. The bridge
    exists to mark where an explicit, approved 7A hand-off attaches.
    """

    def __init__(self, *_args, **_kwargs) -> None:
        raise NotImplementedError(
            "LiveOnboardingBridge is a Phase 10F seam; onboarding stays human-gated (7A)."
        )


class LiveProductionMonitor:
    """Would read real 7B operations health to feed the production-monitor step.

    Deferred: wire the real operations health source here; the loop only *observes* it.
    """

    def __init__(self, *_args, **_kwargs) -> None:
        raise NotImplementedError(
            "LiveProductionMonitor is a Phase 10F seam; wire real 7B health at integration time."
        )
