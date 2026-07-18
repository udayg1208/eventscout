"""Orchestrator seams (Phase 9A) — where real engines plug in, and where 9B will.

The control plane never imports a discovery engine directly; it runs `StageRunner`s. These adapter
factories turn each existing engine into a `StageRunner` by calling its real entry point and mapping
its report to a `StageOutcome` — the concrete *reuse* of D1–D4 / 7A–7B / 8A–8E, additive and
engine-unmodifying. They import lazily (only when wired) and are **not exercised by the 9A tests or
spike**, which mock the seam. The distributed pieces (multi-worker leases, a remote task queue,
worker nodes) are Phase 9B and raise `NotImplementedError`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.orchestrator.models import StageContext, StageHealth, StageOutcome, StageRunner


def outcome_from_counts(
    *,
    discovered: int = 0,
    promoted: int = 0,
    rejected: int = 0,
    duplicates: int = 0,
    pages: int = 0,
    ai_calls: int = 0,
    produced_seeds: list[str] | None = None,
    health: StageHealth = StageHealth.HEALTHY,
) -> StageOutcome:
    return StageOutcome(
        health=health,
        discovered=discovered,
        promoted=promoted,
        rejected=rejected,
        duplicates=duplicates,
        pages=pages,
        ai_calls=ai_calls,
        produced_seeds=list(produced_seeds or []),
    )


def _num(report: object, *names: str) -> int:
    """First present numeric attribute among `names` (reports differ per engine)."""
    for n in names:
        v = getattr(report, n, None)
        if isinstance(v, int):
            return v
    return 0


# --------------------------------------------------------------------------- real-engine adapters
# Each returns a StageRunner. Production wires these; 9A tests/spike pass mocks instead.


def make_search_stage(engine, *, spec=None) -> StageRunner:
    """Wrap `SearchDiscoveryEngine.run(spec)` (D3)."""

    async def run(ctx: StageContext) -> StageOutcome:
        report = await (engine.run(spec) if spec is not None else engine.run())
        n = _num(report, "candidates_inserted", "inserted", "discovered")
        return outcome_from_counts(discovered=n, produced_seeds=list(ctx.seeds))

    return run


def make_web_stage(engine, *, spec=None) -> StageRunner:
    """Wrap `WebDiscoveryEngine.run(spec)` (8B)."""

    async def run(ctx: StageContext) -> StageOutcome:
        report = await (engine.run(spec) if spec is not None else engine.run())
        return outcome_from_counts(
            discovered=_num(report, "candidates_inserted", "inserted"),
            pages=_num(report, "pages", "fetched"),
        )

    return run


def make_expansion_stage(engine, *, max_pages: int = 50) -> StageRunner:
    """Wrap `ExpansionEngine.expand(seeds, max_pages=…)` (8C)."""

    async def run(ctx: StageContext) -> StageOutcome:
        report = await engine.expand(list(ctx.seeds), max_pages=max_pages)
        return outcome_from_counts(
            discovered=_num(report, "candidates_inserted", "inserted", "discovered"),
            pages=_num(report, "pages_crawled", "pages"),
        )

    return run


def make_rendered_stage(engine, pages) -> StageRunner:
    """Wrap `RenderedDiscoveryEngine.discover(pages)` (8E)."""

    async def run(ctx: StageContext) -> StageOutcome:
        report = await engine.discover(pages)
        return outcome_from_counts(
            discovered=_num(report, "candidates_inserted"),
            pages=_num(report, "pages"),
            ai_calls=_num(report, "provider_candidates"),
        )

    return run


def make_onboarding_stage(engine, inbox) -> StageRunner:
    """Wrap `OnboardingEngine.ingest_from_inbox(...)` (7A)."""

    async def run(ctx: StageContext) -> StageOutcome:
        candidates = await engine.ingest_from_inbox()
        promoted = sum(1 for c in candidates if getattr(c, "status", None))
        return outcome_from_counts(discovered=len(candidates), promoted=promoted)

    return run


# --------------------------------------------------------------------------- Phase 9B seams


class DistributedLeaseBackend(ABC):
    """FUTURE (9B): a shared lease store (Redis/Postgres) so many workers share one pipeline."""

    @abstractmethod
    async def acquire(self, stage: str, owner: str, ttl_s: float) -> bool:  # pragma: no cover
        raise NotImplementedError("distributed leasing is Phase 9B — 9A leases are in-process")


class TaskQueue(ABC):
    """FUTURE (9B): a durable cross-process work queue for fan-out to worker nodes."""

    @abstractmethod
    async def push(self, stage: str, payload: dict) -> None:  # pragma: no cover
        raise NotImplementedError("remote task queue is Phase 9B")

    @abstractmethod
    async def pull(self) -> dict | None:  # pragma: no cover
        raise NotImplementedError("remote task queue is Phase 9B")


class WorkerNode(ABC):
    """FUTURE (9B): a discovery worker that leases stages from the cluster and reports back."""

    @abstractmethod
    async def run(self) -> None:  # pragma: no cover
        raise NotImplementedError("multi-worker cluster is Phase 9B — 9A is single-process")
