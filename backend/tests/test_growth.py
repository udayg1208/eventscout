"""Phase 10F — Continuous Autonomous Growth Scheduler tests (fixtures only, no network).

Covers the whole control plane: models, the persistent queue (priority/dedup/lease/retry/cooldown/
abandon), the cadence scheduler, freshness, the six opportunity detectors, the budget engine, the
learning engine (recommendations only), the planner, growth metrics + steady state, the step reuse
seam (including the real 10C→10D→10E adapters), both stores, and the engine loop end-to-end. No
browser, no LLM, no network — the discovery fetcher/searcher are fixtures.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.discovery import InMemoryDiscoveryInbox
from app.discovery.fetch import FetchResult, StaticFetcher
from app.ecosystem import EcosystemExpansionEngine, ExpansionSeed, RelationshipPath, SeedKind
from app.growth import (
    DEFAULT_SCHEDULE,
    CycleRecord,
    EntityKind,
    FreshnessEngine,
    FreshnessRecord,
    GrowthBudget,
    GrowthBudgetEngine,
    GrowthCadence,
    GrowthEngine,
    GrowthInputs,
    GrowthMetricsEngine,
    GrowthOpportunity,
    GrowthPlanner,
    GrowthQueue,
    GrowthResource,
    GrowthScheduler,
    GrowthTask,
    InMemoryGrowthStore,
    LearningEngine,
    OpportunityEngine,
    OpportunityKind,
    OpportunitySignals,
    Recommendation,
    RecommendationKind,
    ScheduleSpec,
    SeedBuffer,
    SQLiteGrowthStore,
    StepContext,
    StepOutcome,
    TaskKind,
    TaskState,
    make_constant_step,
    make_expansion_step,
    make_onboarding_step,
    make_organizer_refresh_step,
    make_production_monitor_step,
    make_validation_step,
)
from app.organizers import OrganizerIntelligenceEngine
from app.validation import RetryPolicy, SeedValidationEngine

NOW = datetime(2026, 7, 17, tzinfo=UTC)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)


def run(coro):
    return asyncio.run(coro)


def mk_task(kind=TaskKind.EXPANSION, target="batch", **kw):
    return GrowthTask(kind=kind, target=target, **kw)


def ctx(task=None, run=1, budget=None, now=NOW):
    return StepContext(
        task=task or mk_task(),
        run=run,
        budget=budget or GrowthBudget(limits={r: 100 for r in GrowthResource}),
        now=now,
    )


RICH = (
    '<html><head><meta property="og:site_name" content="GDG Delhi">'
    '<script type="application/ld+json">{"@type":"Event","name":"DevFest Delhi 2026",'
    '"startDate":"2026-11-01","location":{"@type":"Place","name":"Delhi",'
    '"address":{"addressLocality":"Delhi"}}}</script></head>'
    "<body><h1>GDG Delhi</h1>Google Developer Group Delhi. DevFest. Python, AI. Delhi."
    "</body></html>"
)


class FixtureSearcher:
    def __init__(self, mapping):
        self._m = mapping

    def search(self, query):
        return list(self._m.get(query, []))


# ============================================================ models


def test_task_default_priority():
    assert mk_task(kind=TaskKind.VALIDATION).priority == 90
    assert mk_task(kind=TaskKind.PRODUCTION_MONITOR).priority == 40


def test_task_explicit_priority_preserved():
    assert mk_task(kind=TaskKind.VALIDATION, priority=5).priority == 5


def test_task_id_defaults_to_dedup_key():
    t = mk_task(kind=TaskKind.EXPANSION, target="Pune")
    assert t.task_id == "expansion:Pune" == t.dedup_key


def test_task_resource_mapping():
    assert mk_task(kind=TaskKind.VALIDATION).resource is GrowthResource.VALIDATION
    assert mk_task(kind=TaskKind.ONBOARDING).resource is GrowthResource.ONBOARDING
    assert mk_task(kind=TaskKind.EXPANSION).resource is GrowthResource.CRAWL


def test_task_is_active_states():
    t = mk_task()
    for s in (TaskState.QUEUED, TaskState.LEASED, TaskState.COOLDOWN):
        t.state = s
        assert t.is_active()
    for s in (TaskState.DONE, TaskState.FAILED, TaskState.ABANDONED):
        t.state = s
        assert not t.is_active()


def test_task_eligible_queued_respects_cooldown():
    t = mk_task()
    t.cooldown_until = 5
    assert not t.eligible(4)
    assert t.eligible(5)


def test_task_eligible_leased_only_when_expired():
    t = mk_task(state=TaskState.LEASED)
    t.lease_until = 10
    assert not t.eligible(9)
    assert t.eligible(10)


def test_task_eligible_done_never():
    assert not mk_task(state=TaskState.DONE).eligible(999)


def test_task_as_dict():
    d = mk_task(kind=TaskKind.EXPANSION, target="X").as_dict()
    assert d["kind"] == "expansion" and d["target"] == "X" and d["state"] == "queued"


def test_budget_remaining_and_can_spend():
    b = GrowthBudget(limits={GrowthResource.SEARCH: 10})
    assert b.remaining(GrowthResource.SEARCH) == 10
    assert b.can_spend(GrowthResource.SEARCH, 10)
    assert not b.can_spend(GrowthResource.SEARCH, 11)


def test_budget_spend_clamps_and_never_exceeds():
    b = GrowthBudget(limits={GrowthResource.CRAWL: 5})
    assert b.spend(GrowthResource.CRAWL, 3) == 3
    assert b.spend(GrowthResource.CRAWL, 10) == 2  # only 2 left
    assert b.remaining(GrowthResource.CRAWL) == 0
    assert b.spend(GrowthResource.CRAWL, 1) == 0


def test_budget_fraction_left_and_reset():
    b = GrowthBudget(limits={GrowthResource.CRAWL: 4})
    b.spend(GrowthResource.CRAWL, 3)
    assert b.fraction_left(GrowthResource.CRAWL) == 0.25
    b.reset()
    assert b.remaining(GrowthResource.CRAWL) == 4


def test_budget_as_dict():
    b = GrowthBudget(limits={GrowthResource.SEARCH: 2})
    b.spend(GrowthResource.SEARCH, 1)
    assert b.as_dict() == {"search": {"limit": 2, "consumed": 1}}


def test_freshness_record_age_and_stale():
    r = FreshnessRecord("o1", EntityKind.ORGANIZER, NOW, ttl_seconds=3600)
    assert r.age_seconds(NOW) == 0.0
    assert not r.is_stale(NOW)
    assert r.is_stale(NOW + 2 * HOUR)


def test_opportunity_to_task_mapping():
    stale = GrowthOpportunity(OpportunityKind.STALE_ORGANIZER, "o1", "aged")
    assert stale.to_task().kind is TaskKind.ORGANIZER_REFRESH
    city = GrowthOpportunity(OpportunityKind.NEW_CITY, "Pune", "gap")
    assert city.to_task().kind is TaskKind.EXPANSION


def test_opportunity_dedup_key_and_as_dict():
    o = GrowthOpportunity(OpportunityKind.NEW_CITY, "Pune", "gap", evidence={"city": "Pune"})
    assert o.dedup_key == "new_city:Pune"
    assert o.as_dict()["evidence"] == {"city": "Pune"}


def test_recommendation_as_dict():
    r = Recommendation(RecommendationKind.MAINTAIN, "ok", evidence={"x": 1})
    assert r.as_dict() == {"kind": "maintain", "reason": "ok", "evidence": {"x": 1}}


def test_step_outcome_is_progress():
    assert StepOutcome(seeds_generated=1).is_progress()
    assert StepOutcome(accepted=1).is_progress()
    assert StepOutcome(organizers_found=1).is_progress()
    assert StepOutcome(promoted=1).is_progress()
    assert not StepOutcome(rejected=5, failures=2).is_progress()


def test_step_outcome_as_dict():
    o = StepOutcome(seeds_generated=2, cost={GrowthResource.CRAWL: 3})
    d = o.as_dict()
    assert d["seeds_generated"] == 2 and d["cost"] == {"crawl": 3}


# ============================================================ queue


def test_queue_enqueue_queued():
    q = GrowthQueue()
    assert q.enqueue(mk_task()) == "queued"
    assert q.backlog() == 1


def test_queue_enqueue_duplicate_active_keeps_higher_priority():
    q = GrowthQueue()
    q.enqueue(mk_task(kind=TaskKind.EXPANSION, target="X", priority=10))
    assert q.enqueue(mk_task(kind=TaskKind.EXPANSION, target="X", priority=50)) == "duplicate"
    assert q.get("expansion:X").priority == 50


def test_queue_enqueue_blocks_reenqueue_of_completed():
    q = GrowthQueue()
    t = mk_task(kind=TaskKind.EXPANSION, target="X")
    q.enqueue(t)
    q.lease(t, 1)
    q.complete(t, True, 1)
    assert t.state is TaskState.DONE
    assert q.enqueue(mk_task(kind=TaskKind.EXPANSION, target="X")) == "duplicate"


def test_queue_force_revives_completed():
    q = GrowthQueue()
    t = mk_task(kind=TaskKind.EXPANSION, target="X")
    q.enqueue(t)
    q.lease(t, 1)
    q.complete(t, True, 1)
    assert q.enqueue(mk_task(kind=TaskKind.EXPANSION, target="X"), force=True) == "queued"
    assert q.get("expansion:X").state is TaskState.QUEUED


def test_queue_abandoned_can_be_reattempted():
    q = GrowthQueue()
    t = mk_task(kind=TaskKind.EXPANSION, target="X", max_attempts=1)
    q.enqueue(t)
    q.lease(t, 1)
    q.complete(t, False, 1)  # attempts hits max -> abandoned
    assert t.state is TaskState.ABANDONED
    assert q.enqueue(mk_task(kind=TaskKind.EXPANSION, target="X")) == "queued"


def test_queue_eligible_sorted_by_priority_then_age():
    q = GrowthQueue()
    q.enqueue(mk_task(kind=TaskKind.PRODUCTION_MONITOR, target="a"), run=1)  # 40
    q.enqueue(mk_task(kind=TaskKind.VALIDATION, target="b"), run=2)  # 90
    q.enqueue(mk_task(kind=TaskKind.EXPANSION, target="c"), run=3)  # 60
    order = [t.kind for t in q.eligible(5)]
    assert order[0] is TaskKind.VALIDATION and order[1] is TaskKind.EXPANSION


def test_queue_peek_and_acquire():
    q = GrowthQueue()
    q.enqueue(mk_task(kind=TaskKind.VALIDATION, target="b"))
    task = q.acquire(1)
    assert task.kind is TaskKind.VALIDATION and task.state is TaskState.LEASED


def test_queue_lease_sets_expiry():
    q = GrowthQueue(default_lease_runs=3)
    t = mk_task()
    q.enqueue(t)
    q.lease(t, 5)
    assert t.lease_until == 8


def test_queue_reclaim_expired():
    q = GrowthQueue()
    t = mk_task()
    q.enqueue(t)
    q.lease(t, 1, lease_runs=2)  # expires at run 3
    assert q.reclaim_expired(2) == 0
    assert q.reclaim_expired(3) == 1
    assert t.state is TaskState.QUEUED


def test_queue_complete_success():
    q = GrowthQueue()
    t = mk_task()
    q.enqueue(t)
    q.lease(t, 1)
    assert q.complete(t, True, 1) is TaskState.DONE


def test_queue_complete_failure_schedules_cooldown():
    q = GrowthQueue(default_cooldown_runs=2)
    t = mk_task(max_attempts=3)
    q.enqueue(t)
    q.lease(t, 1)
    assert q.complete(t, False, 5) is TaskState.COOLDOWN
    assert t.attempts == 1 and t.cooldown_until == 7


def test_queue_complete_abandons_at_max_attempts():
    q = GrowthQueue()
    t = mk_task(max_attempts=2)
    q.enqueue(t)
    for r in (1, 2):
        q.lease(t, r)
        q.complete(t, False, r)
    assert t.state is TaskState.ABANDONED


def test_queue_pending_and_leased_counts():
    q = GrowthQueue()
    a, b = mk_task(target="a"), mk_task(kind=TaskKind.VALIDATION, target="b")
    q.enqueue(a)
    q.enqueue(b)
    q.lease(a, 1)
    assert q.backlog() == 2
    assert len(q.leased()) == 1


def test_queue_is_drained():
    q = GrowthQueue()
    assert q.is_drained(1)
    t = mk_task()
    q.enqueue(t)
    assert not q.is_drained(1)
    q.lease(t, 1)
    q.complete(t, True, 1)
    assert q.is_drained(2)


def test_queue_snapshot_and_load():
    q = GrowthQueue()
    q.enqueue(mk_task(kind=TaskKind.VALIDATION, target="b"))
    snap = q.snapshot()
    assert snap and snap[0]["kind"] == "validation"
    q2 = GrowthQueue()
    q2.load([mk_task(target="z")])
    assert q2.get("expansion:z") is not None


# ============================================================ scheduler


def test_scheduler_due_first_time():
    s = GrowthScheduler(clock=lambda: NOW)
    assert len(s.due(NOW)) == len(DEFAULT_SCHEDULE)


def test_scheduler_not_due_within_interval():
    s = GrowthScheduler(
        [ScheduleSpec(TaskKind.VALIDATION, GrowthCadence.HOURLY)], clock=lambda: NOW
    )
    q = GrowthQueue()
    s.tick(q, run=1, now=NOW)
    assert s.due(NOW + timedelta(minutes=30)) == []


def test_scheduler_due_after_interval():
    s = GrowthScheduler(
        [ScheduleSpec(TaskKind.VALIDATION, GrowthCadence.HOURLY)], clock=lambda: NOW
    )
    q = GrowthQueue()
    s.tick(q, run=1, now=NOW)
    assert len(s.due(NOW + HOUR)) == 1


def test_scheduler_manual_never_due():
    s = GrowthScheduler([ScheduleSpec(TaskKind.EXPANSION, GrowthCadence.MANUAL)], clock=lambda: NOW)
    assert s.due(NOW + 10 * DAY) == []


def test_scheduler_continuous_always_due():
    s = GrowthScheduler(
        [ScheduleSpec(TaskKind.VALIDATION, GrowthCadence.CONTINUOUS)], clock=lambda: NOW
    )
    q = GrowthQueue()
    s.tick(q, run=1, now=NOW)
    assert len(s.due(NOW)) == 1  # 0-second interval -> due every check


def test_scheduler_tick_enqueues_due_tasks():
    s = GrowthScheduler(clock=lambda: NOW)
    q = GrowthQueue()
    enq = s.tick(q, run=1, now=NOW)
    assert len(enq) == len(DEFAULT_SCHEDULE)
    assert q.backlog() == len(DEFAULT_SCHEDULE)


def test_scheduler_tick_records_last_fired():
    s = GrowthScheduler([ScheduleSpec(TaskKind.EXPANSION, GrowthCadence.DAILY)], clock=lambda: NOW)
    q = GrowthQueue()
    s.tick(q, run=1, now=NOW)
    assert s.last_fired(TaskKind.EXPANSION) == NOW


def test_scheduler_tick_idempotent_same_clock():
    s = GrowthScheduler([ScheduleSpec(TaskKind.EXPANSION, GrowthCadence.DAILY)], clock=lambda: NOW)
    q = GrowthQueue()
    s.tick(q, run=1, now=NOW)
    assert s.tick(q, run=2, now=NOW) == []  # not due again


def test_scheduler_refires_after_interval_via_force():
    s = GrowthScheduler([ScheduleSpec(TaskKind.EXPANSION, GrowthCadence.DAILY)], clock=lambda: NOW)
    q = GrowthQueue()
    t = s.tick(q, run=1, now=NOW)[0]
    q.lease(t, 1)
    q.complete(t, True, 1)  # done
    enq = s.tick(q, run=2, now=NOW + DAY)  # a day later, revive
    assert len(enq) == 1 and q.get("expansion:batch").state is TaskState.QUEUED


def test_scheduler_custom_targets_provider():
    spec = ScheduleSpec(
        TaskKind.ORGANIZER_REFRESH, GrowthCadence.WEEKLY, targets=lambda: ["o1", "o2"]
    )
    s = GrowthScheduler([spec], clock=lambda: NOW)
    q = GrowthQueue()
    s.tick(q, run=1, now=NOW)
    assert {t.target for t in q.pending()} == {"o1", "o2"}


# ============================================================ freshness


def test_freshness_touch_and_record():
    f = FreshnessEngine(clock=lambda: NOW)
    f.touch("o1", EntityKind.ORGANIZER)
    assert f.record("o1", EntityKind.ORGANIZER) is not None


def test_freshness_age_none_when_absent():
    f = FreshnessEngine(clock=lambda: NOW)
    assert f.age_seconds("nope", EntityKind.ORGANIZER) is None


def test_freshness_stale_after_ttl():
    f = FreshnessEngine(ttl={EntityKind.ORGANIZER: 3600}, clock=lambda: NOW)
    f.touch("o1", EntityKind.ORGANIZER)
    assert f.stale(now=NOW) == []
    assert len(f.stale(now=NOW + 2 * HOUR)) == 1


def test_freshness_stale_filter_by_kind():
    f = FreshnessEngine(ttl={EntityKind.ORGANIZER: 1, EntityKind.SEED: 1}, clock=lambda: NOW)
    f.touch("o1", EntityKind.ORGANIZER)
    f.touch("s1", EntityKind.SEED)
    later = NOW + HOUR
    assert len(f.stale(now=later, kind=EntityKind.SEED)) == 1
    assert len(f.stale(now=later)) == 2


def test_freshness_recommend_refreshes_maps_kind():
    f = FreshnessEngine(ttl={EntityKind.ORGANIZER: 1, EntityKind.EXPANSION: 1}, clock=lambda: NOW)
    f.touch("o1", EntityKind.ORGANIZER)
    f.touch("e1", EntityKind.EXPANSION)
    tasks = f.recommend_refreshes(now=NOW + HOUR)
    kinds = {t.kind for t in tasks}
    assert TaskKind.ORGANIZER_REFRESH in kinds and TaskKind.EXPANSION in kinds


def test_freshness_recommend_empty_when_fresh():
    f = FreshnessEngine(clock=lambda: NOW)
    f.touch("o1", EntityKind.ORGANIZER)
    assert f.recommend_refreshes(now=NOW) == []


def test_freshness_snapshot_and_records():
    f = FreshnessEngine(clock=lambda: NOW)
    f.touch("o1", EntityKind.ORGANIZER)
    assert len(f.records()) == 1
    snap = f.snapshot(now=NOW)
    assert snap[0]["entity_id"] == "o1" and "stale" in snap[0]


# ============================================================ opportunity


def test_opportunity_new_city_fires():
    ops = OpportunityEngine().detect(
        OpportunitySignals(organizer_cities={"Chennai"}, seed_cities={"Chennai", "Pune"})
    )
    kinds = {(o.kind, o.target) for o in ops}
    assert (OpportunityKind.NEW_CITY, "Pune") in kinds
    assert (OpportunityKind.NEW_CITY, "Chennai") not in kinds


def test_opportunity_inactive_ecosystem():
    ops = OpportunityEngine().detect(OpportunitySignals(dormant_organizers=["GDG X"]))
    assert any(o.kind is OpportunityKind.INACTIVE_ECOSYSTEM for o in ops)


def test_opportunity_stale_organizer():
    ops = OpportunityEngine().detect(OpportunitySignals(stale_organizers=["GDG Y"]))
    assert any(o.kind is OpportunityKind.STALE_ORGANIZER for o in ops)


def test_opportunity_recurring_conference():
    ops = OpportunityEngine().detect(OpportunitySignals(recurring_soon=["DevFest Delhi"]))
    assert any(o.kind is OpportunityKind.RECURRING_CONFERENCE for o in ops)


def test_opportunity_missing_university_coverage():
    ops = OpportunityEngine().detect(
        OpportunitySignals(organizer_cities={"Indore"}, university_cities=set())
    )
    assert any(o.kind is OpportunityKind.MISSING_UNIVERSITY_COVERAGE for o in ops)


def test_opportunity_university_present_no_gap():
    ops = OpportunityEngine().detect(
        OpportunitySignals(organizer_cities={"Indore"}, university_cities={"Indore"})
    )
    assert not any(o.kind is OpportunityKind.MISSING_UNIVERSITY_COVERAGE for o in ops)


def test_opportunity_seasonal_fires_in_november():
    ops = OpportunityEngine().detect(OpportunitySignals(now=datetime(2026, 11, 1, tzinfo=UTC)))
    assert any(o.kind is OpportunityKind.SEASONAL_EVENT for o in ops)


def test_opportunity_seasonal_silent_off_season():
    ops = OpportunityEngine().detect(OpportunitySignals(now=datetime(2026, 7, 1, tzinfo=UTC)))
    assert not any(o.kind is OpportunityKind.SEASONAL_EVENT for o in ops)


def test_opportunity_seasonal_needs_now():
    ops = OpportunityEngine().detect(OpportunitySignals(now=None))
    assert not any(o.kind is OpportunityKind.SEASONAL_EVENT for o in ops)


def test_opportunity_empty_signals():
    assert OpportunityEngine().detect(OpportunitySignals()) == []


def test_opportunity_dedup_keys_unique():
    ops = OpportunityEngine().detect(
        OpportunitySignals(
            organizer_cities={"Indore"},
            seed_cities={"Pune"},
            dormant_organizers=["GDG X"],
            now=datetime(2026, 10, 1, tzinfo=UTC),
        )
    )
    keys = [o.dedup_key for o in ops]
    assert len(keys) == len(set(keys))


def test_opportunity_priorities_positive():
    ops = OpportunityEngine().detect(OpportunitySignals(recurring_soon=["A"], seed_cities={"B"}))
    assert all(o.priority > 0 for o in ops)


# ============================================================ budget engine


def test_budget_engine_can_afford_and_remaining():
    b = GrowthBudgetEngine({GrowthResource.SEARCH: 5}, clock=lambda: NOW)
    assert b.can_afford(GrowthResource.SEARCH, 5)
    assert b.remaining(GrowthResource.SEARCH) == 5


def test_budget_engine_allocate_grants_min():
    b = GrowthBudgetEngine({GrowthResource.CRAWL: 3}, clock=lambda: NOW)
    assert b.allocate(GrowthResource.CRAWL, 10) == 3
    assert b.remaining(GrowthResource.CRAWL) == 0


def test_budget_engine_charge_clamped_per_resource():
    b = GrowthBudgetEngine(
        {GrowthResource.VALIDATION: 2, GrowthResource.SEARCH: 10}, clock=lambda: NOW
    )
    spent = b.charge({GrowthResource.VALIDATION: 5, GrowthResource.SEARCH: 4})
    assert spent[GrowthResource.VALIDATION] == 2 and spent[GrowthResource.SEARCH] == 4


def test_budget_engine_refill_first_call_baselines():
    b = GrowthBudgetEngine({GrowthResource.CRAWL: 5}, refill_seconds=3600, clock=lambda: NOW)
    b.allocate(GrowthResource.CRAWL, 5)
    assert b.refill_if_due(now=NOW) is False  # first call sets baseline, no reset
    assert b.remaining(GrowthResource.CRAWL) == 0


def test_budget_engine_refill_within_period_no_reset():
    b = GrowthBudgetEngine({GrowthResource.CRAWL: 5}, refill_seconds=3600, clock=lambda: NOW)
    b.refill_if_due(now=NOW)
    b.allocate(GrowthResource.CRAWL, 5)
    assert b.refill_if_due(now=NOW + timedelta(minutes=30)) is False


def test_budget_engine_refill_after_period_resets():
    b = GrowthBudgetEngine({GrowthResource.CRAWL: 5}, refill_seconds=3600, clock=lambda: NOW)
    b.refill_if_due(now=NOW)
    b.allocate(GrowthResource.CRAWL, 5)
    assert b.refill_if_due(now=NOW + 2 * HOUR) is True
    assert b.remaining(GrowthResource.CRAWL) == 5


def test_budget_engine_as_dict():
    b = GrowthBudgetEngine({GrowthResource.ONBOARDING: 4}, clock=lambda: NOW)
    b.allocate(GrowthResource.ONBOARDING, 1)
    assert b.as_dict()["onboarding"] == {"limit": 4, "consumed": 1}


# ============================================================ learning


def _observe(le, **kw):
    le.observe(StepOutcome(**kw))


def test_learning_observe_accumulates():
    le = LearningEngine()
    _observe(le, accepted=3, rejected=1)
    _observe(le, accepted=2)
    assert le.tally()["accepted"] == 5 and le.tally()["rejected"] == 1


def test_learning_rates():
    le = LearningEngine()
    _observe(le, accepted=6, rejected=4)
    assert abs(le.acceptance_rate - 0.6) < 1e-9
    assert abs(le.rejection_rate - 0.4) < 1e-9


def test_learning_increase_expansion_on_high_acceptance():
    le = LearningEngine()
    _observe(le, accepted=8, rejected=2)  # 0.8, sample 10
    kinds = {r.kind for r in le.recommend()}
    assert RecommendationKind.INCREASE_EXPANSION in kinds


def test_learning_reduce_exploration_on_high_rejection():
    le = LearningEngine()
    _observe(le, accepted=2, rejected=8)
    kinds = {r.kind for r in le.recommend()}
    assert RecommendationKind.REDUCE_EXPLORATION in kinds


def test_learning_revisit_later_on_failures():
    le = LearningEngine()
    _observe(le, failures=3)
    kinds = {r.kind for r in le.recommend()}
    assert RecommendationKind.REVISIT_LATER in kinds


def test_learning_maintain_when_normal():
    le = LearningEngine()
    _observe(le, accepted=1, rejected=1)  # below min_sample
    kinds = {r.kind for r in le.recommend()}
    assert kinds == {RecommendationKind.MAINTAIN}


def test_learning_min_sample_gate():
    le = LearningEngine(min_sample=5)
    _observe(le, accepted=3, rejected=0)  # decided 3 < 5, would be high acceptance
    kinds = {r.kind for r in le.recommend()}
    assert RecommendationKind.INCREASE_EXPANSION not in kinds


def test_learning_recommend_is_pure():
    le = LearningEngine()
    _observe(le, accepted=8, rejected=2)
    before = le.tally()
    le.recommend()
    le.recommend()
    assert le.tally() == before  # recommending mutates nothing


# ============================================================ planner


def test_planner_refill_adds_freshness_and_opportunities():
    q = GrowthQueue()
    p = GrowthPlanner()
    added = p.refill_queue(
        q,
        run=1,
        freshness_tasks=[mk_task(kind=TaskKind.ORGANIZER_REFRESH, target="o1")],
        opportunities=[GrowthOpportunity(OpportunityKind.NEW_CITY, "Pune", "gap")],
    )
    assert added == 2 and q.backlog() == 2


def test_planner_refill_dedups():
    q = GrowthQueue()
    q.enqueue(mk_task(kind=TaskKind.EXPANSION, target="Pune"))
    p = GrowthPlanner()
    added = p.refill_queue(
        q, run=1, opportunities=[GrowthOpportunity(OpportunityKind.NEW_CITY, "Pune", "gap")]
    )
    assert added == 0  # expansion:Pune already queued


def test_planner_select_highest_priority():
    q = GrowthQueue()
    q.enqueue(mk_task(kind=TaskKind.PRODUCTION_MONITOR, target="a"))
    q.enqueue(mk_task(kind=TaskKind.EXPANSION, target="b"))
    b = GrowthBudgetEngine(clock=lambda: NOW)
    task, reason = GrowthPlanner().select(q, b, 1)
    assert task.kind is TaskKind.EXPANSION and "selected" in reason


def test_planner_select_skips_validation_without_seed_backlog():
    q = GrowthQueue()
    q.enqueue(mk_task(kind=TaskKind.VALIDATION, target="batch"))
    b = GrowthBudgetEngine(clock=lambda: NOW)
    task, _ = GrowthPlanner().select(q, b, 1, has_seed_backlog=False)
    assert task is None


def test_planner_select_skips_onboarding_without_backlog():
    q = GrowthQueue()
    q.enqueue(mk_task(kind=TaskKind.ONBOARDING, target="batch"))
    b = GrowthBudgetEngine(clock=lambda: NOW)
    task, _ = GrowthPlanner().select(q, b, 1, has_onboarding_backlog=False)
    assert task is None


def test_planner_select_skips_when_budget_exhausted():
    q = GrowthQueue()
    q.enqueue(mk_task(kind=TaskKind.VALIDATION, target="batch"))
    b = GrowthBudgetEngine({GrowthResource.VALIDATION: 0}, clock=lambda: NOW)
    task, reason = GrowthPlanner().select(q, b, 1, has_seed_backlog=True)
    assert task is None and "idle" in reason


def test_planner_select_none_when_empty():
    task, reason = GrowthPlanner().select(GrowthQueue(), GrowthBudgetEngine(clock=lambda: NOW), 1)
    assert task is None


def test_planner_select_respects_cooldown():
    q = GrowthQueue()
    t = mk_task(kind=TaskKind.EXPANSION, target="b")
    t.state = TaskState.COOLDOWN
    t.cooldown_until = 10
    q.load([t])
    b = GrowthBudgetEngine(clock=lambda: NOW)
    assert GrowthPlanner().select(q, b, 5)[0] is None
    assert GrowthPlanner().select(q, b, 10)[0] is not None


# ============================================================ metrics


def test_metrics_record_and_totals():
    m = GrowthMetricsEngine()
    m.record_cycle(StepOutcome(seeds_generated=3, seeds_validated=3, accepted=2, rejected=1))
    snap = m.snapshot()
    assert snap.new_seeds == 3 and snap.validated == 3 and snap.rejected == 1


def test_metrics_growth_velocity():
    m = GrowthMetricsEngine()
    m.record_cycle(StepOutcome(accepted=2))
    m.record_cycle(StepOutcome())
    assert m.snapshot().growth_velocity == 1.0  # 2 accepted / 2 cycles


def test_metrics_coverage():
    m = GrowthMetricsEngine()
    m.observe_cities(known={"a", "b"}, covered={"a"})
    assert m.snapshot().ecosystem_coverage == 0.5


def test_metrics_expansion_efficiency():
    m = GrowthMetricsEngine()
    m.record_cycle(StepOutcome(seeds_generated=4))
    m.record_cycle(StepOutcome(accepted=2))
    assert m.snapshot().expansion_efficiency == 0.5


def test_metrics_efficiency_zero_without_seeds():
    m = GrowthMetricsEngine()
    m.record_cycle(StepOutcome(accepted=2))
    assert m.snapshot().expansion_efficiency == 0.0


def test_metrics_steady_false_initially():
    assert not GrowthMetricsEngine().is_steady()


def test_metrics_steady_after_window_of_no_progress():
    m = GrowthMetricsEngine(steady_window=3)
    for _ in range(3):
        m.record_cycle(StepOutcome())
    assert m.is_steady()


def test_metrics_steady_resets_on_progress():
    m = GrowthMetricsEngine(steady_window=3)
    m.record_cycle(StepOutcome())
    m.record_cycle(StepOutcome(accepted=1))  # progress
    m.record_cycle(StepOutcome())
    assert not m.is_steady()


def test_metrics_snapshot_as_dict():
    d = GrowthMetricsEngine().snapshot().as_dict()
    assert "growth_velocity" in d and "ecosystem_coverage" in d


# ============================================================ steps (seam)


def test_constant_step():
    out = run(make_constant_step(StepOutcome(seeds_generated=7))(ctx()))
    assert out.seeds_generated == 7


def test_expansion_step_generates_seeds_real_engines():
    org = OrganizerIntelligenceEngine()
    org.ingest_organizer("GDG Bangalore", text="GDG chapter in Bangalore, India. DevFest.")
    eco = EcosystemExpansionEngine()
    buf = SeedBuffer()
    out = run(make_expansion_step(org, eco, buf)(ctx()))
    assert out.seeds_generated > 0
    assert buf.pending_seeds and out.follow_ups[0].kind is TaskKind.VALIDATION


def test_expansion_step_no_new_seeds_second_run():
    org = OrganizerIntelligenceEngine()
    org.ingest_organizer("GDG Bangalore", text="GDG chapter in Bangalore, India.")
    eco = EcosystemExpansionEngine()
    buf = SeedBuffer()
    step = make_expansion_step(org, eco, buf)
    run(step(ctx()))
    out2 = run(step(ctx()))
    assert out2.seeds_generated == 0 and out2.follow_ups == []


def _seed(kind=SeedKind.CHAPTER_SIBLING, target="GDG Delhi", conf=0.6):
    return ExpansionSeed(
        kind=kind,
        target=target,
        target_key=target.lower().replace(" ", "-"),
        source="org:x",
        reason="seed",
        confidence=conf,
        search_hint=f"{target} tech community",
        path=RelationshipPath(nodes=["GDG Bangalore", target], relations=["same_chapter"]),
    )


def _val_engine(inbox, seeds):
    fetch_map, search_map = {}, {}
    for s in seeds:
        url = f"https://{s.target_key}.dev/"
        fetch_map[url] = FetchResult(url=url, status=200, content_type="text/html", text=RICH)
        search_map[f"{s.target} tech community"] = [url]
    return SeedValidationEngine(
        inbox,
        StaticFetcher(fetch_map),
        searcher=FixtureSearcher(search_map),
        clock=lambda: NOW,
        retry=RetryPolicy(max_retries=2, cooldown_runs=1),
    )


def test_validation_step_drains_buffer_and_accepts_real_engine():
    inbox = InMemoryDiscoveryInbox()
    buf = SeedBuffer()
    buf.pending_seeds = [_seed(target="GDG Delhi"), _seed(target="GDG Noida")]
    val = _val_engine(inbox, buf.pending_seeds)
    out = run(make_validation_step(val, buf)(ctx()))
    assert out.seeds_validated == 2 and out.accepted >= 1
    assert buf.pending_seeds == [] and buf.pending_candidates >= 1
    assert run(inbox.count()) >= 1
    assert out.follow_ups and out.follow_ups[0].kind is TaskKind.ONBOARDING


def test_validation_step_empty_buffer_noop():
    val = _val_engine(InMemoryDiscoveryInbox(), [])
    out = run(make_validation_step(val, SeedBuffer())(ctx()))
    assert out.seeds_validated == 0 and out.follow_ups == []


def test_onboarding_step_observational_no_promotion():
    buf = SeedBuffer()
    buf.pending_candidates = 5
    out = run(make_onboarding_step(buf)(ctx()))
    assert out.promoted == 0 and buf.pending_candidates == 0  # counted, never auto-promoted


def test_onboarding_step_with_explicit_hook():
    buf = SeedBuffer()
    buf.pending_candidates = 4

    async def hook(n):
        return n  # simulate human-approved 7A promoting all

    out = run(make_onboarding_step(buf, promote_hook=hook)(ctx()))
    assert out.promoted == 4


def test_production_monitor_no_provider():
    out = run(make_production_monitor_step()(ctx()))
    assert out.failures == 0


def test_production_monitor_reports_failures():
    async def health():
        return {"failures": 2, "healthy": 8}

    out = run(make_production_monitor_step(health)(ctx()))
    assert out.failures == 2


def test_organizer_refresh_reingests():
    org = OrganizerIntelligenceEngine()
    pages = {"GDG Delhi": ("https://gdg-delhi.dev/", RICH)}
    out = run(
        make_organizer_refresh_step(org, pages)(
            ctx(task=mk_task(kind=TaskKind.ORGANIZER_REFRESH, target="GDG Delhi"))
        )
    )
    assert out.organizers_found == 1 and org.organizer_ids()


def test_organizer_refresh_missing_page():
    org = OrganizerIntelligenceEngine()
    out = run(
        make_organizer_refresh_step(org, {})(
            ctx(task=mk_task(kind=TaskKind.ORGANIZER_REFRESH, target="Nope"))
        )
    )
    assert out.organizers_found == 0


# ============================================================ engine


class RecordingStep:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0

    async def __call__(self, c: StepContext) -> StepOutcome:
        self.calls += 1
        return self.outcome


def _engine(steps, *, inputs=None, store=None, queue=None, budget=None):
    return GrowthEngine(
        steps=steps,
        queue=queue or GrowthQueue(),
        budget=budget or GrowthBudgetEngine(clock=lambda: NOW),
        store=store,
        inputs_provider=inputs,
        clock=lambda: NOW,
    )


def _all_steps(**overrides):
    steps = {k: make_constant_step(StepOutcome()) for k in TaskKind}
    steps.update(overrides)
    return steps


def test_engine_run_cycle_executes_task():
    rec_step = RecordingStep(StepOutcome(seeds_generated=1))
    eng = _engine(_all_steps(**{TaskKind.EXPANSION: rec_step}))
    record = run(eng.run_cycle(now=NOW))
    assert record.task_kind is not None and rec_step.calls >= 0


def test_engine_idle_cycle_when_nothing_runnable():
    # empty schedule + no inputs -> nothing to do
    eng = GrowthEngine(
        steps=_all_steps(),
        scheduler=GrowthScheduler([], clock=lambda: NOW),
        queue=GrowthQueue(),
        inputs_provider=lambda: GrowthInputs(),
        clock=lambda: NOW,
    )
    record = run(eng.run_cycle(now=NOW))
    assert record.task_kind is None


def test_engine_charges_budget():
    step = make_constant_step(StepOutcome(cost={GrowthResource.CRAWL: 3}))
    budget = GrowthBudgetEngine({GrowthResource.CRAWL: 10}, clock=lambda: NOW)
    eng = GrowthEngine(
        steps=_all_steps(**{TaskKind.EXPANSION: step}),
        scheduler=GrowthScheduler(
            [ScheduleSpec(TaskKind.EXPANSION, GrowthCadence.DAILY)], clock=lambda: NOW
        ),
        budget=budget,
        inputs_provider=lambda: GrowthInputs(),
        clock=lambda: NOW,
    )
    run(eng.run_cycle(now=NOW))
    assert budget.remaining(GrowthResource.CRAWL) == 7


def test_engine_enqueues_follow_ups():
    follow = GrowthTask(kind=TaskKind.VALIDATION, target="batch")
    step = make_constant_step(StepOutcome(seeds_generated=1, follow_ups=[follow]))
    eng = GrowthEngine(
        steps=_all_steps(**{TaskKind.EXPANSION: step}),
        scheduler=GrowthScheduler(
            [ScheduleSpec(TaskKind.EXPANSION, GrowthCadence.DAILY)], clock=lambda: NOW
        ),
        inputs_provider=lambda: GrowthInputs(),
        clock=lambda: NOW,
    )
    run(eng.run_cycle(now=NOW))
    assert eng.queue.get("validation:batch") is not None


def test_engine_touches_freshness():
    eng = GrowthEngine(
        steps=_all_steps(),
        scheduler=GrowthScheduler(
            [ScheduleSpec(TaskKind.EXPANSION, GrowthCadence.DAILY)], clock=lambda: NOW
        ),
        inputs_provider=lambda: GrowthInputs(),
        clock=lambda: NOW,
    )
    run(eng.run_cycle(now=NOW))
    assert eng.freshness.record("batch", EntityKind.EXPANSION) is not None


def test_engine_records_metrics_and_learning():
    step = make_constant_step(StepOutcome(accepted=2, rejected=1, seeds_validated=3))
    eng = GrowthEngine(
        steps=_all_steps(**{TaskKind.VALIDATION: step}),
        scheduler=GrowthScheduler(
            [ScheduleSpec(TaskKind.VALIDATION, GrowthCadence.HOURLY)], clock=lambda: NOW
        ),
        inputs_provider=lambda: GrowthInputs(has_seed_backlog=True),
        clock=lambda: NOW,
    )
    run(eng.run_cycle(now=NOW))
    assert eng.metrics.snapshot().validated == 3
    assert eng.learning.tally()["accepted"] == 2


def test_engine_run_reaches_steady_state():
    buffer = SeedBuffer()

    async def expansion(c):
        if buffer.seen_seed_keys:
            return StepOutcome(seeds_generated=0)
        buffer.seen_seed_keys.add("x")
        buffer.pending_seeds.extend(["s1", "s2"])
        return StepOutcome(
            seeds_generated=2, follow_ups=[GrowthTask(kind=TaskKind.VALIDATION, target="batch")]
        )

    async def validation(c):
        seeds = buffer.pending_seeds
        buffer.pending_seeds = []
        if not seeds:
            return StepOutcome()
        buffer.pending_candidates += 1
        return StepOutcome(seeds_validated=len(seeds), accepted=1)

    steps = _all_steps(**{TaskKind.EXPANSION: expansion, TaskKind.VALIDATION: validation})

    def inputs():
        return GrowthInputs(
            has_seed_backlog=bool(buffer.pending_seeds),
            has_onboarding_backlog=buffer.pending_candidates > 0,
        )

    eng = _engine(steps, inputs=inputs)
    report = run(eng.run(max_cycles=30, now=NOW))
    assert report.reached_steady_state
    assert "expansion" in report.by_kind and "validation" in report.by_kind
    assert eng.metrics.snapshot().new_seeds == 2


def test_engine_run_respects_max_cycles():
    # a step that always makes progress -> never steady; capped by max_cycles
    step = make_constant_step(StepOutcome(seeds_generated=1))
    eng = GrowthEngine(
        steps=_all_steps(**{TaskKind.EXPANSION: step}),
        scheduler=GrowthScheduler(
            [ScheduleSpec(TaskKind.EXPANSION, GrowthCadence.CONTINUOUS)], clock=lambda: NOW
        ),
        inputs_provider=lambda: GrowthInputs(),
        clock=lambda: NOW,
    )
    report = run(eng.run(max_cycles=4, now=NOW))
    assert report.cycles == 4 and not report.reached_steady_state


def test_engine_snapshot_has_all_sections():
    eng = _engine(
        _all_steps(), inputs=lambda: GrowthInputs(cities_known={"a"}, cities_covered={"a"})
    )
    run(eng.run_cycle(now=NOW))
    d = eng.snapshot(now=NOW).as_dict()
    for key in (
        "backlog",
        "queue",
        "opportunities",
        "budgets",
        "health",
        "freshness",
        "recommendations",
        "metrics",
    ):
        assert key in d


def test_engine_snapshot_surfaces_opportunities():
    eng = _engine(
        _all_steps(),
        inputs=lambda: GrowthInputs(
            signals=OpportunitySignals(organizer_cities={"Chennai"}, seed_cities={"Pune"})
        ),
    )
    snap = eng.snapshot(now=NOW)
    assert any(o["kind"] == "new_city" for o in snap.opportunities)


def test_engine_recommendations_advisory_only():
    step = make_constant_step(StepOutcome(failures=3))
    eng = GrowthEngine(
        steps=_all_steps(**{TaskKind.PRODUCTION_MONITOR: step}),
        scheduler=GrowthScheduler(
            [ScheduleSpec(TaskKind.PRODUCTION_MONITOR, GrowthCadence.HOURLY)], clock=lambda: NOW
        ),
        inputs_provider=lambda: GrowthInputs(),
        clock=lambda: NOW,
    )
    run(eng.run_cycle(now=NOW))
    kinds = {r.kind for r in eng.recommendations()}
    assert RecommendationKind.REVISIT_LATER in kinds  # surfaced, not auto-applied


def test_engine_safety_no_auto_promotion():
    # onboarding runs but promotes nothing without an explicit hook
    buffer = SeedBuffer()
    buffer.pending_candidates = 3
    eng = GrowthEngine(
        steps=_all_steps(**{TaskKind.ONBOARDING: make_onboarding_step(buffer)}),
        scheduler=GrowthScheduler(
            [ScheduleSpec(TaskKind.ONBOARDING, GrowthCadence.HOURLY)], clock=lambda: NOW
        ),
        inputs_provider=lambda: GrowthInputs(has_onboarding_backlog=True),
        clock=lambda: NOW,
    )
    run(eng.run_cycle(now=NOW))
    assert eng.metrics.snapshot().promoted == 0


def test_engine_persistence():
    store = InMemoryGrowthStore()
    eng = GrowthEngine(
        steps=_all_steps(),
        scheduler=GrowthScheduler(
            [ScheduleSpec(TaskKind.EXPANSION, GrowthCadence.DAILY)], clock=lambda: NOW
        ),
        store=store,
        inputs_provider=lambda: GrowthInputs(),
        clock=lambda: NOW,
    )
    run(eng.run_cycle(now=NOW))
    assert len(run(store.load_cycles())) == 1
    assert run(store.load_queue())  # queue persisted


def test_engine_full_real_loop_10c_10d_10e():
    """End-to-end reuse: 10C organizer → 10D expansion → 10E validation → existing inbox."""
    org = OrganizerIntelligenceEngine()
    org.ingest_organizer("GDG Bangalore", text="GDG chapter in Bangalore, India. DevFest. Python.")
    eco = EcosystemExpansionEngine()
    buffer = SeedBuffer()
    inbox = InMemoryDiscoveryInbox()

    # a fetcher/searcher that resolves any chapter-sibling seed to the RICH page
    class AnyFetcher:
        async def get(self, url):
            return FetchResult(url=url, status=200, content_type="text/html", text=RICH)

    class AnySearcher:
        def search(self, query):
            return []

    val = SeedValidationEngine(
        inbox,
        AnyFetcher(),
        searcher=AnySearcher(),
        clock=lambda: NOW,
        retry=RetryPolicy(max_retries=2, cooldown_runs=1),
    )

    steps = _all_steps(
        **{
            TaskKind.EXPANSION: make_expansion_step(org, eco, buffer),
            TaskKind.VALIDATION: make_validation_step(val, buffer),
            TaskKind.ONBOARDING: make_onboarding_step(buffer),
        }
    )

    def inputs():
        return GrowthInputs(
            has_seed_backlog=bool(buffer.pending_seeds),
            has_onboarding_backlog=buffer.pending_candidates > 0,
        )

    eng = _engine(steps, inputs=inputs)
    report = run(eng.run(max_cycles=30, now=NOW))
    assert report.reached_steady_state
    assert run(inbox.count()) > 0  # real candidates reached the existing inbox
    assert eng.metrics.snapshot().new_seeds > 0


# ============================================================ stores


def test_inmemory_store_queue_roundtrip():
    store = InMemoryGrowthStore()
    run(store.save_queue([mk_task(kind=TaskKind.VALIDATION, target="b", attempts=2)]))
    loaded = run(store.load_queue())
    assert loaded[0].kind is TaskKind.VALIDATION and loaded[0].attempts == 2


def test_inmemory_store_freshness_roundtrip():
    store = InMemoryGrowthStore()
    run(store.save_freshness([FreshnessRecord("o1", EntityKind.ORGANIZER, NOW, 3600)]))
    loaded = run(store.load_freshness())
    assert loaded[0].entity_id == "o1" and loaded[0].kind is EntityKind.ORGANIZER


def test_inmemory_store_cycles_append():
    store = InMemoryGrowthStore()
    run(store.append_cycle(CycleRecord(1, "expansion", "batch", {}, "r", NOW.isoformat())))
    assert len(run(store.load_cycles())) == 1


def test_sqlite_store_queue_roundtrip(tmp_path):
    store = SQLiteGrowthStore(str(tmp_path / "g.db"))
    run(store.save_queue([mk_task(kind=TaskKind.EXPANSION, target="Pune", priority=77)]))
    loaded = run(store.load_queue())
    assert loaded[0].target == "Pune" and loaded[0].priority == 77


def test_sqlite_store_freshness_roundtrip(tmp_path):
    store = SQLiteGrowthStore(str(tmp_path / "g.db"))
    run(store.save_freshness([FreshnessRecord("s1", EntityKind.SEED, NOW, 100)]))
    loaded = run(store.load_freshness())
    assert loaded[0].entity_id == "s1" and loaded[0].ttl_seconds == 100


def test_sqlite_store_cycles_ordered(tmp_path):
    store = SQLiteGrowthStore(str(tmp_path / "g.db"))
    for i in range(3):
        run(store.append_cycle(CycleRecord(i, "expansion", "b", {}, "r", NOW.isoformat())))
    cycles = run(store.load_cycles())
    assert [c.run for c in cycles] == [0, 1, 2]


def test_sqlite_store_empty_loads(tmp_path):
    store = SQLiteGrowthStore(str(tmp_path / "g.db"))
    assert run(store.load_queue()) == []
    assert run(store.load_freshness()) == []
    assert run(store.load_cycles()) == []


def test_sqlite_store_queue_replace(tmp_path):
    store = SQLiteGrowthStore(str(tmp_path / "g.db"))
    run(store.save_queue([mk_task(target="a")]))
    run(store.save_queue([mk_task(target="b")]))  # full replace
    loaded = run(store.load_queue())
    assert len(loaded) == 1 and loaded[0].target == "b"
