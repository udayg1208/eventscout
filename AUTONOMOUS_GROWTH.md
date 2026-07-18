# Autonomous Growth — How EventScout Grows Itself

EventScout began as a hand-curated set of ~7 providers. The Discovery Engine (D1–D4) and the
Onboarding Platform (7A) together turn it into a system that **finds and evaluates new event
sources on its own** — safely, explainably, and with a human in the loop where it matters. This
document is the strategy: what "autonomous growth" means here, how the pieces connect, and where
the guardrails are.

Companion to **[PROVIDER_ONBOARDING_PLATFORM.md](PROVIDER_ONBOARDING_PLATFORM.md)** (the 7A build)
and the discovery docs (DISCOVERY_ENGINE, FRAMEWORK_DISCOVERY, SEARCH_DISCOVERY_ENGINE,
AI_DISCOVERY_ENGINE).

## The growth loop

```
        ┌──────────────── discovery ────────────────┐        ┌──────── onboarding (7A) ────────┐
 seeds → D1 structured  ┐                            │        │  Confidence → Sandbox →          │
         D2 framework   ├→ candidate sources → Discovery Inbox → Review / Promotion → Monitoring  │
         D3 search      │    (status = NEW)          │        │        │                         │
         D4 AI prose    ┘                            │        │   APPROVED · REVIEW · REJECTED   │
                                                     │        └──────────────┬──────────────────┘
                                                     │                       │ staged PromotionPlan
                                                     └───────────────────────┼── monitoring feedback
                                                                             ▼
                                                                  [ Phase 7B: production ]  ← gated
```

Each layer answers a different question:

| Layer | Question | Output |
|---|---|---|
| D1 Structured | "Which known domains publish feeds/JSON-LD?" | candidate feeds |
| D2 Framework | "Which hide events in hydration payloads?" | candidate framework sources |
| D3 Search | "Which **new** domains exist that we never seeded?" | candidate URLs |
| D4 AI | "What does a prose page that has no structured data actually say?" | understood candidates |
| **7A Onboarding** | "Which candidates are worth becoming providers, and how?" | staged plans / review / rejections |
| 7B (future) | "Register the approved ones and run them." | live providers |

## Why growth is safe by construction

Autonomy here is **bounded autonomy**. Three structural properties keep self-growth from becoming
self-harm:

1. **A hard production boundary.** Everything from D1 through 7A stops at the Discovery Inbox or a
   *staged* PromotionPlan. The only component that could write to the registry/scheduler
   (`ProductionPromoter`) is an unimplemented interface. The system can propose, evaluate, and
   stage — it cannot deploy itself.
2. **Deterministic and explainable throughout.** No step uses an LLM to *decide* (D4's extractor is
   a mock; a real LLM only ever *extracts*, never *acts*). Every confidence score decomposes into
   weighted factors; every lifecycle transition is audited. A human can always answer "why did this
   source get here?" from the record alone.
3. **Human-in-the-loop where confidence is low.** High-confidence clean feeds auto-approve to a
   staged plan; everything ambiguous produces a review packet. The threshold is a dial: the more
   the operator trusts the pipeline, the more it automates — but the floor (production) is always
   human-gated.

## Promotion strategy

Growth is **coverage-per-effort**, not volume-at-any-cost:

- **Auto-approve the certain.** A source with a real feed (RSS/ICS/JSON-LD), strong tech + India
  relevance, and event evidence needs no human — it stages a plan and waits for 7B.
- **Review the ambiguous.** Framework, search-discovered, and AI-understood sources carry explicit
  risks ("crawl before ingesting", "verify AI extraction") and go to a person with a full packet.
- **Reject the unfit early.** Duplicates, blacklisted domains, and no-evidence pages are rejected
  before scoring — cheap, and they never clutter the review queue.
- **Match the provider to the evidence.** The PromotionPlan maps each discovery feed type to the
  right ingestion strategy (a feed → a feed parser; a hydration payload → field mapping; a search
  hit → "crawl first"), so promotion is a concrete blueprint, not a wish.

## Monitoring the loop

Self-growth without observability drifts. The platform tracks, per pipeline run: approval /
rejection / duplicate / sandbox-failure / promotion rates, average confidence and sandbox quality,
stale review items, and a false-positive estimate. Discovery **trends** (by feed type and by
discovery method — crawl vs search vs AI) show *where* growth is coming from. These metrics are the
feedback that lets an operator tune thresholds per source class: if search-discovered sources
review-approve at 90%, raise their auto band; if AI-extracted ones false-positive, lower it.

## Scaling the vision (toward 100,000 providers)

- **The bottleneck moves from discovery to judgment.** Discovery is cheap and parallel; the scaling
  question is "how many candidates can we *evaluate* safely?" Auto-approval answers it — the clean
  majority flows through untouched, the review queue stays bounded to genuine ambiguity.
- **Everything is set-membership and O(1)-per-candidate**, over the storage-agnostic layer that
  already scales from SQLite to Postgres with no app change. Partition by domain and add workers.
- **The human cost is a tunable, not a wall.** At 100k candidates, the operator doesn't review 100k
  — they review the fraction the confidence engine can't place, and they audit the monitoring
  dashboard, not individual sources.

## Failure modes of autonomy (and the mitigations)

- **Runaway low-quality growth** → auto-approval requires evidence + a passing sandbox; monitoring's
  false-positive estimate surfaces weak promotions before 7B ever runs them.
- **Same source, many faces** → duplicate detection collapses same-domain candidates (cross-domain
  entity resolution is acknowledged future work).
- **Confidence miscalibration** → weights/thresholds are explicit and per-run observable; a future
  feedback loop closes them against real provider performance.
- **Silent drift** → nothing is silent: audit log + monitoring + analytics make every decision and
  trend inspectable.

## The road ahead (gated)

7A is the last **pre-production** phase. What remains is deliberately behind approval:

- **7B — Production Promotion.** Implement `ProductionPromoter`: apply a plan, register the
  provider, add a scheduler entry, and drive `PROMOTED → MONITORING → ACTIVE`, monitoring the live
  provider and feeding real health back into confidence.
- **Calibrated confidence.** Replace reasoned weights with values learned from post-promotion
  outcomes (still explainable — learned weights, not a black box).
- **Cross-domain entity resolution.** Recognize one organizer across a blog, a Meetup page, and a
  conference site as a single source.
- **Real fetch-based sandbox.** Pull a live sample before promotion instead of assessing discovery
  evidence.

Each is a step further into autonomy — and each stays gated until it earns trust, because the whole
point of this design is that **EventScout grows itself without ever being able to hurt itself**.

---

**Status:** With D1–D4 + 7A, EventScout can discover new sources across the open web and evaluate
them into staged, explained, human-reviewable promotion plans — entirely offline of production.
The system proposes; a human (for now) disposes. **Production promotion (7B) is not started and
requires explicit approval.**
