"""Growth Steps (Phase 10F) — the reuse seam that wires the real engines to the loop.

Each `TaskKind` maps to a `GrowthStep` (`StepContext -> StepOutcome`). The adapters here call the
**existing** engines and modify none of them:

* expansion         → 10D `EcosystemExpansionEngine.expand_from(10C engine)`  → new seeds
* validation        → 10E `SeedValidationEngine.validate_batch(seeds)`        → inbox candidates
* onboarding        → observes inbox candidates (human-gated 7A; no auto-promotion by default)
* production_monitor→ observes provider health (7B); reports failures
* organizer_refresh → 10C `OrganizerIntelligenceEngine.ingest(url, html)`     → refreshed profile

A tiny `SeedBuffer` threads state between stages (expansion fills it, validation drains it then
fills the onboarding count). Tests inject constant/mock steps; the spike wires these for real. No
engine is imported at module top except by the adapter that uses it, keeping the loop additive.
No browser, no LLM; network only if the injected fetcher makes it (fixtures in CI).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.growth.models import (
    GrowthResource,
    GrowthStep,
    GrowthTask,
    StepContext,
    StepOutcome,
    TaskKind,
)


@dataclass
class SeedBuffer:
    """Shared pipeline state threaded between growth steps within one growth system."""

    pending_seeds: list = field(default_factory=list)
    seen_seed_keys: set = field(default_factory=set)
    pending_candidates: int = 0  # accepted candidates awaiting (human-gated) onboarding


def make_constant_step(outcome: StepOutcome) -> GrowthStep:
    """A fixed-outcome step — handy for wiring and tests."""

    async def run(ctx: StepContext) -> StepOutcome:
        return outcome

    return run


# --------------------------------------------------------------------------- real adapters


def make_expansion_step(org_engine, eco_engine, buffer: SeedBuffer) -> GrowthStep:
    """10D expansion over the 10C organizer graph → new Discovery Seeds into the buffer."""

    async def run(ctx: StepContext) -> StepOutcome:
        report = eco_engine.expand_from(org_engine)
        fresh = [s for s in eco_engine.seeds.all() if s.target_key not in buffer.seen_seed_keys]
        for s in fresh:
            buffer.seen_seed_keys.add(s.target_key)
            buffer.pending_seeds.append(s)
        follow = (
            [GrowthTask(kind=TaskKind.VALIDATION, target="batch", reason="new seeds to verify")]
            if fresh
            else []
        )
        return StepOutcome(
            success=True,
            seeds_generated=len(fresh),
            follow_ups=follow,
            cost={GrowthResource.CRAWL: max(1, report.sources_expanded)},
            notes=f"expanded {report.sources_expanded} sources → {len(fresh)} new seeds",
        )

    return run


def make_validation_step(val_engine, buffer: SeedBuffer) -> GrowthStep:
    """10E validation of buffered seeds → VERIFIED/PARTIALLY candidates into the existing inbox."""

    async def run(ctx: StepContext) -> StepOutcome:
        seeds = buffer.pending_seeds
        buffer.pending_seeds = []
        if not seeds:
            return StepOutcome(success=True, notes="no seeds in backlog")
        rep = await val_engine.validate_batch(seeds)
        accepted = rep.verified + rep.partial
        buffer.pending_candidates += rep.accepted_to_inbox
        follow = (
            [GrowthTask(kind=TaskKind.ONBOARDING, target="batch", reason="candidates in inbox")]
            if rep.accepted_to_inbox
            else []
        )
        return StepOutcome(
            success=True,
            seeds_validated=rep.total,
            accepted=accepted,
            rejected=rep.rejected,
            follow_ups=follow,
            cost={GrowthResource.VALIDATION: rep.total, GrowthResource.SEARCH: rep.total},
            notes=f"validated {rep.total}: {rep.verified} verified, {rep.partial} partial, "
            f"{rep.rejected} rejected → {rep.accepted_to_inbox} to inbox",
        )

    return run


def make_onboarding_step(
    buffer: SeedBuffer,
    *,
    promote_hook: Callable[[int], Awaitable[int]] | None = None,
) -> GrowthStep:
    """Observe candidates awaiting onboarding. Never creates providers on its own.

    Onboarding through 7A is human-gated. By default this step only *counts* candidates ready for
    review (promoted=0). A `promote_hook` — representing an explicit, human-approved 7A run — may be
    injected to record promotions; nothing here modifies providers or the catalog automatically.
    """

    async def run(ctx: StepContext) -> StepOutcome:
        n = buffer.pending_candidates
        buffer.pending_candidates = 0
        promoted = 0
        if promote_hook is not None and n:
            promoted = await promote_hook(n)
        return StepOutcome(
            success=True,
            promoted=promoted,
            cost={GrowthResource.ONBOARDING: n},
            notes=f"{n} candidate(s) ready for human-gated onboarding; promoted={promoted}",
        )

    return run


def make_production_monitor_step(
    health_provider: Callable[[], Awaitable[dict]] | None = None,
) -> GrowthStep:
    """Observe production health (7B). Reports failures; changes nothing."""

    async def run(ctx: StepContext) -> StepOutcome:
        if health_provider is None:
            return StepOutcome(success=True, notes="no health provider wired")
        health = await health_provider()
        failures = int(health.get("failures", 0))
        return StepOutcome(
            success=True,
            failures=failures,
            notes=f"observed production health: {health}",
        )

    return run


def make_organizer_refresh_step(org_engine, pages: dict[str, tuple[str, str]]) -> GrowthStep:
    """Re-ingest an organizer's page through 10C to refresh its profile. Merges; never deletes."""

    async def run(ctx: StepContext) -> StepOutcome:
        entry = pages.get(ctx.task.target)
        if entry is None:
            return StepOutcome(success=True, notes=f"no page for {ctx.task.target}")
        url, html = entry
        oid = org_engine.ingest(url, html)
        return StepOutcome(
            success=True,
            organizers_found=1 if oid else 0,
            cost={GrowthResource.CRAWL: 1},
            notes=f"refreshed {ctx.task.target} → {oid}",
        )

    return run
