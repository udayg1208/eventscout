# Autonomous Growth Loop — Phase 10E

A companion to [SEED_VALIDATION_ENGINE.md](SEED_VALIDATION_ENGINE.md), focused on the *loop*: how seed
validation closes the discovery cycle, what makes it converge instead of explode, and where the
autonomous version plugs in.

## The loop

```
        ┌──────────────────────────────────────────────────────────────┐
        │                                                              │
   10C organizers  ──►  10D seeds  ──►  10E validation  ──►  Discovery Inbox (NEW)
   (real, extracted)   (hypotheses)    (verify → decide)    (VERIFIED / PARTIALLY)
        ▲                                                              │
        └──────────────────────  new organizers  ◄─────────────────────┘
                         (a verified inbox candidate, once crawled,
                          becomes a new 10C organizer → more seeds)
```

10C turns pages into a real Organizer Graph. 10D expands that graph into *hypotheses* — sibling
chapters, series instances, sponsor programs, campus clubs. 10E is the **filter that keeps the loop
honest**: it verifies each hypothesis against real fetched evidence and admits only the ones that hold,
into the *existing* Discovery Inbox. Those verified candidates, once discovered/onboarded downstream,
become new organizers — and the cycle repeats. The system grows itself, but only outward from
*confirmed* reality.

## Why it converges instead of exploding

10D can generate seeds combinatorially; a naive loop would balloon. Three brakes keep it convergent:

1. **Validation is a hard filter.** Most generated seeds are hypotheses; only VERIFIED / PARTIALLY reach
   the inbox. REJECTED (a reachable page that isn't the seed) and INSUFFICIENT (nothing found) do not —
   so noise is dropped at the gate, not propagated.
2. **Retry with abandonment.** A seed that can't be confirmed is retried a bounded number of times
   (cooldown between attempts) and then **abandoned** — it never becomes a permanent re-check cost.
3. **Inbox dedup.** Verified candidates upsert by URL key into the existing inbox (D1/D3/7A logic), so a
   source confirmed twice is one candidate, not two — the loop doesn't re-add what it already has.

The result: each turn of the loop adds *confirmed* sources and drops the rest, so the inbox grows with
signal, not with the full combinatorial fan-out.

## The four decision states as loop control

| Decision | Meaning | Loop effect |
|---|---|---|
| VERIFIED | strong real evidence | → inbox; becomes a future organizer |
| PARTIALLY_VERIFIED | reachable, some evidence | → inbox (flagged lower confidence); human/onboarding decides |
| INSUFFICIENT_EVIDENCE | couldn't confirm (transient) | retry with cooldown, then abandon |
| REJECTED | reachable but not the seed | dropped, terminal — noise removed |

## What to watch (metrics)

`ValidationMetrics` is the loop's health readout: **verification rate** (how many hypotheses hold up),
**acceptance rate** (how many reach the inbox), **rejection rate** (how much 10D noise the gate catches),
**duplicate rate** (how much the loop re-derives what it has), **average confidence**, and **average
evidence count**. A healthy loop shows a moderate verification rate (10D is speculative by design), a low
duplicate rate, and rising inbox counts across cycles. A rejection rate near 1.0 means 10D is generating
mostly noise (tighten its templates); a duplicate rate near 1.0 means the loop has saturated its current
neighbourhood (widen the seed graph).

## Autonomy — on demand now, scheduled later

10E validates a batch when called; it does not yet run itself. The `GrowthLoopScheduler` seam
(`NotImplementedError`) is where the continuous driver lives: on a schedule, pull the current 10C
organizers → run 10D expansion → validate the new seeds with 10E (cooldown-aware) → let the verified
inbox candidates flow to the *existing*, human-gated onboarding (7A). Nothing about that loop creates
providers or writes the catalog on its own — those remain deliberately downstream and gated.

## Honest self-review (loop view)

- **The loop is designed but not closed here.** Each edge (10C→10D, 10D→10E, 10E→inbox) is real and
  tested, and the shape is a genuine growth cycle — but 10E runs on demand; the autonomous scheduler that
  makes it *self*-driving is a deferred seam. Calling it "autonomous" describes the intent, not a running
  daemon.
- **Convergence depends on the filter's precision.** The brakes work only if validation actually
  distinguishes real from fake. Its biggest gap (see the engine doc) is that it confirms "an organizer
  exists at this URL" without cross-checking that it's *the* seed — so a mis-guessed URL that resolves to
  a different real community could feed the loop the wrong node.
- **Recall is search-bound.** Without the deferred `LiveSeedSearcher`, the loop only confirms seeds whose
  URLs it can guess; real ecosystems it can't find are abandoned. So the loop's *growth rate* is capped
  by a search integration not built in this phase.
- **The gate is honest about uncertainty.** PARTIALLY_VERIFIED exists precisely so the loop doesn't have
  to choose between "certainly real" and "discard" — it forwards the maybes to human-gated onboarding
  rather than pretending to certainty.

---

**Status:** 10E complete — additive, verification-only, into the existing inbox; deterministic; 905
tests green; no browser/LLM/network. **Stopping here — Phase 10F NOT started.**
