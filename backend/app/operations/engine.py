"""Operations Engine (Phase 7B) — the controlled production control plane.

    PromotionPlan → Preflight → Registry → Scheduler → Canary Sync → Health → Rollback|Active
                                                                          │
                                                    continuous monitoring ┘  → Learning → Analytics

Reuses the Provider State Store (health), the scheduler's rate util, and 7A's PromotionPlan. It
records a `ProductionRegistration` and drives it through the controlled flow. Every provider starts
in CANARY (a small mock sync); only a healthy canary earns ACTIVE, otherwise it rolls back
non-destructively. Additive — no Search/Catalog/Discovery/Provider/Frontend/API changes.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.operations.analytics import OperationsAnalytics, build_operations_analytics
from app.operations.feedback import FeedbackSignals, OutcomeRecord, collect_feedback
from app.operations.health import HealthSnapshot, HealthTracker
from app.operations.learning import LearningReport, learn
from app.operations.production import (
    DEFAULT_CANARY_THRESHOLDS,
    CanaryMetrics,
    CanarySync,
    CanaryThresholds,
    evaluate_canary,
    preflight,
)
from app.operations.registry import (
    ProductionRegistration,
    ProductionState,
    registration_from_plan,
)
from app.operations.rollback import (
    DEFAULT_ROLLBACK_THRESHOLDS,
    RollbackDecision,
    RollbackEngine,
    RollbackThresholds,
    evaluate_rollback,
)
from app.operations.scheduler import ScheduleConfig, build_schedule_config
from app.operations.store import OperationsStore
from app.storage.provider_state import DEFAULT_RETRY_POLICY, ProviderStateStore

_RISK_CONFIDENCE = {"low": 0.85, "medium": 0.65, "high": 0.5}


class OperationsEngine:
    def __init__(
        self,
        state_store: ProviderStateStore,
        store: OperationsStore,
        canary: CanarySync,
        *,
        canary_thresholds: CanaryThresholds = DEFAULT_CANARY_THRESHOLDS,
        rollback_thresholds: RollbackThresholds = DEFAULT_ROLLBACK_THRESHOLDS,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._state = state_store
        self._store = store
        self._canary = canary
        self._canary_thresholds = canary_thresholds
        self._rollback_thresholds = rollback_thresholds
        self._clock = clock
        self._health = HealthTracker(state_store, clock=clock)
        self._rollback = RollbackEngine(state_store, clock=clock)
        self._registrations: dict[str, ProductionRegistration] = {}
        self._schedules: dict[str, ScheduleConfig] = {}
        self._outcomes: dict[str, OutcomeRecord] = {}

    # ------------------------------ controlled promotion ------------------------------

    async def promote(
        self, plan, *, prediction: dict | None = None, spam: bool = False
    ) -> ProductionRegistration:
        now = self._clock()
        pf = preflight(plan)
        reg = registration_from_plan(plan, now=now)
        self._registrations[reg.provider_id] = reg

        if not pf.passed:
            reg.record(ProductionState.FAILED_PREFLIGHT, "; ".join(pf.reasons), now)
            await self._store.save_registration(reg)
            return reg

        reg.record(ProductionState.REGISTERED, "preflight passed", now)
        sched = build_schedule_config(reg.provider_id, plan)
        self._schedules[reg.provider_id] = sched
        reg.record(ProductionState.SCHEDULED, f"interval={sched.interval_seconds / 3600:.0f}h", now)
        await self._health.initialize(reg)
        reg.record(ProductionState.CANARY, "canary sync starting", now)

        # ---- canary sync (mock; deterministic) ----
        metrics = await self._canary.run(reg)
        reg.canary_syncs += 1
        await self._health.record_sync(reg.provider_id, metrics, policy=sched.retry_policy)
        await self._store.append_canary(
            {"provider_id": reg.provider_id, "at": now.isoformat(), **metrics.as_dict()}
        )

        # ---- rollback (hard safety) first, then canary health ----
        decision = evaluate_rollback(metrics, self._rollback_thresholds, spam=spam)
        canary = evaluate_canary(metrics, self._canary_thresholds)
        rolled_back = decision.should_rollback or not canary.healthy
        if rolled_back:
            if (
                not decision.should_rollback
            ):  # unhealthy but not a hard trigger → roll back on canary reasons
                decision = RollbackDecision(True, [], canary.reasons)
            entry = await self._rollback.rollback(reg, decision)
            await self._store.append_rollback(entry)
        else:
            reg.record(ProductionState.ACTIVE, "canary healthy → active", now)

        self._outcomes[reg.provider_id] = self._make_outcome(
            reg, plan, metrics, prediction, rolled_back
        )
        await self._store.save_registration(reg)
        return reg

    def _make_outcome(
        self, reg, plan, metrics: CanaryMetrics, prediction: dict | None, rolled_back: bool
    ) -> OutcomeRecord:
        pred = prediction or {}
        predicted_conf = pred.get("confidence", _RISK_CONFIDENCE.get(reg.risk_level, 0.6))
        return OutcomeRecord(
            provider_id=reg.provider_id,
            feed_type=plan.configuration.get("source_feed_type", "unknown"),
            discovered_by=pred.get("discovered_by", "crawl"),
            predicted_confidence=predicted_conf,
            predicted_band=pred.get("band", "auto_approve" if predicted_conf >= 0.72 else "review"),
            sandbox_passed=pred.get("sandbox_passed", True),
            was_manual=pred.get("was_manual", False),
            observed_healthy=(not rolled_back and metrics.fetch_success),
            observed_duplicate_rate=metrics.duplicate_rate,
            observed_quality=metrics.parse_quality,
            rolled_back=rolled_back,
        )

    # ------------------------------ continuous monitoring ------------------------------

    async def continuous_sync(
        self, provider_id: str, metrics: CanaryMetrics, *, spam: bool = False
    ) -> ProductionRegistration | None:
        """Record a post-promotion sync for an ACTIVE provider; auto-rollback on a hard signal."""
        reg = self._registrations.get(provider_id)
        if reg is None or reg.state is not ProductionState.ACTIVE:
            return None
        reg.active_syncs += 1
        sched = self._schedules.get(provider_id)
        policy = sched.retry_policy if sched else DEFAULT_RETRY_POLICY
        await self._health.record_sync(provider_id, metrics, policy=policy)
        decision = evaluate_rollback(metrics, self._rollback_thresholds, spam=spam)
        if decision.should_rollback:
            entry = await self._rollback.rollback(reg, decision)
            await self._store.append_rollback(entry)
            if provider_id in self._outcomes:
                self._outcomes[provider_id].rolled_back = True
                self._outcomes[provider_id].observed_healthy = False
        await self._store.save_registration(reg)
        return reg

    # ------------------------------ observability + learning ------------------------------

    async def health(self, provider_id: str) -> HealthSnapshot | None:
        return await self._health.snapshot(provider_id)

    def registrations(self) -> list[ProductionRegistration]:
        return list(self._registrations.values())

    def outcomes(self) -> list[OutcomeRecord]:
        return list(self._outcomes.values())

    def feedback(self, *, stale_providers: int = 0) -> FeedbackSignals:
        return collect_feedback(self.outcomes(), stale_providers=stale_providers)

    async def learn(self) -> LearningReport:
        report = learn(self.outcomes())
        await self._store.append_learning(report.as_dict())
        await self._store.append_calibration(report.model.as_dict())
        return report

    def analytics(self) -> OperationsAnalytics:
        return build_operations_analytics(
            self.registrations(), self.outcomes(), learn(self.outcomes())
        )
