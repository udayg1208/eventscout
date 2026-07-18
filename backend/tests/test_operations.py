"""Phase 7B — Production Operations tests. Deterministic, no network."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.onboarding.models import PromotionPlan
from app.operations import (
    CanaryMetrics,
    InMemoryOperationsStore,
    MockCanarySync,
    OperationsEngine,
    OutcomeRecord,
    ProductionState,
    RollbackReason,
    apply_calibration,
    collect_feedback,
    evaluate_canary,
    evaluate_rollback,
    learn,
    preflight,
    provider_id_for,
)
from app.storage.sqlite_provider_state import SQLiteProviderStateStore

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


def plan(
    domain="gdg.dev",
    ptype="rss",
    *,
    refresh=12,
    vol="medium",
    risk="low",
    caps=("list_events", "delta_sync"),
    feed="rss",
) -> PromotionPlan:
    return PromotionPlan(
        url=f"https://{domain}/feed",
        domain=domain,
        provider_type=ptype,
        configuration={"url": f"https://{domain}/feed", "domain": domain, "source_feed_type": feed},
        refresh_interval_hours=refresh,
        retry_policy={"failure_threshold": 3, "backoff_seconds": 300, "cooldown_seconds": 1500},
        capabilities=list(caps),
        expected_volume=vol,
        risk_assessment={"level": risk, "factors": []},
        notes=["PLAN ONLY"],
    )


HEALTHY = CanaryMetrics(fetched=10, valid=10, duplicates=1, new_events=9, latency_ms=200.0)
FAILING = CanaryMetrics(
    fetched=8, valid=2, duplicates=8, new_events=0, latency_ms=9000.0, failures=3
)
LOW_EVENTS = CanaryMetrics(fetched=5, valid=5, duplicates=0, new_events=0, latency_ms=200.0)


def ops(scenarios=None, default=None):
    state = SQLiteProviderStateStore(":memory:")
    store = InMemoryOperationsStore()
    engine = OperationsEngine(
        state, store, MockCanarySync(scenarios or {}, default), clock=lambda: NOW
    )
    return engine, state, store


# --------------------------- preflight ---------------------------


def test_preflight_pass_and_fail():
    assert preflight(plan()).passed is True
    bad = preflight(plan(ptype="manual", refresh=0))
    assert bad.passed is False
    assert not bad.checks["provider_type_known"] and not bad.checks["refresh_interval_sane"]


# --------------------------- canary ---------------------------


def test_canary_metrics_properties():
    assert HEALTHY.parse_quality == 1.0 and HEALTHY.duplicate_rate == 0.1
    assert FAILING.parse_quality == 0.25 and FAILING.duplicate_rate == 1.0


def test_evaluate_canary_healthy_and_unhealthy():
    assert evaluate_canary(HEALTHY).healthy is True
    bad = evaluate_canary(FAILING)
    assert bad.healthy is False and bad.reasons


# --------------------------- promotion + canary → active/rollback ---------------------------


def test_promote_healthy_to_active_with_history():
    engine, state, _ = ops(default=HEALTHY)
    reg = run(engine.promote(plan()))
    assert reg.state is ProductionState.ACTIVE
    trail = [h["to"] for h in reg.history]
    assert trail == ["registered", "scheduled", "canary", "active"]
    run(state.close())


def test_promote_failed_preflight_no_canary():
    engine, state, _ = ops(default=HEALTHY)
    reg = run(engine.promote(plan(ptype="manual")))
    assert reg.state is ProductionState.FAILED_PREFLIGHT
    assert reg.canary_syncs == 0  # never reached canary
    run(state.close())


def test_promote_rollback_on_bad_canary_is_nondestructive():
    engine, state, store = ops(scenarios={provider_id_for("bad.org"): FAILING})
    reg = run(engine.promote(plan(domain="bad.org")))
    assert reg.state is ProductionState.ROLLED_BACK
    # history is preserved (never deleted) — the full path plus the rollback
    trail = [h["to"] for h in reg.history]
    assert trail == ["registered", "scheduled", "canary", "rolled_back"]
    rollback_hist = run(store.history("rollback"))
    assert len(rollback_hist) == 1 and "duplicate_explosion" in rollback_hist[0]["reasons"]
    # the provider is disabled in the reused state store (excluded from scheduling), not deleted
    st = run(state.get_provider_state(reg.provider_id))
    assert st is not None and st.enabled is False
    run(state.close())


# --------------------------- rollback rules ---------------------------


def test_evaluate_rollback_each_trigger():
    assert RollbackReason.DUPLICATE_EXPLOSION in evaluate_rollback(FAILING).reasons
    assert RollbackReason.ZERO_EVENTS in evaluate_rollback(LOW_EVENTS).reasons
    spam = evaluate_rollback(HEALTHY, spam=True)
    assert spam.should_rollback and RollbackReason.SPAM_DETECTED in spam.reasons
    assert evaluate_rollback(HEALTHY).should_rollback is False


# --------------------------- health ---------------------------


def test_health_snapshot_reuses_provider_state():
    engine, state, _ = ops(default=HEALTHY)
    run(engine.promote(plan()))
    snap = run(engine.health(provider_id_for("gdg.dev")))
    assert snap.health_status == "healthy" and snap.uptime == 1.0
    assert snap.event_quality == 1.0 and snap.total_successes == 1
    run(state.close())


def test_continuous_sync_can_rollback_active_provider():
    engine, state, store = ops(default=HEALTHY)
    reg = run(engine.promote(plan()))
    assert reg.state is ProductionState.ACTIVE
    # a later sync goes bad → auto-rollback of the live provider
    out = run(engine.continuous_sync(reg.provider_id, FAILING))
    assert out.state is ProductionState.ROLLED_BACK
    assert len(run(store.history("rollback"))) == 1
    run(state.close())


# --------------------------- feedback + learning + calibration ---------------------------


def _outcome(pid, conf, feed, healthy, rolled=False, manual=False, dup=0.1, q=1.0):
    return OutcomeRecord(
        provider_id=pid,
        feed_type=feed,
        discovered_by="crawl",
        predicted_confidence=conf,
        predicted_band="auto_approve" if conf >= 0.72 else "review",
        sandbox_passed=True,
        was_manual=manual,
        observed_healthy=healthy,
        observed_duplicate_rate=dup,
        observed_quality=q,
        rolled_back=rolled,
    )


def test_feedback_signals():
    outcomes = [
        _outcome("a", 0.9, "rss", True),
        _outcome("b", 0.85, "ics", False, rolled=True, q=0.2),
        _outcome("c", 0.6, "ai_extracted", True, manual=True),
    ]
    fb = collect_feedback(outcomes, stale_providers=2)
    assert fb.sample == 3 and fb.manual_overrides == 1 and fb.stale_providers == 2
    assert 0 <= fb.sandbox_accuracy <= 1 and 0 <= fb.confidence_accuracy <= 1
    assert fb.approval_accuracy == round(2 / 3, 4)  # 2 of 3 survived


def test_learning_calibration_detects_overconfidence():
    # a high-confidence bucket that all rolled back → over-confident, negative delta
    outcomes = [
        _outcome("a", 0.9, "rss", False, rolled=True),
        _outcome("b", 0.88, "rss", False, rolled=True),
        _outcome("c", 0.5, "ai_extracted", True),
    ]
    report = learn(outcomes)
    assert report.sample == 3 and report.calibration_error > 0
    top = [b for b in report.buckets if b.lower >= 0.85][0]
    assert top.delta < 0  # predicted high, observed 0 → over-confident
    assert report.model.adjustments["rss"] < 0  # nudge rss confidence down

    # apply_calibration is a pure clamp-nudge a future onboarding could consume
    adjusted = apply_calibration(0.9, "rss", report.model)
    assert adjusted < 0.9


def test_apply_calibration_uses_global_when_feed_unknown():
    outcomes = [_outcome("a", 0.9, "rss", True), _outcome("b", 0.9, "rss", True)]
    model = learn(outcomes).model
    # unknown feed type → global delta (here positive: predicted 0.9, observed 1.0)
    assert apply_calibration(0.5, "unheard_of", model) >= 0.5


# --------------------------- analytics ---------------------------


def test_analytics_rates():
    engine, state, _ = ops(scenarios={provider_id_for("bad.org"): FAILING}, default=HEALTHY)
    run(engine.promote(plan(domain="good1.dev")))
    run(engine.promote(plan(domain="good2.dev")))
    run(engine.promote(plan(domain="bad.org")))
    run(engine.promote(plan(domain="x.com", ptype="manual")))  # fails preflight
    a = engine.analytics()
    assert (
        a.total_promotions == 4 and a.active == 2 and a.rolled_back == 1 and a.failed_preflight == 1
    )
    assert a.canary_success_rate == round(2 / 3, 4)  # 2 active of 3 that ran canary
    assert a.rollback_rate == round(1 / 3, 4)
    assert a.discovery_precision == round(2 / 4, 4)
    run(state.close())


# --------------------------- end-to-end + persistence ---------------------------


def test_end_to_end_lifecycle_and_persistence():
    engine, state, store = ops(scenarios={provider_id_for("bad.org"): FAILING}, default=HEALTHY)
    run(engine.promote(plan(domain="gdg.dev"), prediction={"confidence": 0.9, "was_manual": False}))
    run(engine.promote(plan(domain="bad.org"), prediction={"confidence": 0.8, "was_manual": True}))

    report = run(engine.learn())
    assert report.sample == 2
    # learning + calibration persisted to history (never deleted)
    assert len(run(store.history("learning"))) == 1
    assert len(run(store.history("calibration"))) == 1
    assert len(run(store.history("canary"))) == 2  # one canary per promotion
    assert len(run(store.history("rollback"))) == 1

    # registrations persisted with their terminal state
    active = run(store.list_registrations(state=ProductionState.ACTIVE))
    assert len(active) == 1 and active[0]["domain"] == "gdg.dev"
    fb = engine.feedback()
    assert fb.sample == 2 and fb.manual_overrides == 1
    run(state.close())
