# Worker Engine

The execution side of Phase 3D: how a decided `Job` becomes a completed ingestion run.
Covers the Dispatcher, the Worker, and the Job Queue — and the seams that let the
in-process engine become a distributed one without changing scheduling logic.

## Separation of concerns: decide ≠ run

- The **Scheduler** decides (produces `Job`s) — see [SCHEDULER_BREAKDOWN.md](SCHEDULER_BREAKDOWN.md).
- The **Dispatcher** runs them through a pool of **Workers**.
- The **Job Queue** sits between, so the two sides never touch each other's internals.

The scheduler calls only `dispatcher.submit(job)` / `drain()` / `shutdown()`. It never sees
the queue or the workers — that's what makes the execution backend swappable.

## Worker (`worker.py`)

A worker executes **exactly one provider** and nothing more:

1. Resolve `job.provider_id` → plugin via the Capability Registry (drop unknown/stale jobs).
2. Call the **frozen** `run_ingestion(plugin, repo, state_store, now)`.
3. Emit a **structured log** (provider, result, events, duplicates, rejected, duration, probe,
   retry, errors) and return a typed `WorkerResult`.

**It deliberately does not** re-implement timeout, fetch-retry, or state updates — those already
live inside `run_ingestion`. Duplicating them would drift from the frozen pipeline. The worker
is the *envelope*, not a second pipeline.

## Dispatcher (`dispatcher.py`)

`InProcessDispatcher` is a fixed pool of asyncio worker loops:

- `start()` spawns `concurrency` loops; each blocks on `queue.get()`.
- Each loop runs the handler (the Worker) for one job, then `task_done()`.
- **Global concurrency limit** = pool size — at most that many jobs run at once.
- **Failure isolation** — a handler exception is caught and logged inside the loop; the loop
  and the pool survive. One bad provider can't take down execution.
- `drain()` = `queue.join()` — waits until every submitted job has finished.
- `shutdown(graceful=True)` drains first, then cancels the idle loops (they're blocked on
  `get()`, so cancellation is clean); `graceful=False` cancels immediately.
- `stats()` exposes workers / running / idle / queue-depth for the heartbeat.

The `Dispatcher` ABC is the migration seam: a `CeleryDispatcher` / `RedisDispatcher` /
`SqsDispatcher` implements the same four methods and is injected into the engine — **no
scheduler or worker change**.

## Job Queue (`job.py`)

`JobQueue` is a four-method contract (`put` / `get` / `task_done` / `join` + `qsize`).
`AsyncioJobQueue` wraps `asyncio.Queue` for the single-process engine. A distributed queue
(Redis Streams, RabbitMQ, SQS, Kafka) implements the same contract; the dispatcher and
scheduler are oblivious to which one is present.

## Concurrency, end to end

| Control | Mechanism |
|---|---|
| Global concurrency | dispatcher worker-pool size |
| Per-provider concurrency (=1) | engine in-flight set (scheduler excludes running providers) |
| Per-provider rate | `RateLimiter` min-interval, checked at scheduling time |
| Backpressure | bounded queue (optional `maxsize`) + `drain()` |

## Lifecycle & restart

Workers hold **no durable state** — everything is persisted by the runner into the frozen
stores on every job (provider state, checkpoints, catalog rows). So a worker or the whole
process can die and restart with zero loss: the engine re-bootstraps (idempotent) and the
persisted `next_run`/circuit/checkpoints resume the schedule exactly. This statelessness is
also precisely what makes the future move to distributed workers safe — a job can run on any
worker, on any host, because the truth lives in the stores, not the worker.

## Future: distributed execution

```
today:     Scheduler → AsyncioJobQueue → InProcessDispatcher → asyncio Workers (1 process)
tomorrow:  Scheduler → DistributedQueue → QueueDispatcher     → Worker processes (N hosts)
```

The change is **one injected dependency** (the dispatcher/queue implementation). Because
workers are stateless and idempotent (content-hash upserts, checkpointed sync), horizontal
workers need no coordination beyond the queue and the shared stores. The scheduling policy —
the actual intelligence — moves across unchanged.
