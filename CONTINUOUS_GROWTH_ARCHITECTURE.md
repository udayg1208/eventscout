# Continuous Growth Architecture — Phase 10F

A companion to [AUTONOMOUS_GROWTH_SCHEDULER.md](AUTONOMOUS_GROWTH_SCHEDULER.md), focused on the *shape*:
why the growth loop is a control plane over frozen engines, how it stays convergent, and where the
always-on version attaches.

## Two control planes, two altitudes

EventScout now has two orchestration layers, and they do not overlap:

| | 9A Orchestrator | 10F Growth Scheduler |
|---|---|---|
| Drives | the discovery *pipeline* (search→web→expansion→social→rendered→inbox…) | the growth *lifecycle* (organizers→expansion→validation→inbox→onboarding→production) |
| Unit | a pipeline stage (`StageRunner`) | a growth activity (`GrowthStep`) |
| Question | "run the discovery pipeline reliably" | "where should the ecosystem grow next, and when" |
| Horizon | one discovery cycle | continuous, cross-cycle growth |

10F sits *above* the discovery machinery. It doesn't fetch or parse; it decides which existing engine to
turn, on what cadence, within what budget — and learns from the results. Same design DNA as 9A (a
uniform seam, mockable steps, additive over frozen systems), a different altitude.

## Why a control plane, not a script

A naive "expand everything every hour" loop would (a) balloon combinatorially, (b) re-do settled work,
and (c) blow any free-tier budget. The control plane exists to impose four disciplines the raw engines
don't have on their own:

1. **Cadence** — the scheduler runs each activity on its own clock (validate hourly, expand daily,
   refresh weekly), so nothing runs more often than it should.
2. **Prioritisation under scarcity** — the planner picks *one* task per cycle: the highest-priority one
   that is affordable and unblocked. Scarcity (budget) and readiness (backlog) are first-class inputs.
3. **Idempotence** — the queue treats a completed key as occupied, so the opportunity and freshness
   engines can re-propose the same work every cycle without it ever re-running. Only the cadence gate
   (via the scheduler) revives a periodic task.
4. **Bounded curiosity** — freshness ages work back into the queue and opportunities open new frontiers,
   but budgets clamp the total and abandonment caps the retries.

## What keeps it convergent

The demo cold-starts from one organizer and reaches a steady state twice. Three brakes make that happen:

- **The validation gate (10E)** admits only verified candidates; noise is dropped, not propagated.
- **Idempotent dedup** means a settled target isn't re-worked until its cadence or TTL says so — so each
  wave adds *new* frontier, not repeats.
- **Steady-state detection** stops the loop when the planner finds nothing to do for a window of cycles.

A wave therefore expands the frontier, validates it, banks the winners, and quiesces — until something
*changes* (a new organizer, an elapsed cadence, an aged entity), which reopens exactly the affected
frontier and no more. That is the intended dynamic: **grow on change, rest otherwise.**

## The intelligence layer as feedback, not control

Freshness, opportunities, and learning form a feedback loop around the pipeline — but a deliberately
*advisory* one. Freshness and opportunities enqueue work (bounded, deduped, budgeted). Learning does
**not** touch anything: it reads outcomes and recommends a posture (expand more, explore less, revisit
later). The decision to retune cadences, weights, or budgets stays human. This is the core safety
stance: the loop can *act* on structural facts (this is stale, this city is uncovered) but only
*recommend* on judgment calls (we're rejecting too much — should we explore less?).

## Where the always-on version attaches

10F is tick-driven: something calls `run_cycle`. The `ContinuousDaemon` seam is where a supervised
wall-clock driver would live — and it is exactly the right place to enforce, at one boundary, every
safety rule: no auto provider changes, no auto weight edits, an operator kill-switch, and back-pressure
when budgets run low. The `LiveOnboardingBridge` and `LiveProductionMonitor` seams attach the
human-gated 7A and the real 7B health there too. Until then, the loop is a deterministic engine you step
— which is precisely what makes it testable.

## Honest self-review (architecture view)

- **The loop is closed in shape, open at two edges.** organizers→expansion→validation→inbox is real and
  tested end-to-end; inbox→onboarding→production→new-organizers is *scheduled and observed* but not
  wired (those create providers, which this phase must not do). So "continuous growth" is proven for the
  discovery half and designed-but-deferred for the promotion half.
- **Convergence is demonstrated, not guaranteed.** The brakes work in the demo and tests; there is no
  formal proof the loop can't thrash under adversarial signals (e.g. an opportunity source that keeps
  inventing new cities). Bounded budgets make thrashing *cheap*, not impossible.
- **The altitude separation is clean but untested against 9A running concurrently.** 10F and 9A are
  designed to not overlap, but this phase does not run them together; the interaction (both wanting
  budget, both touching the inbox) is future integration work.
- **Determinism is a feature and a limit.** Run-counter queues and injected clocks make every test
  reproducible — but real autonomy runs against wall-clock drift, partial failures, and concurrency the
  deterministic harness doesn't exercise. The daemon seam is where that reality gets confronted.

---

**Status:** 10F complete — additive control plane over frozen engines; deterministic; 1033 tests green;
no browser/LLM/network; no automatic provider/weight/query/catalog changes. **Stopping here — Phase 11
NOT started.**
