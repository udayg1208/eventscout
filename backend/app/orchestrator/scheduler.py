"""Scheduler (Phase 9A) — decides when a stage is eligible to run.

Pure, deterministic, clock-injected. Understands cadence (continuous / hourly / daily / weekly /
manual), retry (a failed stage becomes due again after an exponential backoff, up to `retry_max`),
cooldown (a stage that asked to rest is not due until its cooldown expires), and pause/resume (a
paused stage is never due). No wall-clock, no sleeping — the engine owns time; this only answers
"is it due at `now`?" and "when next?".
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.orchestrator.models import (
    RunStatus,
    ScheduleKind,
    StageSpec,
    StageState,
)


class Scheduler:
    def is_paused(self, spec: StageSpec, state: StageState) -> bool:
        return spec.schedule.paused or state.paused

    def in_cooldown(self, state: StageState, now: datetime) -> bool:
        return state.cooldown_until is not None and now < state.cooldown_until

    def is_due(self, spec: StageSpec, state: StageState, now: datetime) -> bool:
        """True when the stage's cadence/retry timer has elapsed and it is neither paused,
        cooling down, nor permanently failed (exhausted retries)."""
        if not spec.enabled or self.is_paused(spec, state):
            return False
        if self.in_cooldown(state, now):
            return False
        if state.status is RunStatus.DEAD_LETTER:
            return False
        # a failed-but-retryable stage is due once its backoff window passes
        if state.status is RunStatus.FAILED:
            if state.retry_count >= spec.schedule.retry_max:
                return False
            return state.next_run is None or now >= state.next_run
        if spec.schedule.kind is ScheduleKind.MANUAL:
            return False
        if state.next_run is None or state.last_run is None:
            return True  # never run → due immediately
        return now >= state.next_run

    def next_run_at(self, spec: StageSpec, state: StageState, now: datetime) -> datetime:
        """When the stage should next become due after finishing at `now`."""
        if state.status is RunStatus.FAILED and state.retry_count < spec.schedule.retry_max:
            backoff = spec.schedule.retry_backoff_seconds * (2 ** max(0, state.retry_count - 1))
            return now + timedelta(seconds=backoff)
        interval = spec.schedule.base_interval()
        if interval is None:  # manual — no automatic next run
            return now
        return now + timedelta(seconds=interval)

    def cooldown_until(self, spec: StageSpec, now: datetime) -> datetime | None:
        secs = spec.schedule.cooldown_seconds
        return now + timedelta(seconds=secs) if secs > 0 else None
