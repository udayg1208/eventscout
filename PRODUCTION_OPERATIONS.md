# Production Operations — Phase 7B

The production control plane. 7A stops at a staged `PromotionPlan`; 7B is everything after it —
safely promoting approved providers into the live ecosystem, continuously monitoring them,
automatically rolling back on failure, and learning from real performance to calibrate future
onboarding. This is **controlled autonomous operations**, not autonomous publishing: every provider
earns production through a canary, and any hard failure withdraws it non-destructively.

Code: `backend/app/operations/` (new, self-contained). **Additive and reuse-only** — it reuses the
Provider State Store (health), the scheduler's rate utility, and 7A's `PromotionPlan`, and modifies
nothing in Search, the Event catalog, the Repository, the Discovery Engine, provider
implementations, the frontend, or API contracts.

## The controlled promotion flow

```
PromotionPlan
   │
   ▼  preflight validation      (never bypassed)
REGISTERED → SCHEDULED          (ProductionRegistration + ScheduleConfig — control-plane records)
   │
   ▼  health initialized        (a ProviderState row, via the reused Provider State Store)
CANARY  ── small mock sync ──▶  health evaluation
   │                               │
   ├── healthy ───────────────────┴──▶ ACTIVE ── continuous monitoring ──▶ (auto-rollback on failure)
   └── unhealthy / hard failure ─────▶ ROLLED_BACK   (disabled, history kept — never deleted)
                                              also: FAILED_PREFLIGHT
```

## Package

```
app/operations/
  registry.py     ProductionState (9), ProductionRegistration (+ transition history) — additive record
  scheduler.py    ScheduleConfig from a plan (reuses scheduler.min_interval_seconds + RetryPolicy)
  production.py   preflight(); CanaryMetrics/Thresholds/Result; evaluate_canary; CanarySync + MockCanarySync
  health.py       HealthTracker + HealthSnapshot — REUSES the Provider State Store's transitions
  rollback.py     RollbackReason/Decision; evaluate_rollback; RollbackEngine (non-destructive)
  feedback.py     OutcomeRecord (predicted vs observed) → FeedbackSignals
  learning.py     learn() → LearningReport + CalibrationModel; apply_calibration (pure)
  analytics.py    build_operations_analytics — promotion/canary/rollback/precision/calibration
  engine.py       OperationsEngine — orchestrates promote / continuous_sync / learn / analytics
  interfaces.py   future seams: RealCanarySync, MetricsCollector, OnboardingCalibrator (all deferred)
  store.py        OperationsStore (ABC + InMemory + SQLite) — production + 4 append-only history streams
```

## Canary philosophy

**Every provider starts in CANARY** — never straight to ACTIVE. A canary is a *small first sync*
whose result is evaluated before the provider serves the live ecosystem:

- **fetch success** — did it fetch at all?
- **parse quality** — did what it fetched parse cleanly? (`valid / fetched`)
- **duplicate rate** — is it mostly re-runs of events we already have?
- **new event rate** — did it actually produce new events?
- **latency** — is it fast enough to schedule?
- **failures** — did the sync error out?

Only a canary that clears every threshold earns ACTIVE; anything else rolls back. This bounds the
blast radius: a bad provider costs one small sync, not a place in the live rotation. In 7B the
canary sync is a deterministic `MockCanarySync` (no network, no real provider); the real
runner-backed canary (`RealCanarySync`, reusing the Phase 3C ingestion sandbox) is the deferred
seam — the evaluation logic is identical either way.

## Rollback — automatic, safe, non-destructive

`evaluate_rollback` fires on a hard failure signal: failures over threshold, a **duplicate
explosion**, **zero new events**, **spam**, or **parser failure**. On rollback the engine:

1. marks the registration `ROLLED_BACK` (keeping its full transition history),
2. **disables** the provider in the Provider State Store — reusing the store's own mechanism to
   exclude it from scheduling — rather than deleting anything,
3. appends a rollback record (reason + detail + timestamp) to the append-only rollback stream.

**Nothing is ever deleted.** A rolled-back provider can be re-evaluated later; its history is the
audit trail. Rollback runs at the canary *and* continuously: an ACTIVE provider whose later sync
degrades is withdrawn automatically (demonstrated live — a healthy provider that later returns all
duplicates and zero events rolls back on the spot).

## Health monitoring (reuses the Provider State Store)

`HealthTracker` records every canary/continuous sync **through the existing `ProviderStateStore`**
(`update_after_run` / `update_after_failure` — the same locked, pure transitions the ingestion
runner uses), so uptime, failure streaks, circuit state, and rolling averages come from
battle-tested code. Operations-specific signals the ProviderState schema doesn't carry — parse
quality, duplicate %, freshness, success trend — are tracked alongside and rolled into a
`HealthSnapshot` (uptime, latency, freshness, event quality, duplicate %, failures, retries, trend).

## Continuous learning → confidence calibration

The point of operating is to *get better at onboarding*. `feedback.py` pairs each provider's
onboarding **prediction** (confidence, band, sandbox verdict, approval route) with its production
**observation** (healthy? duplicate rate? quality? rolled back?) into an `OutcomeRecord`.
`learning.py` buckets predicted confidence and measures the observed success rate per bucket — where
prediction and reality diverge is where the confidence model is mis-calibrated. See
**[CONTINUOUS_LEARNING.md](CONTINUOUS_LEARNING.md)** for the full loop.

Crucially: **no ML, only analytics.** The `LearningReport` is explainable bucketed arithmetic, and
the `CalibrationModel` it produces (a per-feed-type confidence nudge) is applied by a *pure*
function (`apply_calibration`) that a future onboarding integration can consume. 7B **produces** the
calibration; wiring it back into 7A is the deliberate, separately-approved `OnboardingCalibrator`
seam.

## Operational safety

- **Preflight is never bypassed** — a plan with an undetermined provider type or an insane refresh
  interval fails before anything is registered.
- **Canary-gated** — production is earned by a passing canary, never granted on promotion.
- **Auto-rollback** at canary and continuously, on explicit hard signals.
- **Non-destructive** — rollback disables and records; it never deletes history.
- **Deterministic + explainable** — every state transition, canary metric, rollback reason, and
  calibration bucket is recorded and inspectable; no ML, no randomness, no network.
- **Reuse over reinvention** — health and retry semantics come from the existing Provider State
  Store, so operations can't drift from the ingestion runner's behavior.

## Live demonstration (deterministic, no network)

`spikes/p7b_operations.py` — 6 plans through the control plane:

```
gdg.community.dev [rss]             → ✔ ACTIVE
fossunited.org    [ics]             → ✔ ACTIVE   (later degrades in continuous monitoring → ROLLED BACK)
reactindia.io     [structured_html] → ✔ ACTIVE
sketchy-events.io [crawl_pending]   → ✘ ROLLED BACK   (dup explosion + zero events + failures)
broken-feed.net   [rss]             → ✘ ROLLED BACK   (parser failure: parse_quality 0.20)
undetermined.com  [manual]          → ⊘ FAILED PREFLIGHT

LEARNING  sample=5  calibration_error=0.388
  conf [0.60,0.72) predicted 0.70 observed 0.00 Δ-0.70   ← over-confident
  conf [0.85,1.01) predicted 0.87 observed 1.00 Δ+0.13
  suggested adjustments: {rss:-0.20, ics:-0.20, jsonld_event:+0.18, search_result:-0.20}
ANALYTICS  active 2 · rolled_back 3 · canary_success 0.40 · rollback_rate 0.60 · discovery_precision 0.33
  history (nothing deleted): canary=5 rollback=3 learning=1
```

The learning report honestly shows this sample was *over-confident* on most feed types (predicted
high, observed rollbacks), and calibration nudges those confidences down for next time.

## Testing

`tests/test_operations.py` — **14 deterministic tests, no network**: preflight pass/fail, canary
metrics + evaluation, promote→active with full history, failed-preflight (no canary), rollback on
bad canary (non-destructive, provider disabled not deleted), each rollback trigger, health snapshot
(reusing ProviderState), continuous-sync rollback of a live provider, feedback signals, learning
calibration (detects over-confidence, nudges down), `apply_calibration`, analytics rates, and an
end-to-end lifecycle with SQLite persistence + all four history streams. Full backend suite: **469
tests**.

## Scaling to 100,000 providers

- **Canary cost is bounded and parallel** — each provider's canary is one small independent sync;
  throughput scales with workers, and a bad provider never costs more than its canary.
- **Health reuses the storage-agnostic Provider State Store** (SQLite → Postgres with no app
  change); `due_providers` already scales the scheduling read.
- **Rollback is O(1) set membership** (disable a provider_id) — no scan, no cascade.
- **Learning is bucketed arithmetic over outcomes** — linear in provider count, and naturally
  windowed (calibrate over the last N outcomes per feed type).
- **The four history streams are append-only** — index-friendly and archivable; nothing is mutated
  in place except the registration's current state.
- **Calibration makes scale safer, not riskier** — as thousands of providers run, per-feed-type
  calibration tightens the confidence bands that decide auto-approval upstream, so the fleet
  self-corrects instead of drifting.

## Critical self-review

**Honestly true**
- Production is genuinely gated: preflight → canary → health, with auto-rollback at canary and
  continuously. Rollback never deletes. Health is the reused, tested Provider State Store.
- Learning is real, explainable calibration (predicted-vs-observed buckets) and correctly flags
  over-confidence in the live demo.

**Weaknesses / deferred**
1. **The canary doesn't actually fetch.** `MockCanarySync` returns injected metrics — it proves the
   *control plane*, not real provider behavior. A provider that looks healthy in the mock could fail
   a real fetch. `RealCanarySync` (runner + sandbox, needs network) is the deferred seam.
2. **The calibration loop is open, by design.** 7B *produces* a `CalibrationModel` but does not feed
   it back into 7A's confidence (that would modify onboarding). Until the `OnboardingCalibrator`
   seam is wired (separately approved), "improves future decisions" is one manual step away.
3. **No real production registration.** "Register provider / scheduler configuration" produces
   control-plane *records* (`ProductionRegistration`, `ScheduleConfig`) — it does not inject a
   provider into the frozen ingestion registry or enqueue it into the live scheduler (those are
   provider-implementation + registry changes, out of scope). ACTIVE here means "canary-cleared and
   recorded as live-eligible," not "currently being fetched by the running scheduler."
4. **Health vs rollback can disagree cosmetically.** A provider whose fetch succeeds but parses
   poorly shows `health_status=healthy` (the sync worked) yet is `ROLLED_BACK` (quality gate) — two
   different lenses (raw sync success vs operations quality). Correct, but needs reading carefully.
5. **Calibration is small-sample and un-smoothed.** Deltas are clamped but not confidence-weighted
   by sample size; a handful of outcomes can swing a feed-type nudge. Real calibration needs volume
   and decay.
6. **Thresholds are reasoned, not tuned.** Canary and rollback thresholds are sensible defaults, not
   fit against labeled production outcomes.

## Where Phase 8 begins (NOT this phase)

7B closes the discover → onboard → operate → learn loop with a human still holding the production
key (the real registration + the calibration feedback are seams, not switches). Phase 8 —
autonomous discovery optimization, AI-driven query generation, and real production search providers
— would let the system *act* on what it learns without a human in each loop. That is a materially
larger grant of autonomy and requires explicit approval.

---

**Status:** 7B complete. Additive; frozen systems untouched; 469 tests green; canary-gated,
auto-rollback, non-destructive, deterministic, analytics-only learning. **Stopping here — Phase 8
NOT started.**
