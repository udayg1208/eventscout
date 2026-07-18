"""Phase 9A live demonstration: the continuous discovery orchestrator, driven entirely by mocks.

Shows one autonomous run draining a discovered batch through the whole pipeline —
Search → Web → Expansion → Social → Rendered → Inbox → Onboarding → Production → Catalog →
Optimization — the data-driven planner choosing each stage by priority + backlog + budget, the state
manager fanning seeds downstream, budgets depleting, and the metrics engine reporting rates. Then
short resilience demos: a poison stage that retries and dead-letters, and crash recovery from a
persisted checkpoint. No real engines, no network, no LLM — every stage is a mock `StageRunner`.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta

logging.disable(logging.CRITICAL)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.orchestrator import (  # noqa: E402
    BudgetKind,
    InMemoryOrchestratorStore,
    MetricsEngine,
    OrchestratorEngine,
    Pipeline,
    Schedule,
    ScheduleKind,
    StageContext,
    StageName,
    StageOutcome,
    StageSpec,
    Trigger,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
S = StageName


def stage(**kw):
    seeds = kw.pop("seeds", None)
    spend = kw.pop("spend", None)

    async def runner(ctx: StageContext) -> StageOutcome:
        return StageOutcome(produced_seeds=list(seeds or []), budget_spent=dict(spend or {}), **kw)

    return runner


def build_engine() -> OrchestratorEngine:
    budgets = {
        BudgetKind.SEARCH: 200,
        BudgetKind.CRAWL: 500,
        BudgetKind.PAGE: 800,
        BudgetKind.AI: 300,
        BudgetKind.PROVIDER: 50,
        BudgetKind.DEPTH: 10,
    }
    eng = OrchestratorEngine(
        budgets=budgets, metrics=MetricsEngine(clock=lambda: NOW), clock=lambda: NOW
    )
    eng.register(
        S.SEARCH_DISCOVERY,
        stage(
            discovered=6,
            seeds=["gdg.dev", "hasgeek.com"],
            spend={BudgetKind.SEARCH: 20, BudgetKind.PAGE: 40},
        ),
    )
    eng.register(
        S.WEB_DISCOVERY,
        stage(
            discovered=4,
            pages=30,
            seeds=["confs.tech"],
            spend={BudgetKind.SEARCH: 15, BudgetKind.PAGE: 60},
        ),
    )
    eng.register(
        S.EXPANSION,
        stage(
            discovered=5,
            pages=40,
            duplicates=3,
            seeds=["meetup.com/x"],
            spend={BudgetKind.CRAWL: 40, BudgetKind.PAGE: 40},
        ),
    )
    eng.register(S.SOCIAL_DISCOVERY, stage(discovered=3, pages=12, spend={BudgetKind.PAGE: 12}))
    eng.register(
        S.RENDERED_DISCOVERY,
        stage(discovered=7, pages=9, ai_calls=4, spend={BudgetKind.PAGE: 9, BudgetKind.AI: 30}),
    )
    eng.register(S.INBOX, stage(discovered=9))
    eng.register(
        S.ONBOARDING,
        stage(
            discovered=3, promoted=3, ai_calls=3, spend={BudgetKind.AI: 20, BudgetKind.PROVIDER: 3}
        ),
    )
    eng.register(S.PRODUCTION_OPS, stage(promoted=3, spend={BudgetKind.PROVIDER: 3}))
    eng.register(S.CATALOG_REFRESH, stage(note="catalog reindexed"))
    eng.register(S.OPTIMIZATION, stage(ai_calls=2, spend={BudgetKind.AI: 5}))
    return eng


async def demo_continuous() -> None:
    print("=== Phase 9A — Continuous Autonomous Discovery Orchestrator (mocks, no network) ===")
    pipe = Pipeline()
    print("\nPIPELINE (data-driven — priorities + triggers, no hardcoded sequence):")
    for spc in pipe.specs:
        print(
            f"  {spc.priority:>4.1f}  {spc.name.value:20s} {spc.schedule.kind.value:10s} "
            f"trigger={spc.trigger.value:8s} → {[d.value for d in spc.produces_for] or '—'}"
        )

    eng = build_engine()
    print(
        "\nBUDGETS:",
        {
            k.value: v
            for k, v in {
                BudgetKind.SEARCH: 200,
                BudgetKind.CRAWL: 500,
                BudgetKind.PAGE: 800,
                BudgetKind.AI: 300,
                BudgetKind.PROVIDER: 50,
                BudgetKind.DEPTH: 10,
            }.items()
        },
    )

    print("\n--- AUTONOMOUS RUN (run until the batch drains, then idle) ---")
    report = await eng.run(max_cycles=60, stop_when_idle=True)
    for cr in report.per_cycle:
        if cr.stage is None:
            print(f"  cyc{cr.cycle:2d}  (idle — nothing due) → stop")
            continue
        o = cr.outcome
        extra = f"disc={o.discovered}" if o.discovered else (o.note or "")
        promo = f" promoted={o.promoted}" if o.promoted else ""
        print(
            f"  cyc{cr.cycle:2d}  {cr.stage.value:20s} {cr.status.value:7s} "
            f"[{cr.reason}]  {extra}{promo}"
        )

    print(f"\nstages executed: {report.stages_run}")
    # the demo clock is frozen for determinism; project the rates over a 1-hour window
    m = eng.metrics.snapshot(NOW + timedelta(hours=1))
    print("\n=== METRICS (rates extrapolated over a 1h window) ===")
    print(f"  events discovered   : {m.events_discovered}   ({m.events_per_hour:.0f}/hr)")
    print(f"  new providers       : {m.new_providers}   ({m.providers_per_day:.0f}/day)")
    print(f"  new sources         : {m.new_sources}")
    print(f"  promotion rate      : {m.promotion_rate:.2%}")
    print(f"  duplicate rate      : {m.duplicate_rate:.2%}")
    print(f"  crawl efficiency    : {m.crawl_efficiency:.2f} discovered/page")
    print(f"  AI calls            : {m.ai_calls}")
    print(f"  throughput          : {m.throughput_per_cycle:.2f} stages/cycle")
    print(f"  per-stage latency   : {len(m.stage_latency_s)} stages measured")
    print(f"\nprovider stats : {eng.state.provider_stats}")
    print("budget remaining:", {k.value: eng.state.budget.remaining(k) for k in BudgetKind})
    print("overall health :", eng._sm.overall_health().value, " dead-letter:", report.dead_lettered)


async def demo_retry_dead_letter() -> None:
    print("\n\n=== RESILIENCE 1 — retry then dead-letter (a poison stage) ===")

    class Clk:
        def __init__(self):
            self.t = NOW

        def __call__(self):
            return self.t

    clk = Clk()
    pipe = Pipeline(
        [
            StageSpec(
                name=S.RENDERED_DISCOVERY,
                schedule=Schedule(
                    kind=ScheduleKind.CONTINUOUS, retry_max=2, retry_backoff_seconds=30
                ),
                trigger=Trigger.BOTH,
            )
        ]
    )

    async def poison(ctx):
        raise RuntimeError("extractor crashed")

    eng = OrchestratorEngine(pipe, {S.RENDERED_DISCOVERY: poison}, clock=clk)
    eng._sm.start(clk())
    for _ in range(4):
        cr = await eng.run_once()
        st = eng.state.stage(S.RENDERED_DISCOVERY)
        print(
            f"  cyc{cr.cycle}: {cr.status.value:11s} retry={st.retry_count}/2  "
            f"dlq={eng.dead_letter.size()}"
        )
        clk.t += timedelta(seconds=10_000)
    print("  → parked in dead-letter queue; planner now skips it (loop keeps running).")


async def demo_crash_recovery() -> None:
    print("\n=== RESILIENCE 2 — crash recovery from a checkpoint ===")
    pipe = Pipeline([StageSpec(name=S.SEARCH_DISCOVERY, trigger=Trigger.BOTH)])
    store = InMemoryOrchestratorStore()
    eng_a = OrchestratorEngine(
        pipe, {S.SEARCH_DISCOVERY: stage(discovered=5)}, store=store, clock=lambda: NOW
    )
    eng_a._sm.mark_running(S.SEARCH_DISCOVERY)  # crash mid-run
    await store.save_state(eng_a.state)
    print(f"  worker A crashed with {S.SEARCH_DISCOVERY.value} left RUNNING; state persisted.")

    eng_b = OrchestratorEngine(
        pipe, {S.SEARCH_DISCOVERY: stage(discovered=5)}, store=store, clock=lambda: NOW
    )
    resumed = await eng_b.resume_from_store()
    st = eng_b.state.stage(S.SEARCH_DISCOVERY)
    print(f"  worker B resumed={resumed}; interrupted stage re-queued as {st.status.value}.")
    eng_b._sm.start(NOW)
    cr = await eng_b.run_once()
    print(f"  worker B replayed it → {cr.stage.value} {cr.status.value}.")


async def main() -> None:
    await demo_continuous()
    await demo_retry_dead_letter()
    await demo_crash_recovery()
    print("\n  ✔ pure control plane over mocked stages — additive, no engines modified, no network")


if __name__ == "__main__":
    asyncio.run(main())
