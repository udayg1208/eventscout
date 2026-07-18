"""Growth Metrics (Phase 10F) — measure how fast and how efficiently the ecosystem grows.

Accumulates per-cycle outcomes into cumulative counters (new organizers / seeds / validated /
promoted / rejected) and derives velocity (accepted per cycle), ecosystem coverage (cities covered /
cities known), and expansion efficiency (accepted / seeds generated). Also detects steady state — a
run of cycles that produced no new growth — so the loop knows when to stop. Deterministic; offline.
"""

from __future__ import annotations

from collections import deque

from app.growth.models import GrowthMetricsSnapshot, StepOutcome


class GrowthMetricsEngine:
    def __init__(self, *, steady_window: int = 3) -> None:
        self._cycles = 0
        self._new_organizers = 0
        self._new_seeds = 0
        self._validated = 0
        self._promoted = 0
        self._rejected = 0
        self._accepted = 0
        self._seeds_generated_total = 0
        self._cities_known: set[str] = set()
        self._cities_covered: set[str] = set()
        self._progress = deque(maxlen=steady_window)
        self._steady_window = steady_window

    def record_cycle(self, outcome: StepOutcome) -> None:
        self._cycles += 1
        self._new_organizers += outcome.organizers_found
        self._new_seeds += outcome.seeds_generated
        self._validated += outcome.seeds_validated
        self._promoted += outcome.promoted
        self._rejected += outcome.rejected
        self._accepted += outcome.accepted
        self._seeds_generated_total += outcome.seeds_generated
        self._progress.append(outcome.is_progress())

    def observe_cities(
        self, *, known: set[str] | None = None, covered: set[str] | None = None
    ) -> None:
        if known:
            self._cities_known |= {c.strip().lower() for c in known if c.strip()}
        if covered:
            self._cities_covered |= {c.strip().lower() for c in covered if c.strip()}

    def is_steady(self) -> bool:
        """Steady state = a full window of cycles with no growth progress."""
        return len(self._progress) >= self._steady_window and not any(self._progress)

    def snapshot(self) -> GrowthMetricsSnapshot:
        velocity = self._accepted / self._cycles if self._cycles else 0.0
        coverage = (
            len(self._cities_covered & self._cities_known) / len(self._cities_known)
            if self._cities_known
            else 0.0
        )
        efficiency = (
            self._accepted / self._seeds_generated_total if self._seeds_generated_total else 0.0
        )
        return GrowthMetricsSnapshot(
            cycles=self._cycles,
            new_organizers=self._new_organizers,
            new_seeds=self._new_seeds,
            validated=self._validated,
            promoted=self._promoted,
            rejected=self._rejected,
            growth_velocity=velocity,
            ecosystem_coverage=coverage,
            expansion_efficiency=efficiency,
        )
