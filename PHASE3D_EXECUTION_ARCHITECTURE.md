# Phase 3D — Execution Architecture (Scheduler & Worker Engine)

The layer that runs the ingestion pipeline **automatically and continuously**. It decides
what runs, when, how often, how many at once, and what happens on failure, restart, and
shutdown — **without touching the pipeline itself** (Repository v2, Provider State Store,
Plugin System, Ingestion Runner, Capability Registry, Sandbox all frozen and reused
through their public interfaces).

## Design principle: reuse, don't reinvent

The runner already owns **fetch-retry, timeout, and provider-state updates**; the Provider
State Store already owns **backoff scheduling and circuit opening**. So this phase adds no
second copy of those. The engine is pure orchestration — it *honors* the state the store
computes and *delegates* execution to the runner. Everything it decides comes from
**declared provider metadata + persisted state** — never from provider identity.

## Components

```
                         ┌──────────────────────── IngestionEngine ───────────────────────┐
                         │                                                                 │
  Provider State Store   │   Scheduler  ──jobs──►  Dispatcher  ──►  Worker pool            │
  (due? backoff?         │   (DECIDE)              (RUN)            (one provider each)     │
   circuit? health?) ◄───┼──────────────────────────────────────────────┐                 │
                         │      ▲                        │ Job Queue      │ run_ingestion() │
   Capability Registry ──┼──────┘  (metadata)           │ (asyncio now,  ▼ (FROZEN runner) │
   (plugins + metadata)  │                              │  distributed   Repository v2      │
                         │   RateLimiter  Heartbeat  Metrics  later)     Provider State     │
                         └─────────────────────────────────────────────────────────────────┘
```

| Component | Responsibility |
|---|---|
| **Scheduler** (`scheduler.py`) | Decide *what* runs and *in what order*, from metadata + state. Produces `Job`s; never executes. |
| **Job / JobQueue** (`job.py`) | The unit of work + the queue abstraction. `AsyncioJobQueue` now; a distributed queue later — same interface. |
| **Dispatcher** (`dispatcher.py`) | Run jobs through a bounded worker pool. `InProcessDispatcher` now; Redis/Celery/SQS/Kafka later behind the same `Dispatcher` port. |
| **Worker** (`worker.py`) | Execute exactly one provider via the frozen `run_ingestion`; add structured logging + a typed result. Nothing else. |
| **RateLimiter** (`ratelimit.py`) | Per-provider min-interval gate, enforced at scheduling time so workers never block. |
| **Heartbeat / EngineMetrics** (`metrics.py`) | Liveness (uptime, ticks, queue, running) + execution metrics (throughput, rates, health). |
| **IngestionEngine** (`engine.py`) | Wire it together: bootstrap the fleet, run the loop, own the in-flight set, graceful shutdown. |

## Execution flow (the loop)

```
bootstrap fleet (seed a state row per provider, idempotent)
repeat:
  heartbeat (uptime, tick, queue, running)
  find due providers   → state_store.due_providers(now)   [indexed: enabled ∧ next_run ≤ now]
  filter + order       → drop in-flight; auto-disable permanent failures; rate-limit;
                         label open-circuit probes; sort by metadata priority
  enqueue jobs         → dispatcher.submit(job)
  workers consume      → dispatcher pool pulls, runs run_ingestion(plugin, repo, state)
  runner updates state → update_after_run / update_after_failure (backoff, circuit, checkpoint)
  sleep to next tick   → interruptible wait (wakes instantly on shutdown; never busy-waits)
```

One **tick** = one scheduling pass. `run_cycle()` (tick + drain) is the deterministic unit
used in tests; `run_forever()` is the production loop.

## Concurrency model

- **Global concurrency** = the dispatcher's worker-pool size. At most *N* providers run at once.
- **Per-provider concurrency = 1** — the engine's in-flight set; a provider already running is
  excluded from the next tick (so a slow run can't be double-dispatched).
- **Per-provider rate limit** — a min-interval gate from `rate_limit_per_minute`, checked at
  scheduling time so workers never block on it.
- **Failure isolation** — a handler exception is caught inside the worker loop; one bad job
  never kills a worker or the pool.

## Retry, backoff, and the circuit breaker

Three layers, none duplicated (see [SCHEDULER_BREAKDOWN.md](SCHEDULER_BREAKDOWN.md)):

1. **Fetch retry** (within one run) — the runner's bounded `max_attempts` + timeout.
2. **Run retry / backoff** (across runs) — the state store's `apply_failure` pushes `next_run`
   out exponentially; the scheduler simply stops seeing the provider as due until then.
3. **Permanent failure** — the scheduler auto-disables a provider whose consecutive failures
   exceed a metadata-derived cap.

**Circuit breaker** — the store opens the circuit at the failure threshold and sets a cooldown
via `next_run`. When the cooldown passes, the provider becomes due again and the scheduler
dispatches it as a single **half-open probe**; the outcome closes it (success) or re-opens it
with a longer backoff (failure). No provider is ever hammered while open.

## Graceful shutdown & restart

- **Shutdown** stops the loop, then drains the dispatcher: queued and in-flight jobs finish
  before it returns (`graceful=True`). Provider state and checkpoints are persisted by the
  runner on *every* job, so nothing is lost.
- **Restart** reopens the durable stores and calls `bootstrap()` — which is **idempotent**, so
  existing state (run counts, `next_run`, circuit, checkpoints) is preserved and the engine
  resumes exactly where it left off. Verified live: `bootstrap_new=0`, `due_after_restart=0`,
  catalog and health intact.

## Observability

- **Heartbeat**: uptime, tick count, last tick, workers alive/idle, queue depth, running providers.
- **Metrics**: providers executed, currently running, queue depth, retries, probes, success/
  failure rate, average execution, throughput/min, events/min, fleet health.

## Future migration to distributed workers

The `Dispatcher` and `JobQueue` are the seams. Today: `InProcessDispatcher` + `AsyncioJobQueue`
(one process, asyncio concurrency). Tomorrow, when provider count or freshness SLA demands it:
implement `Dispatcher`/`JobQueue` over Redis/Celery/RabbitMQ/SQS/Kafka and inject it — **the
Scheduler, Worker, metadata, and policy code are unchanged**, because the scheduler only ever
calls `submit`/`drain`/`shutdown` and never knows which queue exists. Scheduling *policy* is
already decoupled from execution *mechanism*.
