"""Scheduler configuration (Phase 7B) — additive; reuses the existing scheduler utilities.

Derives a `ScheduleConfig` for a promoted provider from its PromotionPlan: run interval, execution
priority, a per-minute rate limit (via the scheduler's own `min_interval_seconds`), and a
`RetryPolicy` (the Provider State Store's own type). This *records* how the provider would be
scheduled — it does not modify `app/scheduler/` or enqueue anything into the live scheduler.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.scheduler.ratelimit import min_interval_seconds
from app.storage.provider_state import RetryPolicy

_VOLUME_RANK = {"high": 3, "medium": 2, "low": 1}
_VOLUME_RATE = {"high": 30.0, "medium": 10.0, "low": 5.0}  # requests/minute ceiling by volume


@dataclass(frozen=True)
class ScheduleConfig:
    provider_id: str
    interval_seconds: float
    priority: tuple[float, int]  # (interval, -volume_rank) — lower interval / higher volume first
    rate_limit_per_minute: float
    min_spacing_seconds: float
    retry_policy: RetryPolicy

    def as_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "interval_seconds": self.interval_seconds,
            "priority": list(self.priority),
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "min_spacing_seconds": self.min_spacing_seconds,
            "retry_policy": {
                "failure_threshold": self.retry_policy.failure_threshold,
                "base_backoff_seconds": self.retry_policy.base_backoff_seconds,
                "circuit_cooldown_seconds": self.retry_policy.circuit_cooldown_seconds,
                "refresh_interval_seconds": self.retry_policy.refresh_interval_seconds,
            },
        }


def retry_policy_from_plan(plan) -> RetryPolicy:
    """Map the plan's retry dict onto the state store's RetryPolicy (reuse the existing type)."""
    rp = plan.retry_policy or {}
    return RetryPolicy(
        failure_threshold=int(rp.get("failure_threshold", 3)),
        base_backoff_seconds=float(rp.get("backoff_seconds", 300)),
        circuit_cooldown_seconds=float(rp.get("cooldown_seconds", 1500)),
        refresh_interval_seconds=float(plan.refresh_interval_hours) * 3600.0,
    )


def build_schedule_config(provider_id: str, plan) -> ScheduleConfig:
    interval = float(plan.refresh_interval_hours) * 3600.0
    rate = _VOLUME_RATE.get(plan.expected_volume, 5.0)
    return ScheduleConfig(
        provider_id=provider_id,
        interval_seconds=interval,
        priority=(interval, -_VOLUME_RANK.get(plan.expected_volume, 1)),
        rate_limit_per_minute=rate,
        min_spacing_seconds=min_interval_seconds(rate),
        retry_policy=retry_policy_from_plan(plan),
    )
