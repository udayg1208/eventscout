# Autonomous Discovery Orchestrator — Phase 9A

The **control plane** that runs EventScout's entire discovery ecosystem continuously. It is *not* a
new discovery engine — it schedules, budgets, executes, checkpoints, recovers, and measures every
capability built in D1–D4, 7A–7B, and 8A–8E, driving each through one uniform stage seam. The
canonical loop is Search → Web → Expansion → Social → Rendered → Inbox → Onboarding → Production →
Catalog Refresh → Optimization → repeat, but that order is **data, not code** — the planner reads a
pipeline spec and picks the next stage by priority, backlog, and remaining budget.

Code: `backend/app/orchestrator/` (new package — additive). It **reuses** every existing engine via
adapters and **modifies nothing**: Search, Repository, Catalog, provider implementations, the
discovery engines, onboarding, production operations, the scheduler, the frontend, and the API are
all untouched. No browser, no LLM, no network — the loop is deterministic and clock-injected.

## Architecture

```
app/orchestrator/
  models.py      enums (StageName·StageHealth·RunStatus·ScheduleKind·Trigger·BudgetKind) + dataclasses
                 (Budget·Schedule·StageSpec·StageContext·StageOutcome·StageState·Lease·Checkpoint·
                 DeadLetterEntry·OrchestratorState·MetricsSnapshot·…) + the StageRunner seam
  pipeline.py    default_pipeline() — the 10 stages as data (schedules, priorities, seed-flow edges)
  scheduler.py   Scheduler — is_due / next_run_at (cadence · retry backoff · cooldown · pause)
  planner.py     Planner — picks the highest effective-priority eligible stage; grants budget
  state.py       StateManager — the single writer of state; fan-out; provider stats; serde
  executor.py    LeaseManager + StageExecutor — single-flight execution under lease + timeout
  recovery.py    DeadLetterQueue + RecoveryManager — checkpoint restore, crash replay, DLQ
  metrics.py     MetricsEngine — counters → rates (events/hr, promotion, duplicate, precision, …)
  engine.py      OrchestratorEngine — the continuous loop
  store.py       OrchestratorStore (InMemory + SQLite) — durable state + checkpoint trail
  interfaces.py  adapters that wrap the real engines as StageRunners + Phase-9B seams
```

### The loop (`engine.py`)

```
while running:
    now      = clock()
    plan     = planner.plan(state, now)      # which stage, what budget — or None (idle)
    outcome  = executor.execute(runner, ctx) # under a lease + timeout; failure ≠ hang
    state.apply_outcome(...)                 # totals, budget spend, schedule, seed fan-out
    metrics.observe(...)                     # rates
    store.save_state + save_checkpoint       # recover from here
    optimize()                               # bounded, reversible self-tuning (opt-in)
    sleep(interval)                          # injected; only sleeps when interval > 0
```

`run(max_cycles=…)` bounds the loop for tests and demos — **there is no unbounded loop in test
code**. Each cycle executes exactly one stage (the planner's pick), which keeps scheduling fair and
the loop trivially checkpointable.

## Reuse — how each stage maps to a real engine

The core never imports an engine; `interfaces.py` adapts each one to a `StageRunner`
(`StageContext → StageOutcome`). Production wires these; the 9A tests and spike pass mocks.

| Stage | Real component (frozen) | Entry point |
|---|---|---|
| `search_discovery` | `SearchDiscoveryEngine` (D3) | `run(spec)` |
| `web_discovery` | `WebDiscoveryEngine` (8B) | `run(spec)` |
| `expansion` | `ExpansionEngine` (8C) | `expand(seeds, max_pages)` |
| `social_discovery` | `SocialDiscoveryEngine` (8D) | `discover(pages)` |
| `rendered_discovery` | `RenderedDiscoveryEngine` (8E) | `discover(pages)` |
| `inbox` | `DiscoveryInbox` (D1) | drain `status=NEW` |
| `onboarding` | `OnboardingEngine` (7A) | `ingest_from_inbox()` |
| `production_ops` | `OperationsEngine` (7B) | `promote()` / `continuous_sync()` |
| `catalog_refresh` | Catalog | reindex |
| `optimization` | `OptimizationEngine` (8A) | `run()` → recommendations |

## Scheduling

`Scheduler` answers *"is this stage due at `now`?"* deterministically. Cadences: **continuous**
(eligible whenever budget/backlog allow), **hourly**, **daily**, **weekly**, **manual** (trigger
only). On top of cadence: **retry** (a FAILED stage becomes due again after an exponential backoff,
`backoff · 2^(retry-1)`, up to `retry_max`), **cooldown** (a stage that asked to rest is not due
until its window expires), and **pause/resume** (a paused stage is never due). A `Trigger` decides
whether a stage runs on its schedule, only when it has backlog, or both.

## Planning — data-driven, budget-adaptive

The planner hardcodes no sequence. It scores every eligible stage:

```
effective = base_priority
          + backlog_pressure            (min 3.0, +0.5 per queued unit)
          + starvation                  (up to +2.0 for long-overdue stages)
          − budget_penalty              (up to +1.0 per budget kind running low)
          − health_penalty              (−1.5 if degraded)
```

and picks the maximum. It **grants budget that shrinks as the pool depletes** (below 25% remaining a
stage's ask is halved), and defers any stage whose required budget kind is exhausted — the control
plane throttles itself instead of blowing the ₹0 ceiling. The canonical Search→…→Optimization order
*emerges* from the default priorities plus seed fan-out; reorder or reprioritise by editing data.

## Budgets

Six kinds — **crawl, search, AI, page, provider, depth** — each a `Budget{limit, consumed}` in a
`BudgetPool`. A stage requests per-kind budget in its spec; the planner grants against what's left;
the outcome reports what was actually spent, and the state manager debits the pool. When a kind runs
low the planner throttles grants and lowers those stages' effective priority; when it's empty they're
deferred. This is how a daily crawl/search/AI/page/provider/depth ceiling is enforced end-to-end.

## State

`StateManager` is the single writer. Per stage it persists **last run, next run, duration, status,
health, consecutive failures, retry count, cooldown, backlog, seeds, cumulative discovered/promoted/
rejected, and budget consumed**; globally it tracks the cycle, budget pool, dead-letter queue, and
**provider statistics** (discovered/promoted/rejected/active). Every mutation flows through one place,
so a checkpoint is a faithful snapshot and restore is exact.

## Recovery

Four mechanisms (`recovery.py` + `engine.resume_from_store`):
- **Checkpoint recovery** — every cycle snapshots full state to the store; on start we restore the latest.
- **Crash replay** — a stage left `RUNNING` when the process died is re-queued (its lease, being
  time-bounded, is stolen by the next owner). Verified: worker A "crashes" mid-run, worker B resumes
  and replays it to success.
- **Partial retry** — a FAILED stage is retried on the scheduler's backoff up to `retry_max`.
- **Dead-letter queue** — a stage that exhausts its retries is parked in the DLQ and marked
  `DEAD_LETTER` (the planner skips it) so one poison stage never blocks the loop; an operator can
  requeue it.

## Concurrency safety

`LeaseManager` gives each stage a single-owner, TTL'd lease kept alive by heartbeats. A stage runs
only while its caller holds a live lease; a second owner is refused (`LeaseError` → the executor
returns a DEGRADED outcome without running — **the same stage never executes twice at once**). A
lapsed lease (crashed owner) can be stolen, which is exactly what makes crash replay safe. Timeouts
wrap every stage: a hung runner becomes a FAILED outcome, never a stuck loop.

## Metrics

`MetricsEngine` turns raw counters into the dashboard: **events discovered/hour, new providers/day,
new sources/day, promotion rate, duplicate rate, crawl efficiency (discovered/page), AI usage, queue
sizes, per-stage latency, throughput (stages/cycle), catalog size, and precision/recall/false
positives**. Rates use the injected clock so they're exact. Precision/recall depend on labelled
downstream feedback (`record_feedback`) and are honestly 0 until a downstream confirms candidates.

## Health model

Every stage reports `healthy | degraded | failed | paused`; the state manager rolls these up
(`failed` if any stage failed, else `degraded` if any degraded, …). Health feeds back into planning —
a degraded stage is penalised, a paused one is skipped, a failed one retries then dead-letters — so
the pipeline adapts automatically to a struggling stage instead of stalling on it.

## Live demonstration

`backend/spikes/p9a_orchestrator.py` (mocks, no network) drains a discovered batch through the whole
pipeline to idle, then shows resilience:

```
cyc 1  search_discovery   success [first run]  disc=6
cyc 2  web_discovery      success [backlog=1]  disc=4
cyc 3  expansion          success [backlog=2]  disc=5
…                                                        (planner picks by priority + backlog)
cyc38  optimization       success [first run]
cyc39  (idle — nothing due) → stop

METRICS: 131 events (131/hr) · 42 providers · promotion 32% · duplicate 4.4% ·
         crawl-eff 0.81 disc/page · 35 AI calls · throughput 0.97 stages/cycle
budget remaining: provider 8/50, ai 65/300, …           (self-throttled)

RESILIENCE 1 — poison stage: failed → dead_letter(retry 2/2) → skipped   (loop keeps running)
RESILIENCE 2 — crash recovery: worker A RUNNING → worker B resume → replay → success
```

## Tests

`backend/tests/test_orchestrator.py` — **37 tests, no network, every stage mocked**: budgets;
scheduler (first-run, cadence, pause, cooldown, manual, retry backoff + exhaustion); planner
(priority pick, backlog eligibility, idle, unaffordable skip, budget-throttled grant); state manager
(fan-out, failure/retry, budget spend, provider stats); executor + leases (acquire/conflict/steal,
release/reap, run, exception→failed, timeout→failed, **lock prevents double execution**); metrics
(rates, precision/recall); recovery (DLQ, crash replay); stores (InMemory + SQLite typed round-trip);
and the engine end-to-end (run-once, bounded sequencing, **retry→dead-letter**, **crash recovery**,
checkpoint-per-cycle, budget-exhaustion defer, pause/resume, stop-when-idle). Full backend suite:
**580 passed**.

## Honest self-review

**Truly true**
- The control plane is real and deterministic: planning, cadence/retry/cooldown/pause scheduling,
  budget throttling, single-flight leases with steal-on-expiry, checkpoint + crash replay + DLQ, and
  metric derivation all work and are tested. It genuinely modifies none of the engines — it drives
  them through a seam.

**Weaknesses / limitations**
1. **Single-process; in-memory leases.** 9A is one loop on one machine. The leases/heartbeats/timeouts
   are the *right shape* for a cluster but are in-process — real multi-worker coordination (shared
   lease backend, task queue, worker nodes) is Phase 9B and currently `NotImplementedError` seams.
2. **The real-engine wiring is not exercised here.** The adapters in `interfaces.py` map each engine
   to the seam, but the 9A tests and spike run entirely on mocks (by requirement). End-to-end against
   live engines — with their real reports, network, and failure modes — is unproven in this phase.
3. **The planner is greedy and hand-tuned.** One stage per cycle, effective-priority weights chosen by
   hand. They're explainable and behave sensibly, but this is not an optimal scheduler; pathological
   priority/budget combinations could starve a stage.
4. **Backpressure can bunch.** Mid-pipeline stages fed by several upstreams accumulate backlog (visible
   in the demo: inbox/onboarding run many times). The planner drains it, but there's no queue bound or
   rate-limit beyond budgets, so a burst upstream can dominate many cycles.
5. **Backlog is an approximation.** Fan-out adds "+1 backlog per upstream run", not exact item counts,
   and a run drains one unit. It sequences the pipeline correctly but is a coarse proxy for real
   pending-work volume.
6. **Recovery is whole-stage, snapshot-based.** A crashed stage reruns from scratch, so **stage runners
   must be idempotent** (re-running search/onboarding must not double-count). Checkpoints are full-state
   each cycle — fine at this scale, not incremental; there's no within-stage progress replay.
7. **Metrics need feedback and wall-clock.** Precision/recall are 0 without labelled downstream results;
   rates are 0 under a frozen clock (the demo extrapolates over a 1-hour window). They measure the loop,
   not ground-truth discovery quality.
8. **`optimize()` is a bounded nudge, not the real 8A engine.** Auto-tune (off by default) makes small
   reversible priority adjustments; it is recommend-only otherwise and is not the OptimizationEngine
   closing the loop.

## Where Phase 9B begins (NOT this phase)

9A is a single-process control plane. **Phase 9B — Distributed Multi-Worker Discovery Cluster** —
would add a shared lease backend (Redis/Postgres), a durable cross-process task queue, worker nodes
that lease stages from the cluster, and parallel multi-stage execution. The seams
(`DistributedLeaseBackend`, `TaskQueue`, `WorkerNode`) are stubbed and raise `NotImplementedError`.

---

**Status:** 9A complete. Additive; D1–D4 / 7A–7B / 8A–8E / frozen systems untouched; 580 tests green;
deterministic, mock-driven, no browser/LLM/network; control-plane-only. **Stopping here — Phase 9B
NOT started.**
