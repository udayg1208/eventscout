# Continuous Learning — Phase 7B

How EventScout learns from real production performance to make better onboarding decisions — without
training any ML model. This is the feedback loop that turns "we promoted this provider" into "we
now know how well our confidence predicted reality, and we've adjusted."

Companion to **[PRODUCTION_OPERATIONS.md](PRODUCTION_OPERATIONS.md)** (the control plane).

## The loop

```
                 ┌──────────────────────────────────────────────────────────┐
                 │                                                          │
   7A onboarding │  predicts: confidence, band, sandbox verdict, approval    │
        │        │                          ▼                               │
   PromotionPlan ─┴─▶ 7B promote → canary → ACTIVE / ROLLBACK                │
                                            │                               │
                                    observes: healthy? duplicate rate?      │
                                    quality? rolled back?                   │
                                            ▼                               │
                                   OutcomeRecord (predicted vs observed)     │
                                            ▼                               │
                                   LearningReport + CalibrationModel  ───────┘
                                   (per-feed-type confidence nudge)
                                            │  apply_calibration() — pure, future-wired
                                            ▼
                             better onboarding confidence next time
```

Every promoted provider produces an `OutcomeRecord` pairing what onboarding **predicted** with what
production **observed**. The Learning engine turns a batch of these into an explainable calibration.

## Predicted vs observed

| Predicted (onboarding, 7A) | Observed (operations, 7B) |
|---|---|
| confidence (0..1) | healthy after canary? (0/1) |
| band (auto / review) | rolled back? |
| sandbox passed? | duplicate rate |
| approval route (auto / human) | parse quality |

The gap between the two columns is the signal. If onboarding said 0.87 and the provider sailed
through canary, the model was well-calibrated there. If it said 0.70 and the provider rolled back,
the model was **over-confident** in that band.

## Confidence calibration (bucketed, no ML)

`learn(outcomes)` buckets predicted confidence into fixed ranges and, per bucket, computes:

- **predicted_mean** — average predicted confidence of providers in the bucket
- **observed_rate** — fraction that were actually healthy and not rolled back
- **delta = observed − predicted** — negative ⇒ over-confident, positive ⇒ under-confident

From the live demo:

```
conf [0.60,0.72)  n=1  predicted 0.70  observed 0.00  Δ −0.70   ← badly over-confident
conf [0.72,0.85)  n=2  predicted 0.78  observed 0.50  Δ −0.28
conf [0.85,1.01)  n=1  predicted 0.87  observed 1.00  Δ +0.13   ← slightly under-confident
calibration_error = 0.388   (count-weighted mean |Δ|; 0 = perfectly calibrated)
```

The **calibration error** is the count-weighted mean absolute delta — a single number for "how well
does our confidence predict production success?" Lower is better; 0 is perfect.

This is deliberately **arithmetic, not learning-in-the-ML-sense**: bucket, average, subtract. It is
fully explainable (every number traces to specific outcomes), deterministic (same outcomes → same
report), and needs no training data, no model, no gradients. The constraint — *never train ML, only
analytics* — is honored structurally.

## The calibration model

`learn()` also emits a `CalibrationModel`: a per-feed-type additive nudge (mean `observed −
predicted`, clamped to ±0.2) plus a global fallback. From the demo:

```
{rss: −0.20, ics: −0.20, jsonld_event: +0.18, search_result: −0.20}
```

Read: "in this sample, rss/ics/search sources were over-predicted — trust them a little less next
time; jsonld sources were under-predicted — trust them a little more." `apply_calibration(raw,
feed_type, model)` is a **pure** function that nudges a raw onboarding confidence by the learned
delta (clamped to 0..1) — the mechanism by which future onboarding *would* improve.

## The loop is open by design (for now)

7B **produces** the calibration model; it does **not** feed it back into 7A's confidence engine.
That would modify onboarding, which is out of scope. The seam is explicit: `OnboardingCalibrator`
(interface, `NotImplementedError`). Closing the loop — having onboarding consume the model so
future auto-approve/review decisions self-correct — is a deliberate, separately-approved step. Until
then, the calibration is a **report an operator reads** and applies by adjusting thresholds, not an
automatic rewrite of the confidence model.

This is the safety posture of the whole platform in miniature: the system *learns and recommends*,
but a human still turns the dial that changes behavior.

## Feedback signals (the operator's dashboard)

Alongside calibration, `collect_feedback` distills accuracy signals over all outcomes:

- **sandbox_accuracy** — of providers the onboarding sandbox passed, how many were actually healthy
- **confidence_accuracy** — `1 − mean|predicted − observed|`, an at-a-glance calibration score
- **approval_accuracy** — of approved promotions, how many survived (weren't rolled back)
- **duplicate_accuracy** — how often "predicted low-duplicate" held (observed ≤ 0.5)
- **provider_quality** — mean observed parse quality
- **stale_providers** / **manual_overrides** — operational hygiene signals

These answer "is the onboarding pipeline's *judgment* actually good?" — the question that decides
whether to raise the auto-approve band (more autonomy) or lower it (more human review).

## Why this matters for scale

At a handful of providers, calibration is noise. At thousands, it's the mechanism that keeps
autonomous growth honest: as real outcomes accumulate per feed type, the confidence model's blind
spots become measurable and correctable. A feed type that consistently over-promises gets its
confidence trimmed; one that reliably delivers earns more auto-approval. The fleet self-corrects
from evidence — deterministically, explainably, and always with the production key held by a human
until the calibration loop is explicitly closed.

## Limitations (honest)

1. **Small-sample volatility.** Deltas are clamped but not confidence-weighted by sample size; a few
   outcomes can swing a feed-type nudge. Real use needs volume + time-decay.
2. **Observed truth is the canary's truth.** "Healthy" means "passed a (mock) canary", not "served
   great events for a month." Longer-horizon quality (freshness, sustained uptime) isn't in the loop
   yet.
3. **The loop doesn't close itself.** By constraint, calibration informs but doesn't auto-apply.
4. **No causal attribution.** Calibration correlates predicted confidence with observed success by
   bucket/feed-type; it doesn't isolate *which* confidence factor (sandbox, tech, discovery…) was
   wrong. Factor-level calibration is future work.

---

**Status:** 7B closes the discover → onboard → operate → **learn** loop with explainable,
ML-free confidence calibration. The system measures how well it predicted reality and produces the
adjustment — a human (for now) chooses to apply it. Closing the loop automatically is a
separately-approved future step.
