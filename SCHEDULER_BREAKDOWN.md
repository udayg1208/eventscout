# Scheduler Breakdown

How the Intelligent Scheduler decides **what runs and in what order** — entirely from
declared provider metadata + persisted state, with **no provider-specific logic** (no
`if provider == …`, no hardcoded refresh/retry/priority rules). Code:
`backend/app/scheduler/scheduler.py`.

## Input: `due_providers(now)`

The scheduler starts from the Provider State Store's indexed query:

```
enabled = 1  AND  (next_run_at IS NULL OR next_run_at <= now)   ORDER BY next_run_at
```

This is **O(due)**, not O(providers) — the store returns only what's actually due, ordered
by soonest (never-run first). Backoff and circuit cooldowns are already baked into
`next_run_at` by the store, so "not due yet" transparently covers "backing off" and
"circuit cooling down." This is what lets the loop **sleep instead of polling everything**.

## Per-provider filtering (each a pure decision from metadata/state)

For each due provider, in order:

1. **In-flight guard** — if the provider is already running (engine's in-flight set), skip.
   Enforces **per-provider concurrency = 1** without a lock.
2. **Unknown provider** — if it isn't in the Capability Registry, drop it. The registry is the
   source of truth; a stale state row never runs.
3. **Permanent failure** — if `consecutive_failures ≥ max_consecutive_failures` (a configured
   cap; `None` = never), **auto-disable** the provider and skip. This is the "give up" end of
   the retry spectrum.
4. **Rate limit** — if it ran within `60 / rate_limit_per_minute` seconds, skip until a later
   tick. Belt-and-suspenders on top of `next_run` spacing.
5. Otherwise **emit a `Job`**, labelled `is_probe` (open circuit) and `is_retry` (had prior
   failures) for metrics/logging.

## Execution order (priority)

Jobs are sorted by a pure function of **declared metadata only**:

```
execution_priority(plugin) = (refresh_interval_seconds, -expected_volume)   # ascending
```

Fresher-cadence providers run first; ties break toward higher expected volume. No identity,
no hand-maintained priority table. (An explicit `priority` field is the natural future
addition; today it's derived to respect the frozen Plugin System.)

## Retry strategy — three layers, zero duplication

| Layer | Where it lives | What it does |
|---|---|---|
| **Fetch retry** | Ingestion Runner (frozen) | `max_attempts` fetch attempts + `timeout` per attempt, within one run |
| **Run backoff** | Provider State Store (frozen) | `apply_failure` sets `next_run = now + min(base·2ⁿ, max)`; the scheduler stops seeing it as due |
| **Permanent failure** | Scheduler (this phase) | auto-disable after a metadata-derived consecutive-failure cap |

The scheduler adds **only** the permanent-failure policy. It never recomputes backoff — it
reads the `next_run` the store already set. All timing knobs come from the plugin's
`RetryPolicy` (`failure_threshold`, `base/max_backoff`, `circuit_cooldown`, `refresh_interval`).

## Circuit breaker

The circuit lives in the state store (`CLOSED → OPEN → HALF_OPEN`); the scheduler drives the
*probe*:

- **CLOSED** → runs on its normal refresh cadence.
- Failures accumulate; at `failure_threshold` the store sets **OPEN** and pushes `next_run` out
  by the cooldown → the provider is not due, so it's never hammered.
- When the cooldown elapses the provider becomes due again with `circuit = OPEN`; the scheduler
  dispatches it as a single **HALF_OPEN probe** (`Job.is_probe = True`), and the in-flight guard
  ensures only one probe runs.
- The runner's outcome resolves it: **success → CLOSED** (`apply_success`), **failure → OPEN**
  again with a longer backoff. Fully automatic: open, recover, probe, close.

Verified: `test_engine_circuit_opens_probes_and_recovers` walks the full cycle deterministically.

## Efficiency at 300–1000+ providers

- **No busy-wait**: the loop sleeps one tick interval and wakes instantly on shutdown.
- **No O(n²)**: due selection is a single indexed query; filtering is O(due); sorting is
  O(due log due). Nothing scans the whole fleet every tick.
- **No polling everything**: only due rows are read; the vast majority of providers (not due)
  cost nothing per tick.
- The tick interval is the scheduling granularity; freshness is tiered in minutes/hours, so a
  coarse tick (seconds) is ample. (Sleeping *exactly* until the next due time is a future
  optimization needing a `next_due_at()` store method.)
