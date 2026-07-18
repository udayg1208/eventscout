# Provider Onboarding Platform — Phase 7A

Everything **after** the Discovery Inbox. D1–D4 discover candidate sources and stop at the inbox
(`status=NEW`). Phase 7A is the platform that turns those candidates into promotion-ready providers
through a safe, explainable, mostly-automatic workflow — and then **stops before production**.

Every candidate comes to rest at exactly one of three verdicts:

- **APPROVED** — a `PromotionPlan` is staged (auto-approved, or human-approved from review).
- **REVIEW** — a `ReviewPacket` awaits a human.
- **REJECTED** — rejected / blacklisted / duplicate / failed-sandbox.

Nothing reaches production automatically. The engine never drives a candidate past `PROMOTED`;
turning a plan into a live registry/scheduler entry is Phase 7B, behind explicit approval.

Code: `backend/app/onboarding/` (new, self-contained). Additive — the catalog, search, ingestion
runner, scheduler, registry, providers, frontend, and API are **untouched**.

## Lifecycle

A deterministic state machine (`lifecycle.py`) — illegal transitions raise; every legal transition
returns an audited `AuditEntry`:

```
DISCOVERED → ANALYZED → SANDBOXED → SCORED ─┬─ AUTO_APPROVED → APPROVED → PROMOTED ┐
                                            ├─ MANUAL_REVIEW → APPROVED → PROMOTED ┘   (7A stops here)
                                            └─ REJECTED
   rejection paths at any gate: REJECTED · BLACKLISTED · DUPLICATE · FAILED_SANDBOX
   (PROMOTED → MONITORING → ACTIVE exist in the machine but are 7B; never auto-entered in 7A)
```

## Package

```
app/onboarding/
  models.py       OnboardingState (14), OnboardingCandidate, ConfidenceFactor, SandboxOutcome,
                  ReviewPacket, PromotionPlan, AuditEntry, Monitoring/Analytics dataclasses
  lifecycle.py    the deterministic transition table + transition() (audited, guarded)
  confidence.py   score_onboarding() — 8 explainable factors → auto/review/reject band
  review.py       build_review_packet() — the human review packet
  promotion.py    build_promotion_plan() — the staged blueprint (never applied)
  monitor.py      build_monitoring() — pipeline health metrics
  analytics.py    build_analytics() — reporting + discovery trends
  engine.py       OnboardingEngine — orchestrates the pipeline; deterministic sandbox
  interfaces.py   future seams: SandboxExecutor, ProductionPromoter (7B), ReviewNotifier
  store.py        OnboardingStore (ABC + InMemory + SQLite) — state + audit, no schema-break
```

## Safety philosophy

1. **Nothing reaches production automatically.** The hard boundary is `ProductionPromoter`
   (`interfaces.py`) — the only thing that would write to the registry/scheduler — and it raises
   `NotImplementedError`. 7A physically cannot promote to production.
2. **Everything is explainable.** The confidence total is *exactly* the sum of its eight factor
   contributions (score × weight, each with a human-readable detail) — no hidden magic numbers.
   Every state change is an audit entry (from → to, actor, reason).
3. **Deterministic.** No LLM, no randomness, no network — the same candidate always yields the same
   verdict, so the platform is reproducible and testable.
4. **Human-in-the-loop by default.** Only high-confidence candidates auto-approve to a *staged*
   plan; the medium band always produces a review packet for a person. Even auto-approval stops at
   a blueprint, not a live provider.
5. **Fail safe, not open.** Blacklist, duplicate, and no-evidence candidates are rejected before
   scoring; a source with no ingestible evidence fails the sandbox rather than being guessed in.

## Confidence Engine (8 explainable factors)

`score_onboarding(snapshot, sandbox)` → `OnboardingConfidence`. Weights sum to 1.0 (`WEIGHTS`, the
single source of truth):

| Factor | Weight | Meaning |
|---|---|---|
| discovery | 0.20 | D4 discovery_confidence, or a structured/tech proxy for D1–D3 |
| sandbox | 0.18 | dry-run evidence quality |
| extraction | 0.12 | how many key fields (title/city/country/org/tech/class) are present |
| provider_health | 0.10 | reliability proxy by feed type (a feed ≫ a search hit) |
| content | 0.12 | tech keywords + organizer + registration + event evidence |
| duplicate | 0.08 | inverse of duplication |
| tech | 0.12 | technology relevance |
| india | 0.08 | India relevance |

Bands (explicit thresholds): `≥ 0.72` → AUTO_APPROVE, `≥ 0.45` → REVIEW, else REJECT.

## Sandbox (deterministic dry-run)

7A's sandbox (`engine.simulate_sandbox`) validates a candidate against its **already-discovered
evidence** — no network, no provider instance (both forbidden here). It passes when there is
plausible ingestible signal (event evidence, structured data, or strong tech+India relevance) and
fails otherwise (`FAILED_SANDBOX`). A real fetch-based sandbox that pulls a live sample is the
`SandboxExecutor` seam, deferred (it needs network + reuse of the ingestion sandbox).

## Review Engine

`build_review_packet` produces everything a reviewer needs, nothing opaque: discovered URL,
confidence + reasons, extraction summary, sample-event evidence, sandbox report, detected
technologies, explicit **risks** (e.g. "AI-understood prose: verify before ingesting", "unproven:
discovered by search, crawl before ingesting", "weak India relevance"), and a recommendation.

## Promotion Engine

`build_promotion_plan` is a **blueprint only** — it never edits production. It maps the discovery
feed type to a provider type (rss→rss, ics→ics, jsonld→structured_html, next_data→framework_
hydration, ai_extracted→ai_assisted, search_result→crawl_pending, …) and fills in configuration,
refresh interval + retry policy (scaled by expected volume), declared capabilities, and a risk
assessment. Every plan carries the note *"PLAN ONLY — not applied to production."*

## Monitoring & analytics

`build_monitoring` tracks approval / rejection / duplicate / sandbox-failure / promotion rates,
average confidence and sandbox quality, **stale** review items (aged past a window), and a
conservative **false-positive estimate** (promoted despite weak confidence/quality).
`build_analytics` reports inbox size, review-queue depth, auto vs human approvals, rejections,
promotion candidates, average confidence, and **discovery trends** (by state / feed type /
discovery method).

## Live demonstration (deterministic, no network)

`spikes/p7a_onboarding.py` — 9 candidates spanning D1 feeds, D2 framework, D3 search, D4 AI, plus a
duplicate, a blacklisted domain, and no-evidence pages:

```
Inbox 9 → Confidence → Sandbox → Review/Promotion → Monitoring
  fossunited.org  [ics]          conf 0.74 → promoted
  reactindia.io   [jsonld_event] conf 0.82 → promoted
  community.dev   [jsonld_event] conf 0.71 → manual_review
  lu.ma           [next_data]    conf 0.66 → manual_review
  pydelhi.org     [ai_extracted] conf 0.63 → manual_review
  community.dev   [rss]          → duplicate  (same domain already onboarded)
  someblog.io / randomcorp.com   → failed_sandbox  (no ingestible evidence)
  spammy-events.net              → blacklisted

  promoted 2 · review 3 · rejected 4    → after human review (all 3 approved): promoted 5
  MONITORING approval_rate 0.56 · rejection_rate 0.44 · duplicate_rate 0.11 ·
             sandbox_failure_rate 0.22 · avg_confidence 0.71 · false_positive_estimate 1
  ✔ nothing promoted to production — everything rests at PROMOTED / REVIEW / REJECTED
```

Note the honest signals: the duplicate GDG domain is caught, no-evidence pages fail the sandbox,
and monitoring flags one human-approved-but-low-quality promotion (PyData-style, sandbox quality
0.32) as a potential false positive.

## Testing

`tests/test_onboarding.py` — **16 deterministic tests, no network**: lifecycle (legal/illegal/
terminal transitions, audited mutation), confidence (weights sum to 1, total = Σ contributions,
banding), sandbox pass/fail, review packet contents + risks, promotion plan (blueprint-only,
provider-type mapping, ai-requires-validation), full pipeline (auto-approve→promoted with full
audit trail, review→human decision both ways, blacklist/duplicate/failed-sandbox rejections,
ingest-from-inbox), the **never-reaches-production** invariant, monitoring (rates + staleness), and
SQLite state + audit persistence. Full backend suite: **455 tests**.

## Failure modes (and how they're handled)

- **Discovery false positives** → the sandbox + evidence-require gate reject no-signal pages;
  monitoring's false-positive estimate surfaces weak promotions for audit.
- **Duplicate domains** → detected before scoring (`DUPLICATE`), so one source isn't onboarded
  twice.
- **Malicious / spam domains** → the blacklist rejects them up front (`BLACKLISTED`).
- **Over-eager auto-approval** → even AUTO_APPROVED stops at a staged plan; production promotion is
  a separate, human-gated phase.
- **Stale review queue** → monitoring flags review items aged past a window.

## Scaling to 100,000 providers

- **The lifecycle is O(1) per candidate** — a fixed sequence of deterministic steps, no
  cross-candidate coordination, so throughput scales linearly with workers.
- **Storage is the existing storage-agnostic pattern** (SQLite now → Postgres later with zero app
  change); candidates and the append-only audit log are both index-friendly.
- **Auto-approval is the scaling lever** — at scale, the high-confidence band absorbs the bulk of
  clean feed sources without human touch, while the review queue stays bounded to genuinely
  ambiguous cases. Tuning the thresholds trades reviewer load against precision.
- **Monitoring closes the loop** — approval/false-positive rates per feed type let the platform
  raise or lower thresholds by source class as evidence accumulates.
- **Sharding by domain** is natural (the frontier/duplicate check is set membership); a real
  deployment partitions candidates across workers by registrable domain.

## Critical self-review

**Honestly true**
- Nothing can reach production — the only production-writing seam raises `NotImplementedError`.
- Confidence is genuinely transparent (total = Σ factor contributions, verified in a test) and
  every transition is audited.
- The pipeline correctly separates auto / review / reject and enforces duplicate/blacklist/sandbox
  gates before scoring.

**Weaknesses / what's deferred**
1. **The sandbox doesn't actually fetch.** It assesses *discovered evidence*, not a live sample —
   so a source whose discovery data looks good but whose real feed is broken would pass. The real
   fetch-based sandbox (`SandboxExecutor`, reusing Phase 3C) is deferred (needs network).
2. **Confidence weights and thresholds are reasoned, not calibrated.** 0.72/0.45 and the eight
   weights are sensible defaults, not tuned against labeled onboarding outcomes; there's no feedback
   loop yet from post-promotion provider performance back into the scores.
3. **Duplicate detection is domain-exact.** Two different domains for the *same* organizer (a blog
   and a Meetup page) aren't recognized as one source; entity resolution across domains is future
   work.
4. **`known_domains` is caller-supplied data, not a live registry read** (by constraint). It can go
   stale relative to the real provider set until 7B wires the two together.
5. **Persistence rehydration is partial.** The SQLite store round-trips state + audit + the JSON
   snapshot, but the typed confidence/sandbox/plan sub-objects are read back as data, not fully
   reconstructed — fine for audit/analytics, but a cross-process resume of the *engine* would
   re-derive them.
6. **`false_positive_estimate` is a proxy**, not a measured error rate — it flags weak promotions,
   but true false positives can only be known once providers run in production (7B + monitoring).

## Where Phase 7B begins (NOT this phase)

7A ends with staged `PromotionPlan`s. 7B implements `ProductionPromoter`: apply a plan — register
the provider, add a scheduler entry, drive `PROMOTED → MONITORING → ACTIVE` — and monitor the live
provider's health, feeding real performance back into confidence. That crosses into production and
requires explicit approval.

---

**Status:** 7A complete. Additive; frozen systems untouched; 455 tests green; deterministic,
explainable, human-in-the-loop, and provably pre-production. **Stopping here — automatic production
provider registration (7B) NOT started.**
