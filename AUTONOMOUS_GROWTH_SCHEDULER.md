# Autonomous Growth Scheduler — Phase 10F

The discovery intelligence (10A–10E) is complete. This phase makes it **autonomous**: a control plane
that continuously grows EventScout by looping the *existing* engines. It redesigns nothing and drives
everything through one seam.

Code: `backend/app/growth/` (new package — additive). It **reuses** 10C organizers, 10D ecosystem
expansion, 10E seed validation, the D1 Discovery Inbox, and (as observation points) 7A onboarding and
7B production — and **modifies none of them** (D1–D4, 7A–7B, 8A–8D, 9A, 10A–10E, Search, Repository,
Registry, Scheduler, Providers, Catalog, API, Frontend). No browser, no LLM, no network (the discovery
fetcher/searcher are injected — fixtures in tests, real in production). No automatic
provider/weight/query/catalog changes.

## The loop

```
        ┌──────────────────────── Growth Intelligence ─────────────────────────┐
        │  (freshness · opportunities · budget · learning · metrics)            │
        ▼                                                                       │
   Known Organizers ─► 10D Expansion ─► Discovery Seeds ─► 10E Validation ─► Discovery Inbox
        ▲                                                                       │
        │                                                                       ▼
        └──── new organizers ◄── 7B Production ◄── 7A Onboarding (human-gated) ◄┘
```

Each edge is an existing engine. 10F is the **scheduler + planner + queue + intelligence** that decides
*what to run, when, and within what budget* — turning the on-demand loop of 10E into a self-driving one.

## Architecture — a control plane over a `GrowthStep` seam

Like the 9A orchestrator, 10F is engine-agnostic. Every activity is a `TaskKind` mapped to a
`GrowthStep` (`StepContext → StepOutcome`). The adapters in `steps.py` call the real engines; tests
inject mocks. The five activities:

| TaskKind | Step reuses | Produces |
|---|---|---|
| `expansion` | 10D `EcosystemExpansionEngine.expand_from(10C)` | new Discovery Seeds → a validation follow-up |
| `validation` | 10E `SeedValidationEngine.validate_batch` | inbox candidates → an onboarding follow-up |
| `onboarding` | observes inbox (human-gated 7A) | promotions **only** via an explicit approval hook |
| `production_monitor` | observes 7B health | failure signals |
| `organizer_refresh` | 10C `ingest(url, html)` | a refreshed organizer profile |

A tiny `SeedBuffer` threads state between stages (expansion fills it, validation drains it).

## The eleven components

1. **Growth Scheduler** (`scheduler.py`) — each `TaskKind` runs on a cadence
   (continuous/hourly/daily/weekly/manual). On each tick it compares an **injectable clock** to when
   each kind last fired and enqueues the due ones. Cadence gating means periodic work re-runs exactly
   once per interval.
2. **Growth Planner** (`planner.py`) — chooses what runs next. It *refills* the queue from the
   freshness engine (stale entities) and the opportunity engine (growth openings), then *selects* the
   single highest-priority task that is **affordable** (budget) and **unblocked** (don't validate with
   no seeds, don't onboard with an empty inbox). Every decision returns a reason.
3. **Growth Queue** (`queue.py`) — a persistent priority queue with **deduplication** (one active task
   per kind+target; a completed key stays occupied so opportunities can re-propose idempotently),
   **leases** (a leased task is invisible until it completes or the lease expires), **cooldown
   retries**, and **abandonment** at `max_attempts`. Run-counter driven → fully deterministic.
4. **Freshness Engine** (`freshness.py`) — tracks the age of every organizer / seed / validation /
   provider / expansion against a per-kind TTL and *recommends* refreshes for the stale ones. Nothing
   is ever deleted — an aged entity is refreshed, not removed.
5. **Opportunity Engine** (`opportunity.py`) — six deterministic detectors over a graph snapshot: new
   cities (seeds reference a city with no organizer), inactive ecosystems, stale organizers, seasonal
   windows (Hacktoberfest→October, DevFest→November, …), recurring conferences predicted to return, and
   missing university coverage. Each opportunity explains itself and becomes a `GrowthTask`.
6. **Budget Engine** (`budget.py`) — allocates the four rate-limited resources (search / crawl /
   validation / onboarding), **clamping every spend to what remains** so the loop can never exceed a
   free-tier envelope, and refills on a period via the clock.
7. **Learning Engine** (`learning.py`) — observes accepted/rejected seeds, promotions, and production
   failures and emits **recommendations only** (expand more / explore less / revisit later / maintain),
   each with its evidence. It **never** mutates weights, queries, budgets, or the queue.
8. **Growth Metrics** (`metrics.py`) — new organizers/seeds/validated/promoted/rejected, plus growth
   velocity (accepted per cycle), ecosystem coverage (cities covered ÷ known), and expansion efficiency
   (accepted ÷ seeds generated). Also detects **steady state**.
9. **Dashboard Model** (`GrowthSnapshot`) — a read-only picture: backlog, queue, opportunities,
   budgets, health, freshness, recommendations, metrics. No UI.
10. **Safety** — the loop never auto-modifies providers, auto-changes weights, auto-edits queries, or
    auto-deletes organizers. Onboarding promotes nothing without an explicit human-approval hook.
    Everything is explainable (reasons on tasks, opportunities, recommendations; a per-cycle audit).
11. **Stores** (`store.py`) — `GrowthStore` ABC + `InMemoryGrowthStore` + `SQLiteGrowthStore` persist
    the queue, freshness, and an append-only cycle audit so an autonomous run can resume.

## The engine cycle

`GrowthEngine.run_cycle()`: refill budgets → reclaim expired leases → scheduler enqueues due work →
planner folds in freshness + opportunities → planner selects the best affordable, unblocked task → run
its step → charge the budget, complete the task, enqueue follow-ups, touch freshness, record metrics,
feed learning → audit. `run()` repeats until a **steady state** (a window of cycles where the planner
finds nothing to do) or a cycle cap.

## Live demonstration

`backend/spikes/p10f_growth.py` (fixtures, no network) grows EventScout from **one** organizer:

```
WAVE 1 — cold start
  cycle  1: expansion          seeds+8                 inbox=0 backlog=5
  cycle  2: validation         val8 acc6 rej2          inbox=6 backlog=11
  cycle  3–9: expansion        (opportunity-driven, one per new city)
  cycle 10: onboarding         prom6                   inbox=6
  cycle 11: organizer_refresh
  cycle 13: production_monitor
  → steady state reached after 16 cycles

>>> 8 days later: new organizer 'GDG Hyderabad' ingested; 4 production failures observed <<<
WAVE 2 — react & regrow
  cycle 17: expansion  seeds+1   cycle 18: validation  cycle 21: production_monitor fail4
  → steady state reached after 8 cycles

FINAL METRICS: new_seeds 9, validated 9, promoted 6, rejected 3, efficiency 0.667
RECOMMENDATIONS: [revisit_later (4 failures), increase_expansion (high acceptance)]
INBOX: 6 candidates, discovered_by=validation, status=NEW
```

The loop cold-starts, stabilises, then **reacts** to a new organizer and to production failures on the
next wave — surfacing `revisit_later` without acting on it. (`new_organizers` stays 0 by design: 10F
does not mint organizers — new ones arrive only after onboarding→production, which is downstream and
gated.)

## Tests

`backend/tests/test_growth.py` — **128 tests, fixtures only, no network/browser/LLM**: models, the
queue (priority, dedup, force-revive, lease, reclaim, retry-cooldown, abandon, drain), the cadence
scheduler (due/not-due/manual/continuous/re-fire), freshness, all six opportunity detectors, the budget
engine (clamping + refill), the learning engine (every recommendation + recommendations-are-pure), the
planner (priority, backlog gating, budget gating, cooldown), metrics + steady state, the step seam
(**including the real 10C→10D→10E adapters** and an end-to-end real loop into the inbox), the engine
(cycle execution, budget charging, follow-ups, freshness touch, metrics/learning, run-to-steady, safety:
no auto-promotion), and both stores. Full backend suite: **1033 passing**.

## Honest self-review

**Truly true**
- Every growth activity runs the *real* frozen engine through the step seam; the loop genuinely
  cold-starts from one organizer and drives real candidates into the *existing* inbox. Budgets are hard
  ceilings (every spend is clamped). Learning only recommends. Onboarding promotes nothing without an
  explicit human hook. Every task, opportunity, and recommendation is explainable, and every cycle is
  audited.

**Weaknesses / limitations**
1. **It is tick-driven, not a running daemon.** `run_cycle`/`run` advance the loop when *called*; the
   always-on scheduler (`ContinuousDaemon`) that would call them on a wall-clock tick — with supervised
   scheduling, back-pressure, and an operator kill-switch — is a **deferred seam** (`NotImplementedError`).
   "Autonomous" describes the control logic, not an unattended process.
2. **Onboarding and production are observation points, not integrations.** The loop schedules and
   *observes* them; the live human-gated 7A hand-off (`LiveOnboardingBridge`) and the real 7B health
   feed (`LiveProductionMonitor`) are deferred seams. So the loop closes *conceptually* — verified
   candidates reach the inbox — but the inbox→onboarding→production→new-organizer leg is not wired here
   (by design: those create providers).
3. **Opportunity signals are supplied by the wiring, not mined.** The engine detects opportunities from
   an `OpportunitySignals` snapshot; assembling that snapshot faithfully (which cities, which dormant
   ecosystems, which recurring series) is the caller's job and, in the demo, is a best-effort read of
   graph state. Garbage-in signals → misdirected expansion.
4. **Budget clamping is coarse.** A spend is clamped to what remains, but a single step may still do
   more work than one budget "unit" implied (the planner authorises 1 unit; the step reports its actual
   cost, which is then clamped). Fine-grained pre-authorisation per unit of work is future work.
5. **Thresholds are hand-tuned, not learned.** Cadences, TTLs, priorities, budget limits, and the
   learning thresholds are reasonable defaults, not calibrated from outcomes. The learning engine
   surfaces *when* to change them; a human still does.
6. **Steady state = an idle window, not provable convergence.** The loop stops when the planner finds
   nothing to do for N cycles. A perpetually-scheduled task with no backlog (validation waiting for
   seeds) is correctly ignored, but "steady" is an operational heuristic, not a fixpoint proof.
7. **Coverage/velocity are within-run counters.** Metrics reset per process; there is no long-horizon
   store of growth history beyond the SQLite cycle audit, and coverage depends entirely on the cities
   the wiring reports as "known".

## Future work (NOT this phase)

`interfaces.py` marks the seams: `ContinuousDaemon` (the always-on driver), `LiveOnboardingBridge` (real
7A hand-off), `LiveProductionMonitor` (real 7B health). Wiring those — behind an operator switch, with
the safety rules enforced at the boundary — is what turns this control plane into a live service.

---

**Status:** 10F complete. Additive; every frozen system untouched; **1033 tests green**; deterministic;
no browser/LLM/network; no automatic provider/weight/query/catalog changes. See
[CONTINUOUS_GROWTH_ARCHITECTURE.md](CONTINUOUS_GROWTH_ARCHITECTURE.md) for the control-plane view.
**Stopping here — Phase 11 NOT started.**
