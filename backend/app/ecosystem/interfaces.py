"""Future ecosystem-expansion seams (Phase 10D) — INTERFACES ONLY, no implementations.

10D generates seeds deterministically from the graph; it never fetches. These mark where later
phases plug in: a seed validator that hands a seed to real discovery (10A/10B) to confirm it
exists, and a scheduler that re-expands continuously as the organizer graph grows. Each raises
`NotImplementedError`; none run in 10D — no network, no browser, no login.
"""

from __future__ import annotations

from abc import abstractmethod


class SeedValidator:
    """FUTURE: hand an ExpansionSeed to real discovery (10A/10B) to confirm the ecosystem exists.

    That needs network + the discovery pipeline; deliberately out of 10D's deterministic scope."""

    @abstractmethod
    async def validate(self, seed: dict) -> bool:  # pragma: no cover
        raise NotImplementedError("seed validation is deferred — 10D generates candidates only")


class ExpansionScheduler:
    """FUTURE: continuously re-expand as the organizer graph grows (cooldown-aware)."""

    @abstractmethod
    async def tick(self) -> None:  # pragma: no cover
        raise NotImplementedError("scheduled re-expansion is deferred — 10D is on-demand")
