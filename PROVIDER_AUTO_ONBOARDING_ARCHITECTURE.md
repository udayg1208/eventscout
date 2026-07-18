# Provider Auto-Onboarding Platform (Phase 6C)

Architecture only — no code, no changes to existing modules. This designs the **bridge**
between the Discovery Engine (which finds candidate sources) and the Provider Registry (which
runs production providers): the control plane that decides whether a newly discovered source
should become a production provider.

> **Design stance:** this is mostly a *control plane* over components EventScout **already has**
> — the Provider **Sandbox** (3C), **State Store** (3B), **Scheduler** (3D), event **dedup**
> (Phase 2), **Entity Graph** + resolver (3F), and **enrichment** (5A). Auto-onboarding adds the
> *Inbox*, *Confidence Engine*, *Review Dashboard*, and *lifecycle/monitoring rules* around them.
> Reuse over rebuild; provider-agnostic throughout (it reasons about *signals + metadata*, never
> a source's identity — the same "no `if provider ==`" principle as the registry).

---

## 1. Candidate Source Model

Everything stored for one discovered source. Storage-agnostic entity (`CandidateSource`),
keyed by canonical domain+path so re-discovery updates rather than duplicates.

```
CandidateSource
  # identity
  id                    uuid
  url                   canonical entry URL
  domain                registrable domain (dedup key)
  # provenance (from Discovery Engine)
  discovery_method      seed-crawl | search-engine | link-graph | ai-extract | human
  discovered_from       parent source id / query / organizer that surfaced it
  discovery_confidence  0..1 (engine's initial guess)
  discovered_at         ts
  # organization (resolved via 3F Entity Graph)
  organization_name     str
  organization_entity_id link into the Entity Graph (or null)
  organization_type     community | company | university | conference-org | government | unknown
  # geography / relevance
  country               ISO (target: IN)
  city                  canonical (city.py)
  india_relevance       0..1
  # content signals
  detected_technologies [str]   (from 5A taxonomy over sampled events)
  detected_topics       [str]
  categories_seen       [EventCategory]
  # ingestion spec (from the Feed Detector)
  feed_types            [json-ld | rss | ics | sitemap | bevy | next-data | api | ai-extract]
  feed_urls             [url]        the concrete endpoints
  parser_type           adapter family to use (which generic provider)
  auth_required         bool         (hard-reject signal)
  robots_policy         allowed | disallowed | crawl-delay=N
  crawl_permissions     rate limit, allowed paths
  # scores (from Validation + Confidence)
  quality_score         0..1
  confidence_score      0..1
  tech_relevance        0..1
  professional_relevance 0..1
  spam_score            0..1
  duplicate_ratio       0..1   (fraction of sampled events already in catalog)
  # lifecycle
  status                DiscoveryInbox state (§2)
  status_reason         str
  provider_id           set once promoted → links to the registry plugin + State Store
  # audit
  created_at / updated_at / analyzed_at / validated_at / approved_at / promoted_at / last_checked_at
  version               int (bumped on any material change)
  history               [ {ts, from_status, to_status, actor(system|reviewer|monitor), reason, score_delta} ]
  last_validation_report ValidationReport (§3)
  last_sandbox_report    SandboxReport (§5)
```

Notes: `history` is an append-only audit log (who/what moved it and why). `version` + timestamps
support optimistic concurrency and "what changed" queries. Re-discovery merges into the existing
row (never a duplicate candidate).

## 2. Discovery Inbox (state machine)

A durable queue/store of `CandidateSource`s. Every discovery lands here first. Dedup on entry by
`domain` (re-discovery updates the row, boosts `discovery_confidence`, appends history).

**States:** `NEW → ANALYZING → {VALIDATED | REJECTED | HUMAN_REVIEW} → APPROVED → PRODUCTION`,
plus `DISABLED`, `ARCHIVED`.

| From | To | Trigger | Condition |
|---|---|---|---|
| — | NEW | Discovery Engine emits candidate | dedup: new domain |
| NEW | ANALYZING | Validation worker picks it up | queue capacity |
| ANALYZING | REJECTED | Validation | **hard gate** fails (robots-disallow, auth-required, no-HTTPS, anti-bot, 0 events, non-India, entertainment) |
| ANALYZING | VALIDATED | Validation | all hard gates pass |
| VALIDATED | APPROVED | Confidence Engine | `confidence ≥ AUTO` **and** sandbox clean |
| VALIDATED | HUMAN_REVIEW | Confidence Engine | `REVIEW ≤ confidence < AUTO` |
| VALIDATED | REJECTED | Confidence Engine | `confidence < REVIEW` |
| HUMAN_REVIEW | APPROVED / REJECTED | Reviewer | one-click decision |
| HUMAN_REVIEW | ANALYZING | Reviewer "Retry" | re-run validation/sandbox |
| APPROVED | PRODUCTION | Promotion pipeline (§7) | first sync succeeds + quality ok |
| PRODUCTION | DISABLED | Monitor (§8) / Reviewer | degradation rule fires |
| DISABLED | PRODUCTION | Monitor / Reviewer | recovery confirmed |
| DISABLED / REJECTED | ARCHIVED | Retention job (§9) | dead / superseded / expired |
| ARCHIVED | HUMAN_REVIEW | Re-discovery with new signal | appeal / changed source |

Invariants: only the **Promotion pipeline** writes to the Registry (never validation/AI directly);
`REJECTED`/`ARCHIVED` are retained (not deleted) so re-discovery dedups against them.

## 3. Automatic Validation Pipeline

Ordered stages; **hard gates fail-fast → REJECTED**; soft stages emit weighted signals. Every
stage outputs a structured `Signal{name, passed, score∈0..1, weight, evidence}`; the collection
is a `ValidationReport`.

| # | Stage | Type | Emits |
|---|---|---|---|
| 1 | HTTPS + valid cert | hard gate | pass/fail |
| 2 | robots.txt allows our UA + path | hard gate | policy + crawl-delay |
| 3 | Auth / anti-bot detection (401/403/challenge) | hard gate | reject if present (never bypass) |
| 4 | Response stability (N fetches, consistent, < timeout) | soft | uptime signal |
| 5 | Feed detection (JSON-LD Event / ICS / RSS / sitemap / next-data) | hard-ish | ≥1 ingestion method, else → ai-extract candidate or reject |
| 6 | Event detection + **density** (events/page) | soft | count + density |
| 7 | Recurring activity (multiple events / historical dates) | soft | "alive" signal |
| 8 | Tech relevance (5A classify: professional-tech vs entertainment/edtech) | hard gate | reject if entertainment |
| 9 | India relevance (geo signals: city, TLD, chapter country) | hard gate | reject if non-India |
| 10 | Professional relevance (not personal blog / product marketing / spam) | soft | score |
| 11 | Duplicate detection (sample events vs catalog via Phase-2 dedup; org vs 3F resolver) | soft | duplicate_ratio |
| 12 | Spam/quality heuristics (title entropy, link farm, boilerplate) | soft | spam_score |
| 13 | Organization detection (resolve → Entity Graph) | soft | org entity + type |

Reuses: the **5A classifier/taxonomy** (stages 8, 6-tech), **Phase-2 dedup** + **3F resolver**
(stage 11/13), **city.py** (stage 9). Network stages honor the crawl budget (§13).

## 4. Confidence Engine

**Deterministic**, explainable score (same philosophy as the frozen Ranking/Trending engines —
weighted sum of signals, reproducible, no black box). Input = ValidationReport + provenance +
history.

```
confidence = Σ wᵢ · signalᵢ , clamped 0..1
```

| Factor | Weight (illustrative) | Source |
|---|---|---|
| structured_data (JSON-LD/ICS/RSS present) | 0.25 | stage 5 |
| event_density | 0.15 | stage 6 |
| recurring_updates | 0.15 | stage 7 |
| trusted_domain (allowlist: *.community.dev, lu.ma, known orgs, .edu.in) | 0.10 | provenance |
| historical_uptime (if re-discovered / previously seen) | 0.10 | monitoring |
| manual_approvals (prior human approvals of similar/clustered sources) | 0.10 | review feedback |
| community_reputation (inbound links from trusted sources; entity-graph centrality) | 0.10 | link-graph/3F |
| duplicate_ratio | −0.15 (penalty) | stage 11 |
| spam_score | −0.15 (penalty) | stage 12 |

**Bands:** `confidence ≥ AUTO (e.g. 0.85)` → **auto-approve**; `REVIEW (0.55) ≤ c < AUTO` →
**human review**; `c < REVIEW` → **reject**. Thresholds are config (tunable per family + tightened
if false-approval rate rises). Output includes a **per-factor breakdown** so a reviewer sees
*why*. Determinism = auditable, testable, and safe to gate promotion on.

## 5. Sandbox Execution (reuses the 3C Provider Sandbox)

Generalizes the existing `run_sandbox` (which is already structurally unable to touch production
— no repo argument). Given a `CandidateSource` + parser spec, instantiate a throwaway adapter and
run the **full pipeline in isolation**:

```
Fetch (rate-limited, time-boxed, resource-capped)
  → Validate (schema/required fields)
  → Normalize (city.py, dates)
  → Classify (5A category)
  → Deduplicate (self + vs a READ-ONLY snapshot of the catalog)
  → Preview
```

Produces a `SandboxReport`: `fetched, valid, invalid, duplicates, sample_events[], validation_errors,
missing_field_sparsity, quality_score, est_concurrent_yield, est_90day_yield, est_refresh_cadence,
est_maintenance_risk` — **without a single production write**. Hard limits: max pages, max time,
max bytes, network egress allow-listed to the candidate domain (SSRF guard, §13). The sandbox is
the *evidence* the Confidence Engine and reviewer act on.

## 6. Human Review Dashboard

The workflow for the `HUMAN_REVIEW` queue (and spot-audits of auto-approvals). Per candidate the
reviewer sees, all from the sandbox + reports:

- **Preview events** (rendered sample) · **quality report** (per-signal from §3) · **duplicates**
  (which catalog events/organizers overlap, with %) · **confidence + breakdown** (§4) · **detected
  parser/feed type** · **validation failures** · **auto-recommendation** (templated: *"Approve —
  0.88, clean JSON-LD, 12 events, 0 dups, org=PyData Chennai"* / *"Reject — 82% duplicate of
  gdg"*).
- **One-click:** Approve · Reject · **Pause** (re-queue for later) · **Retry** (re-run
  validation/sandbox).
- **Bulk / cluster actions:** the engine groups re-discovered siblings ("40 GDG On Campus
  chapters", "12 PyData chapters") → one decision approves the pattern and **auto-approves future
  members of the cluster** (the biggest reviewer-throughput lever).
- **Feedback:** every decision writes to `history` and feeds the `manual_approvals` /
  `community_reputation` factors (§4) and future AI (§11). Full audit trail.

## 7. Promotion Pipeline (APPROVED → PRODUCTION)

Each stage reuses an existing subsystem; failure at any stage **rolls back** to `HUMAN_REVIEW`/`DISABLED`.

```
Sandbox (final confirmation run)
  → Registry   : write the provider config ROW (type,url,cadence,metadata) — the auto-populated
                 registry from the Discovery-Engine design (data, not code)
  → Scheduler  : register with the metadata-driven Scheduler (3D) — refresh/priority from metadata
  → State Store: create the ProviderState row (3B) — health, circuit, retry policy
  → First Sync : CANARY ingestion — bounded scope, results flagged "provisional", watched
  → Monitoring : attach the health/quality monitors (§8), capture a baseline
  → Health Tracking: after K successful syncs + quality gate, clear "provisional"
  → Production : status=PRODUCTION, full cadence
```

Canary discipline: the first sync writes to the catalog but tagged provisional; if it yields junk
or fails, auto-demote before it can pollute at scale. Promotion never bypasses the Sandbox +
Confidence gate.

## 8. Continuous Monitoring + automatic degradation

Post-production, per provider (built on the 3B State Store + 3D scheduler metrics + catalog signals):

| Signal | Source | Degradation rule |
|---|---|---|
| yield (events/sync, trend) | ingestion reports | 0 for K syncs → **PAUSE** + alert |
| duplicate_ratio (vs catalog) | dedup | > D for K syncs → **DISABLE** (redundant source) |
| error_rate / circuit | State Store (3B) | circuit opens repeatedly → **DISABLE** (already native) |
| uptime | State Store | sustained failures → DISABLE |
| structure_change (parse-failure spike) | ingestion | → **PAUSE** + flag for re-sandbox / AI re-parse suggestion (§11) |
| quality drop / spam rise | enrichment (5A) + spam heuristics | → **HUMAN_REVIEW** |

Degradation is **graded**: `warn → pause → disable → archive`, so a transient blip doesn't retire a
good source, and a genuinely dead one is removed automatically. Reuses the existing circuit breaker
+ health rollups — the platform adds *policy*, not new machinery.

## 9. Retirement

| State | When | Reversible? | Retention |
|---|---|---|---|
| **PAUSED** | structure change / under investigation / transient | yes (auto-retry) | full |
| **DISABLED** | repeated failures, circuit open, low yield, high dup | yes (on recovery) | full |
| **ARCHIVED** | dead domain (404 for N days), permanently 0-yield, superseded by a better source, reviewer retire | rarely (re-discovery can appeal) | kept M months for dedup + audit |
| **REMOVED** (hard delete) | spam/malicious/legal only | no | none |

Everything except spam/legal is **archived, not deleted** — provenance + history are preserved so
re-discovery dedups and the audit trail survives.

## 10. Platform metrics

| Metric | Meaning / why |
|---|---|
| candidate_sources / day | discovery throughput |
| approval_rate | % of candidates that reach PRODUCTION |
| **false_positive_rate** | approved → later degraded/archived (the key **precision** metric) |
| false_negative signals | rejected → later re-approved (recall leak) |
| **manual_review %** | fraction needing a human (automation health — drive it down) |
| time-to-production | discovery → PRODUCTION latency |
| active / disabled / archived providers | fleet composition |
| provider_lifetime | avg PRODUCTION → ARCHIVED |
| events / provider (distribution) | yield concentration (few big, long tail) |
| provider_quality (avg) | catalog health |
| reviewer throughput | ops capacity |
| catalog dup-rate trend | regression detector |

These answer the two questions that matter: *is automation healthy* (manual_review% ↓, approval
latency ↓) and *is precision holding* (false_positive_rate ↓, catalog dup-rate flat).

## 11. Where AI assists later (never publishes)

| AI job | Assists with | Always gated by |
|---|---|---|
| parser_suggestion | propose extraction for unstructured pages | sandbox must confirm it produces valid events |
| quality/yield estimation | prioritize the inbox before sandboxing | deterministic validation still runs |
| website_understanding | org type, ecosystem, metadata | Entity resolver + human on low confidence |
| duplicate_prediction | semantic dedup beyond strings | Phase-2 dedup remains authoritative |
| maintenance_prediction | fragility scoring (which will break) | monitoring is ground truth |
| reviewer assist | draft recommendation / summary | reviewer decides |

**Hard rule (non-negotiable):** AI output is a **suggestion**. A source reaches PRODUCTION **only**
via (deterministic confidence ≥ AUTO + clean sandbox) **or** an explicit human approval. **AI never
moves a source to PRODUCTION.** This keeps hallucination out of the catalog and preserves the
"grounding over trust" principle from the Discovery Engine design.

## 12. Final architecture

```
        Discovery Engine  (seeds · search · link-graph · AI-extract)
              │  candidate source
              ▼
        ┌── DISCOVERY INBOX ──┐  (dedup on entry; state machine §2; durable)
        │        │            │
        │        ▼            │
        │  VALIDATION PIPELINE│  (§3 — hard gates + weighted signals; reuses 5A/dedup/3F/city)
        │        │            │
        │        ▼            │
        │  CONFIDENCE ENGINE  │  (§4 — deterministic score → auto | review | reject)
        │        │            │
        │        ▼            │
        │     SANDBOX ────────┼─ read-only catalog snapshot (§5 — reuses 3C sandbox; no prod write)
        │      │      │       │
        │  auto│      │review │
        │      │      ▼       │
        │      │  HUMAN REVIEW │  (§6 — preview/quality/dups/confidence; 1-click; cluster-approve)
        │      │      │       │
        └──────┼──────┼───────┘
               ▼      ▼   (APPROVED)
        PROMOTION PIPELINE  (§7 — Registry → Scheduler(3D) → State Store(3B) → canary First Sync)
               │
               ▼
        PROVIDER REGISTRY  (auto-populated: rows, not code)
               ▼
        SCHEDULER (3D) → INGESTION → normalize → dedup → AI enrich (5A) → CATALOG → SEARCH → USERS
               ▲                                                           │
               └────────── CONTINUOUS MONITORING (§8) ◀────────────────────┘
                           (yield/dups/errors/uptime/quality/structure → degrade/pause/disable/archive)
                                        │
                                        └── feedback → Inbox scores + AI training
```

## 13. Critical review (challenging the design)

**Failure modes**
- *Auto-approval cascade:* a batch of well-structured but low-value sources auto-approve and bloat
  the catalog. Mitigation: conservative `AUTO` threshold, canary first-sync, spot-audit of
  auto-approvals, catalog dup-rate regression alarm.
- *Sandbox ≠ production:* a source behaves differently at full scale/over time (rate-limits,
  pagination, seasonality). Mitigation: provisional canary period + monitoring before "trusted."
- *Backlog:* discovery outruns validation/review. Mitigation: priority queue by confidence×yield;
  cluster-approve; shed low-confidence candidates.

**False approvals** — the dangerous case: a **spam/entertainment source with clean JSON-LD** passes
structure gates. Structure ≠ quality. Mitigation: the **tech/professional-relevance classifier is a
hard gate** (not just a score), plus human spot-audits and the false_positive_rate metric driving
threshold tightening. Also *duplicate sources dedup can't catch* (same events, syndicated under
different URLs) → org-level dedup via the entity resolver + yield-overlap monitoring.

**False rejections** — a legitimate source with no structured data where AI-extract fails, or an
over-strict robots parse. Cost: lost coverage (silent). Mitigation: periodic re-evaluation of
ARCHIVED/REJECTED, an appeal path, and logging rejections with reasons so recall leaks are visible.

**Maintenance costs** — thresholds, classifiers, and parser families need tuning; reviewers cost
time even at <10%; structure drift needs re-sandbox. The platform **trades linear per-provider
engineering for a standing precision/ops function** — lower total, but never zero.

**Security risks** (the real ones, because we fetch untrusted domains):
- *SSRF / malicious redirects* → sandbox egress **allow-listed to the candidate domain**, no
  internal-network access, no following to private IPs.
- *Resource exhaustion / zip-bombs / infinite pagination* → hard caps (bytes/time/pages) in fetch.
- *Poisoned JSON-LD/ICS* (script injection → stored XSS in the UI) → the frozen normalization must
  sanitize/escape; treat all fetched fields as hostile text.
- *No code execution* from fetched content — parsers are data-only (no eval of remote JS).

**Scalability** — millions of candidate URLs: the frontier + inbox shard by domain; validation is
**network-bound** (polite crawl budget + search/LLM quota is the real ceiling, not CPU); dedup
must be index-backed at scale. The bottleneck is *politeness budget*, by design.

**Operational bottlenecks** — **human review is the throughput cap**; the whole platform's value
is keeping auto-approve precision high enough that review stays <10%. The **confidence thresholds**
are the single most important knob; mis-set, they either flood reviewers (too low) or pollute the
catalog (too high).

## 14. Five-year vision (10k+ candidates · 2k+ providers · millions of pages)

- **The structured majority auto-flows:** most discovered sources have JSON-LD/ICS/RSS → high
  confidence → auto-approve + canary. Humans touch only the ambiguous ~5–15%.
- **Cluster-once, approve-many:** re-discovered siblings (GDG chapters, IEEE branches, PyData
  chapters) are grouped; one pattern approval auto-onboards all current + future members — this is
  what makes 2,000+ providers manageable by a small team.
- **Self-healing fleet:** monitoring auto-pauses/disables/archives dead or degraded providers, so
  the *active* set stays clean without manual gardening; provider_lifetime + false_positive_rate
  are watched, not individual providers.
- **Compounding precision:** the manual-approval feedback loop + AI assist raise auto-approve
  accuracy over time, pushing manual_review% down as the catalog grows.
- **Engineers change jobs:** from *"onboard each provider"* to *"tune policy, handle edge cases,
  own precision + security."* Millions of crawled pages are handled by the frontier/validation
  workers within the politeness/quota budget; engineers never see most of them.

**Honest bottom line:** this platform makes continuous growth *operationally sustainable* — 2,000+
providers auto-managed, ~10k candidates in flight, human touch on a small minority. It does **not**
make growth free: the permanent cost centers are **precision/quality control** (validators,
classifiers, dedup, review) and **modest API spend** (search + LLM). It correctly relocates the
constraint from *engineering labor* (which doesn't scale) to *standing ops + quality* (which does).
The system finally *grows its own catalog* — with humans as auditors of a mostly-automatic machine,
not as the machine.
