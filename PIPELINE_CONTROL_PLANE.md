# Pipeline Control Plane — Phase 9A

A companion to [AUTONOMOUS_ORCHESTRATOR.md](AUTONOMOUS_ORCHESTRATOR.md), focused on the *idea*: why
EventScout needs a control plane separate from its discovery engines, how the pipeline is expressed
as data, how it scales, and where the distributed future (9B) plugs in.

## Data plane vs. control plane

Phases D1–8E built the **data plane** — engines that *do* discovery (search, crawl, expand, extract,
onboard, promote). Each is excellent in isolation and knows nothing about *when* it should run, *how
often*, *with what budget*, or *what to do when it fails*. 9A is the **control plane**: the thin,
always-on layer that answers those questions and turns a pile of capabilities into a system that runs
itself. The separation is deliberate — the engines stay simple and frozen; all orchestration policy
lives in one place you can reason about, test, and change without touching a single engine.

## The pipeline is data

The canonical loop is a list of `StageSpec`s, not a hardcoded sequence:

```
StageSpec(SEARCH_DISCOVERY, schedule=hourly,     priority=9.0, trigger=schedule, produces_for=[WEB, EXPANSION])
StageSpec(EXPANSION,        schedule=continuous, priority=8.0, trigger=backlog,  produces_for=[SOCIAL, RENDERED, INBOX])
StageSpec(ONBOARDING,       schedule=continuous, priority=5.0, trigger=backlog,  produces_for=[PRODUCTION_OPS])
…
```

Everything the planner needs is here: **when** (schedule + trigger), **how important** (priority),
**what it costs** (budgets), and **what it feeds** (`produces_for`, the seed-flow edges). The
Search→…→Optimization order is an *emergent property* of these numbers plus backlog fan-out — change
the data and the behaviour changes. Want rendered discovery to lead? Raise its priority. Want catalog
refresh hourly? Change its schedule. No control-flow edits.

## How work flows

A stage's `StageOutcome` carries `produced_seeds` and counts. The state manager fans those to each
downstream stage's **backlog** (and seed list). Backlog-triggered stages become eligible only when
they have work; schedule-triggered stages fire on cadence. So the pipeline is **event-driven**: a
search result becomes an expansion seed becomes a rendered candidate becomes an inbox entry becomes an
onboarding job — each step pulled forward when its input exists and its priority wins the cycle.

## Budgeting as the ₹0 governor

The whole platform is ₹0-budget, so the control plane treats budget as a first-class, six-dimensional
resource (crawl / search / AI / page / provider / depth). The planner grants against what remains,
**shrinks grants as a pool depletes**, and defers stages whose budget is spent. This is what lets the
loop "run forever" safely — it self-throttles toward the cheap stages (reading inbox, onboarding,
catalog) as the expensive quotas (search, AI, crawl) drain, then resumes them when the daily ceiling
resets. The demo shows the provider budget falling 50→8 while the loop keeps making progress.

## Health-driven adaptation

Each stage reports `healthy | degraded | failed | paused`, and health feeds straight back into
planning: degraded stages are penalised, paused stages skipped, failed stages retried-then-dead-
lettered. The pipeline **routes around** a struggling stage automatically rather than stalling — a
crashed rendered extractor dead-letters and the inbox/onboarding/catalog stages keep flowing.

## Scaling strategy

- **Vertical (9A, now):** one process, one stage per cycle, in-memory leases. Correct and cheap;
  throughput is bounded by cycle rate. Budgets + priorities keep it within the free tier.
- **Concurrency within a process:** the lease model already supports it — distinct stages hold
  distinct leases, so several *could* run at once. 9A executes one per cycle for fairness and
  determinism; lifting that is a small change guarded by the same leases.
- **Horizontal (9B):** many workers sharing one pipeline. The pieces are already shaped for it — a
  lease *is* a distributed-lock primitive, a checkpoint *is* shared state, the DLQ *is* a durable
  failure log. What's missing is a **shared backend** for them.

## The distributed future (Phase 9B)

`interfaces.py` marks the seams, each raising `NotImplementedError`:
- **`DistributedLeaseBackend`** — move leases from in-memory to Redis/Postgres so N workers coordinate
  one pipeline without double-running a stage (the TTL + steal-on-expiry semantics already match).
- **`TaskQueue`** — a durable cross-process queue so a worker can enqueue "expand these seeds" for any
  peer to pick up, replacing the in-process backlog with a real work queue.
- **`WorkerNode`** — a process that leases stages from the cluster, runs them, reports outcomes, and
  heartbeats; the orchestrator becomes a scheduler over many of these.

9A is intentionally the single-node version of exactly this design, so 9B is a backend swap plus a
worker loop — not a rewrite.

## Honest self-review (control-plane view)

- **The abstraction is real, the distribution is not.** 9A cleanly separates policy from engines and
  its primitives (lease, checkpoint, DLQ, budget) are the correct distributed shapes — but it runs on
  one node with in-memory state. Calling it a "cluster" would be wrong; it's a cluster-*ready* single
  node.
- **Emergent ordering is a feature and a risk.** Deriving the sequence from priorities + backlog is
  flexible, but it means the order isn't guaranteed by construction — a bad priority/budget config can
  produce a surprising schedule. The pipeline data needs the same care as code.
- **Idempotency is assumed, not enforced.** Because recovery replays whole stages, every engine
  adapter must be safe to re-run. The control plane can't guarantee that; it's a contract the data
  plane must honour.
- **One process is one failure domain between checkpoints.** Durability is per-cycle; work done inside
  a cycle that crashes before checkpoint is replayed, not resumed. Good enough for ₹0/single-node,
  insufficient for strict exactly-once.
- **Mock-validated.** By design the 9A tests/spike prove the *control logic*, not the integration with
  live engines and their real latencies/failures. That integration is the first thing 9B (or a wiring
  phase) must earn.

---

**Status:** 9A complete — additive, control-plane-only, deterministic, no browser/LLM/network; 580
tests green. **Stopping here — Phase 9B (Distributed Multi-Worker Discovery Cluster) NOT started.**
