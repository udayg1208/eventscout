"""Phase 9A — Continuous Autonomous Discovery Orchestrator tests. NO network; every stage mocked."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.orchestrator import (
    Budget,
    BudgetKind,
    BudgetPool,
    DeadLetterEntry,
    InMemoryOrchestratorStore,
    LeaseError,
    LeaseManager,
    MetricsEngine,
    OrchestratorEngine,
    Pipeline,
    Planner,
    RecoveryManager,
    RunStatus,
    Schedule,
    ScheduleKind,
    Scheduler,
    SQLiteOrchestratorStore,
    StageContext,
    StageExecutor,
    StageHealth,
    StageName,
    StageOutcome,
    StageSpec,
    StateManager,
    Trigger,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
S = StageName


def run(coro):
    return asyncio.run(coro)


class Clock:
    def __init__(self, t: datetime = NOW) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += timedelta(seconds=seconds)


def mock_stage(**kw):
    """An async stage runner returning a fixed outcome."""
    seeds = kw.pop("seeds", None)
    spend = kw.pop("spend", None)

    async def runner(ctx: StageContext) -> StageOutcome:
        return StageOutcome(produced_seeds=list(seeds or []), budget_spent=dict(spend or {}), **kw)

    return runner


def failing_stage(msg="boom"):
    async def runner(ctx: StageContext) -> StageOutcome:
        raise RuntimeError(msg)

    return runner


def one_stage_pipeline(**schedule_kw) -> Pipeline:
    return Pipeline(
        [StageSpec(name=S.SEARCH_DISCOVERY, schedule=Schedule(**schedule_kw), trigger=Trigger.BOTH)]
    )


# --------------------------------------------------------------------------- budgets


def test_budget_spend_caps_at_limit():
    b = Budget(kind=BudgetKind.CRAWL, limit=10)
    assert b.spend(4) == 4
    assert b.spend(20) == 6  # only 6 left
    assert b.remaining() == 0
    assert not b.can_spend(1)


def test_budget_pool_fraction_left():
    pool = BudgetPool({BudgetKind.AI: Budget(kind=BudgetKind.AI, limit=100, consumed=75)})
    assert pool.remaining(BudgetKind.AI) == 25
    assert pool.fraction_left(BudgetKind.AI) == 0.25
    assert pool.fraction_left(BudgetKind.SEARCH) == 1.0  # absent → treated as full


# --------------------------------------------------------------------------- scheduler


def test_scheduler_first_run_is_due():
    sc = Scheduler()
    spec = StageSpec(name=S.SEARCH_DISCOVERY, schedule=Schedule(kind=ScheduleKind.HOURLY))
    from app.orchestrator import StageState

    assert sc.is_due(spec, StageState(name=S.SEARCH_DISCOVERY), NOW) is True


def test_scheduler_hourly_respects_interval():
    from app.orchestrator import StageState

    sc = Scheduler()
    spec = StageSpec(name=S.SEARCH_DISCOVERY, schedule=Schedule(kind=ScheduleKind.HOURLY))
    st = StageState(name=S.SEARCH_DISCOVERY, last_run=NOW, next_run=NOW + timedelta(hours=1))
    assert sc.is_due(spec, st, NOW + timedelta(minutes=30)) is False
    assert sc.is_due(spec, st, NOW + timedelta(hours=1)) is True


def test_scheduler_paused_and_cooldown_and_manual():
    from app.orchestrator import StageState

    sc = Scheduler()
    paused = StageSpec(name=S.INBOX, schedule=Schedule(paused=True))
    assert sc.is_due(paused, StageState(name=S.INBOX), NOW) is False

    cool = StageSpec(name=S.INBOX, schedule=Schedule(kind=ScheduleKind.CONTINUOUS))
    st = StageState(name=S.INBOX, cooldown_until=NOW + timedelta(minutes=5))
    assert sc.is_due(cool, st, NOW) is False
    assert sc.is_due(cool, st, NOW + timedelta(minutes=6)) is True

    manual = StageSpec(name=S.INBOX, schedule=Schedule(kind=ScheduleKind.MANUAL))
    assert sc.is_due(manual, StageState(name=S.INBOX, last_run=NOW, next_run=NOW), NOW) is False


def test_scheduler_retry_backoff_and_exhaustion():
    from app.orchestrator import StageState

    sc = Scheduler()
    spec = StageSpec(
        name=S.SEARCH_DISCOVERY, schedule=Schedule(retry_max=2, retry_backoff_seconds=10)
    )
    st = StageState(name=S.SEARCH_DISCOVERY, status=RunStatus.FAILED, retry_count=1)
    st.next_run = sc.next_run_at(spec, st, NOW)
    assert st.next_run == NOW + timedelta(seconds=10)  # backoff * 2**0
    assert sc.is_due(spec, st, NOW + timedelta(seconds=9)) is False
    assert sc.is_due(spec, st, NOW + timedelta(seconds=10)) is True
    st.retry_count = 2  # exhausted
    assert sc.is_due(spec, st, NOW + timedelta(hours=1)) is False


def test_scheduler_next_run_cadences():
    from app.orchestrator import StageState

    sc = Scheduler()
    st = StageState(name=S.SEARCH_DISCOVERY, status=RunStatus.SUCCESS)
    daily = StageSpec(name=S.CATALOG_REFRESH, schedule=Schedule(kind=ScheduleKind.DAILY))
    weekly = StageSpec(name=S.OPTIMIZATION, schedule=Schedule(kind=ScheduleKind.WEEKLY))
    assert sc.next_run_at(daily, st, NOW) == NOW + timedelta(days=1)
    assert sc.next_run_at(weekly, st, NOW) == NOW + timedelta(weeks=1)


# --------------------------------------------------------------------------- planner


def _sm(pipeline: Pipeline, budgets=None) -> StateManager:
    return StateManager(pipeline, budgets=budgets or {k: 1000 for k in BudgetKind})


def test_planner_picks_highest_priority_due():
    pipe = Pipeline()
    sm = _sm(pipe)
    plan = Planner(pipe).plan(sm.state, NOW)
    assert plan is not None
    assert plan.stage is S.SEARCH_DISCOVERY  # priority 9, schedule-due on first run


def test_planner_backlog_makes_backlog_stage_eligible():
    pipe = Pipeline()
    sm = _sm(pipe)
    # expansion is BACKLOG-triggered → ineligible until it has backlog
    assert not Planner(pipe).eligible(pipe.spec(S.EXPANSION), sm.state.stage(S.EXPANSION), NOW)
    sm.enqueue_seeds(S.EXPANSION, ["https://x.com"])
    assert Planner(pipe).eligible(pipe.spec(S.EXPANSION), sm.state.stage(S.EXPANSION), NOW)


def test_planner_none_when_nothing_eligible():
    pipe = Pipeline(
        [StageSpec(name=S.EXPANSION, trigger=Trigger.BACKLOG)]
    )  # no backlog, no schedule
    sm = _sm(pipe)
    assert Planner(pipe).plan(sm.state, NOW) is None


def test_planner_skips_unaffordable_stage():
    pipe = one_stage_pipeline()
    pipe.spec(S.SEARCH_DISCOVERY).budgets = {BudgetKind.SEARCH: 5}
    sm = _sm(pipe, budgets={BudgetKind.SEARCH: 0})  # exhausted
    assert Planner(pipe).plan(sm.state, NOW) is None


def test_planner_grant_shrinks_when_budget_low():
    pipe = one_stage_pipeline()
    spec = pipe.spec(S.SEARCH_DISCOVERY)
    spec.budgets = {BudgetKind.SEARCH: 100}
    sm = _sm(pipe, budgets={BudgetKind.SEARCH: 100})
    sm.state.budget.spend(BudgetKind.SEARCH, 80)  # 20% left → throttle
    plan = Planner(pipe).plan(sm.state, NOW)
    assert plan is not None
    assert plan.context.budgets[BudgetKind.SEARCH] <= 20  # capped by remaining
    assert plan.context.budgets[BudgetKind.SEARCH] <= 50  # and by the <25% throttle (ceil(100*.5))


# --------------------------------------------------------------------------- state manager


def test_apply_success_fans_out_and_totals():
    pipe = Pipeline()
    sm = _sm(pipe)
    out = StageOutcome(discovered=5, produced_seeds=["https://a.com", "https://b.com"])
    sm.apply_outcome(S.SEARCH_DISCOVERY, out, now=NOW, duration_s=0.2)
    st = sm.state.stage(S.SEARCH_DISCOVERY)
    assert st.status is RunStatus.SUCCESS
    assert st.total_discovered == 5
    # downstream (web, expansion) received backlog + seeds
    assert sm.state.stage(S.WEB_DISCOVERY).backlog == 1
    assert "https://a.com" in sm.state.stage(S.EXPANSION).seeds


def test_apply_failure_increments_retry_and_records_error():
    pipe = Pipeline()
    sm = _sm(pipe)
    out = StageOutcome(health=StageHealth.FAILED, error="kaboom")
    sm.apply_outcome(S.SEARCH_DISCOVERY, out, now=NOW, duration_s=0.1)
    st = sm.state.stage(S.SEARCH_DISCOVERY)
    assert st.status is RunStatus.FAILED
    assert st.retry_count == 1
    assert st.errors[-1] == "kaboom"


def test_apply_spends_budget():
    pipe = Pipeline()
    sm = _sm(pipe, budgets={BudgetKind.SEARCH: 100})
    sm.apply_outcome(
        S.SEARCH_DISCOVERY,
        StageOutcome(discovered=1, budget_spent={BudgetKind.SEARCH: 30}),
        now=NOW,
        duration_s=0.1,
    )
    assert sm.state.budget.remaining(BudgetKind.SEARCH) == 70


def test_provider_stats_track_totals():
    pipe = Pipeline()
    sm = _sm(pipe)
    sm.apply_outcome(S.ONBOARDING, StageOutcome(discovered=3, promoted=2), now=NOW, duration_s=0.1)
    assert sm.state.provider_stats["promoted"] == 2
    assert sm.state.provider_stats["active"] == 2


# --------------------------------------------------------------------------- executor / leases


def test_lease_acquire_conflict_and_steal():
    lm = LeaseManager(ttl_seconds=30)
    lm.acquire(S.INBOX, "A", NOW)
    assert lm.held(S.INBOX, NOW)
    try:
        lm.acquire(S.INBOX, "B", NOW)
        raised = False
    except LeaseError:
        raised = True
    assert raised
    # once expired, a new owner may steal it
    stolen = lm.acquire(S.INBOX, "B", NOW + timedelta(seconds=31))
    assert stolen.owner == "B"


def test_lease_release_and_reap():
    lm = LeaseManager(ttl_seconds=10)
    lease = lm.acquire(S.INBOX, "A", NOW)
    lm.release(lease)
    assert not lm.held(S.INBOX, NOW)
    lm.acquire(S.EXPANSION, "A", NOW)
    reaped = lm.reap_expired(NOW + timedelta(seconds=11))
    assert S.EXPANSION in reaped


def test_executor_runs_stage():
    ex = StageExecutor(clock=lambda: NOW)
    ctx = StageContext(stage=S.INBOX, cycle=1, now=NOW)
    outcome, dur = run(ex.execute(mock_stage(discovered=7), ctx))
    assert outcome.discovered == 7
    assert dur >= 0.0


def test_executor_exception_becomes_failed():
    ex = StageExecutor(clock=lambda: NOW)
    ctx = StageContext(stage=S.INBOX, cycle=1, now=NOW)
    outcome, _ = run(ex.execute(failing_stage("nope"), ctx))
    assert outcome.health is StageHealth.FAILED
    assert "nope" in outcome.error


def test_executor_timeout_becomes_failed():
    async def slow(ctx):
        await asyncio.sleep(1.0)
        return StageOutcome()

    ex = StageExecutor(clock=lambda: NOW)
    ctx = StageContext(stage=S.INBOX, cycle=1, now=NOW)
    outcome, _ = run(ex.execute(slow, ctx, timeout_seconds=0.01))
    assert outcome.health is StageHealth.FAILED
    assert "timeout" in outcome.error


def test_lock_prevents_double_execution():
    """A stage held by another owner is not run twice — the executor declines (degraded)."""
    lm = LeaseManager(ttl_seconds=60)
    lm.acquire(S.INBOX, "other-worker", NOW)  # someone else holds it
    ran = {"called": False}

    async def runner(ctx):
        ran["called"] = True
        return StageOutcome(discovered=1)

    ex = StageExecutor(lm, owner="me", clock=lambda: NOW)
    outcome, _ = run(ex.execute(runner, StageContext(stage=S.INBOX, cycle=1, now=NOW)))
    assert ran["called"] is False  # never ran concurrently
    assert outcome.health is StageHealth.DEGRADED


# --------------------------------------------------------------------------- metrics


def test_metrics_rates_from_elapsed():
    clk = Clock()
    m = MetricsEngine(clock=clk)
    m.start(NOW)
    m.observe_stage(S.SEARCH_DISCOVERY, StageOutcome(discovered=10, pages=20, duplicates=2), 0.5)
    m.observe_cycle()
    snap = m.snapshot(NOW + timedelta(hours=1))
    assert snap.events_discovered == 10
    assert snap.events_per_hour == 10.0
    assert snap.crawl_efficiency == 0.5  # 10 discovered / 20 pages
    assert round(snap.duplicate_rate, 4) == round(2 / 12, 4)
    assert snap.throughput_per_cycle == 1.0


def test_metrics_precision_recall_from_feedback():
    m = MetricsEngine(clock=lambda: NOW)
    m.start(NOW)
    m.record_feedback(true_positives=8, false_positives=2, false_negatives=4)
    snap = m.snapshot(NOW)
    assert snap.precision == 0.8  # 8/(8+2)
    assert round(snap.recall, 4) == round(8 / 12, 4)
    assert snap.false_positives == 2


# --------------------------------------------------------------------------- recovery


def test_dead_letter_queue_add_list_requeue():
    pipe = Pipeline()
    sm = _sm(pipe)
    from app.orchestrator import DeadLetterQueue

    dlq = DeadLetterQueue(sm.state)
    dlq.add(DeadLetterEntry(stage=S.EXPANSION, cycle=3, attempts=3, error="x", created_at=NOW))
    assert dlq.size() == 1
    removed = dlq.requeue(S.EXPANSION)
    assert len(removed) == 1 and dlq.size() == 0


def test_recovery_should_dead_letter_and_crash_replay():
    pipe = Pipeline()
    rm = RecoveryManager(pipe)
    assert rm.should_dead_letter(3, 3) is True
    assert rm.should_dead_letter(1, 3) is False
    sm = _sm(pipe)
    sm.state.stage(S.EXPANSION).status = RunStatus.RUNNING
    assert S.EXPANSION in rm.crash_replay_stages(sm.state)


# --------------------------------------------------------------------------- store


def test_inmemory_store_state_and_checkpoint():
    pipe = Pipeline()
    sm = _sm(pipe)
    store = InMemoryOrchestratorStore()
    rm = RecoveryManager(pipe)
    run(store.save_state(sm.state))
    run(store.save_checkpoint(rm.make_checkpoint(sm.state, S.SEARCH_DISCOVERY, NOW)))
    assert run(store.load_state()) is sm.state
    assert run(store.latest_checkpoint()).stage is S.SEARCH_DISCOVERY


def test_sqlite_store_roundtrips_typed_state():
    pipe = Pipeline()
    sm = _sm(pipe, budgets={BudgetKind.SEARCH: 100})
    sm.apply_outcome(
        S.SEARCH_DISCOVERY,
        StageOutcome(discovered=4, budget_spent={BudgetKind.SEARCH: 25}),
        now=NOW,
        duration_s=0.3,
    )
    store = SQLiteOrchestratorStore(":memory:")
    try:
        run(store.save_state(sm.state))
        loaded = run(store.load_state())
        assert loaded is not None
        assert loaded.stage(S.SEARCH_DISCOVERY).status is RunStatus.SUCCESS
        assert loaded.stage(S.SEARCH_DISCOVERY).total_discovered == 4
        assert loaded.budget.remaining(BudgetKind.SEARCH) == 75
        assert loaded.stage(S.WEB_DISCOVERY).backlog == 1  # fan-out survived the round-trip
    finally:
        run(store.close())


# --------------------------------------------------------------------------- engine integration


def _full_engine(**kw):
    budgets = {k: 10_000 for k in BudgetKind}
    eng = OrchestratorEngine(budgets=budgets, clock=lambda: NOW, **kw)
    eng.register(S.SEARCH_DISCOVERY, mock_stage(discovered=5, seeds=["https://a.com"]))
    eng.register(S.WEB_DISCOVERY, mock_stage(discovered=3, pages=10, seeds=["https://b.com"]))
    eng.register(S.EXPANSION, mock_stage(discovered=4, pages=20, seeds=["https://c.com"]))
    eng.register(S.SOCIAL_DISCOVERY, mock_stage(discovered=2))
    eng.register(S.RENDERED_DISCOVERY, mock_stage(discovered=6, ai_calls=2))
    eng.register(S.INBOX, mock_stage(discovered=8))
    eng.register(S.ONBOARDING, mock_stage(discovered=2, promoted=2))
    eng.register(S.PRODUCTION_OPS, mock_stage(promoted=2))
    eng.register(S.CATALOG_REFRESH, mock_stage())
    eng.register(S.OPTIMIZATION, mock_stage(ai_calls=1))
    return eng


def test_engine_run_once_executes_one_stage():
    eng = _full_engine()
    eng._sm.start(NOW)
    cr = run(eng.run_once())
    assert cr.stage is S.SEARCH_DISCOVERY
    assert cr.status is RunStatus.SUCCESS


def test_engine_bounded_run_sequences_pipeline():
    eng = _full_engine()
    report = run(eng.run(max_cycles=12))
    # the canonical front of the pipeline all executed at least once
    for stage in (S.SEARCH_DISCOVERY, S.WEB_DISCOVERY, S.EXPANSION, S.INBOX):
        assert report.stages_run.get(stage.value, 0) >= 1
    assert report.metrics.events_discovered > 0
    # search ran before inbox (data-driven order emerges from priority + fan-out)
    order = [c.stage for c in report.per_cycle if c.stage]
    assert order.index(S.SEARCH_DISCOVERY) < order.index(S.INBOX)


def test_engine_retry_then_dead_letter():
    clk = Clock()
    pipe = one_stage_pipeline(retry_max=2, retry_backoff_seconds=10)
    eng = OrchestratorEngine(pipe, {S.SEARCH_DISCOVERY: failing_stage()}, clock=clk)
    eng._sm.start(clk())
    statuses = []
    for _ in range(4):
        cr = run(eng.run_once())
        statuses.append(cr.status)
        clk.advance(10_000)  # jump past any backoff so the retry becomes due
    assert statuses[0] is RunStatus.FAILED
    assert RunStatus.DEAD_LETTER in statuses
    assert eng.dead_letter.size() == 1
    # once dead-lettered the stage is skipped, so the loop goes idle
    assert eng.state.stage(S.SEARCH_DISCOVERY).status is RunStatus.DEAD_LETTER


def test_engine_crash_recovery_via_resume():
    pipe = one_stage_pipeline()
    store = SQLiteOrchestratorStore(":memory:")
    try:
        # engine A "crashes" mid-run: the stage is left RUNNING and persisted
        eng_a = OrchestratorEngine(
            pipe, {S.SEARCH_DISCOVERY: mock_stage(discovered=1)}, store=store, clock=lambda: NOW
        )
        eng_a._sm.mark_running(S.SEARCH_DISCOVERY)
        run(store.save_state(eng_a.state))

        # engine B resumes from the store and re-queues the interrupted stage
        eng_b = OrchestratorEngine(
            pipe, {S.SEARCH_DISCOVERY: mock_stage(discovered=1)}, store=store, clock=lambda: NOW
        )
        resumed = run(eng_b.resume_from_store())
        assert resumed is True
        assert eng_b.state.stage(S.SEARCH_DISCOVERY).status is RunStatus.PENDING
        eng_b._sm.start(NOW)
        cr = run(eng_b.run_once())
        assert cr.stage is S.SEARCH_DISCOVERY and cr.status is RunStatus.SUCCESS
    finally:
        run(store.close())


def test_engine_checkpoints_each_cycle():
    store = InMemoryOrchestratorStore()
    eng = _full_engine(store=store)
    run(eng.run(max_cycles=3))
    assert run(store.checkpoint_count()) == 3
    assert run(store.load_state()) is not None


def test_engine_budget_exhaustion_defers_stage():
    # a single expensive stage with no budget left is never planned
    pipe = one_stage_pipeline(kind=ScheduleKind.CONTINUOUS)
    pipe.spec(S.SEARCH_DISCOVERY).budgets = {BudgetKind.SEARCH: 5}
    eng = OrchestratorEngine(
        pipe,
        {S.SEARCH_DISCOVERY: mock_stage(discovered=1)},
        budgets={BudgetKind.SEARCH: 0},
        clock=lambda: NOW,
    )
    eng._sm.start(NOW)
    cr = run(eng.run_once())
    assert cr.status is RunStatus.SKIPPED  # nothing affordable → idle


def test_engine_pause_and_resume_stage():
    eng = _full_engine()
    eng.pause(S.SEARCH_DISCOVERY)
    eng._sm.start(NOW)
    cr = run(eng.run_once())
    assert cr.stage is not S.SEARCH_DISCOVERY  # paused → skipped in favour of another stage
    eng.resume_stage(S.SEARCH_DISCOVERY)
    assert eng.state.stage(S.SEARCH_DISCOVERY).paused is False


def test_engine_stop_when_idle():
    pipe = Pipeline([StageSpec(name=S.EXPANSION, trigger=Trigger.BACKLOG)])  # nothing ever due
    eng = OrchestratorEngine(pipe, {S.EXPANSION: mock_stage()}, clock=lambda: NOW)
    report = run(eng.run(max_cycles=5, stop_when_idle=True))
    assert report.cycles == 1  # first cycle is idle → stop immediately
    assert report.per_cycle[0].status is RunStatus.SKIPPED


def test_engine_optimize_recommendations():
    eng = _full_engine()
    run(eng.run(max_cycles=10))
    recs = eng.optimize_recommendations()
    assert isinstance(recs, list)  # recommend-only, non-mutating
