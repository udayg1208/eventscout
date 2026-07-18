"""Validation seams (Phase 10E) — the search seam + future autonomous-loop seams.

`SeedSearcher` is the injectable search step: given a verification query, return candidate URLs.
The engine calls it (duck-typed) alongside the strategy's URL templates. In tests a fixture
implements it; in production a thin adapter wraps the 8B/10A web search — deferred here
(`LiveSeedSearcher`). The `GrowthLoopScheduler` seam drives the full autonomous loop (10C → 10D →
10E → inbox → repeat). Both raise `NotImplementedError`; no network in 10E.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class SeedSearcher(ABC):
    """A verification search step: query → candidate URLs (injected into the engine)."""

    @abstractmethod
    def search(self, query: str) -> list[str]: ...


class LiveSeedSearcher(SeedSearcher):
    """FUTURE: wrap the 8B/10A real web search to turn a query into candidate URLs (network)."""

    def search(self, query: str) -> list[str]:  # pragma: no cover
        raise NotImplementedError(
            "live search is deferred — inject a fixture searcher in 10E tests"
        )


class GrowthLoopScheduler:
    """FUTURE: drive the autonomous loop — 10C organizers → 10D seeds → 10E validation → inbox."""

    @abstractmethod
    async def tick(self) -> None:  # pragma: no cover
        raise NotImplementedError(
            "the continuous growth loop is deferred — 10E validates on demand"
        )
