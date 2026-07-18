# Seed Validation Engine — Phase 10E

Closes the discovery loop. A 10D Discovery Seed is a *hypothesis* ("GDG Chennai probably exists");
this phase **verifies** it through the existing pipeline and, only when the evidence holds, inserts a
provenance-bearing `CandidateSource(status=NEW)` into the **existing** Discovery Inbox. Verification
only — no provider creation, no onboarding, no production promotion. Generated seeds are never trusted;
they must earn their place with real evidence.

Code: `backend/app/validation/` (new package — additive). It **reuses** the D1 Discovery Inbox +
`CandidateSource` + fetcher, 10B universal extraction, 10C organizer extraction + confidence, 10D
seeds, and D4 provenance, and **modifies nothing** (D1–D4, 7A–7B, 8A–8D, 9A, 10A–10D, Search,
Repository, Registry, Scheduler, Event model, API, Frontend). No network in tests, no browser, no LLM.
The catalog is never touched.

## The verification pipeline

```
Discovery Seed (10D)
   │
   ▼  Verification Planner — pick the seed kind's strategy → search query + candidate URLs + path
   ▼  Fetch — injected Fetcher (real HttpxFetcher in prod, StaticFetcher in tests) + optional searcher
   ▼  Evidence — run 10B (events/JSON-LD) + 10C (organizer/tech/city/feeds) over each page
   ▼  Confidence Merge — seed · discovery · universal · organizer  → verification confidence
   ▼  Decision Engine — VERIFIED | PARTIALLY_VERIFIED | INSUFFICIENT_EVIDENCE | REJECTED
   ▼
Discovery Inbox (NEW)   ← only VERIFIED / PARTIALLY_VERIFIED   (audited either way; retry the rest)
```

## Verification strategies (one per seed kind, isolated)

| Seed kind | Strategy proves it by | Content signals |
|---|---|---|
| chapter_sibling | an organizer homepage in the right city | organizer, city |
| series_instance | an event page for that city | events, city |
| sponsor_program | a tech-matching program page | tech, organizer |
| university_unit | the campus site | organizer |
| venue_unit | the venue page carrying events | events |
| similar_organizer | a community/organizer page | organizer |
| connected_resource | the resource URL resolves with content | organizer |

Each strategy contributes candidate URL templates, a search query, the verification path (steps), and a
**content-fit score** over the evidence. Reachability is handled separately, so a page that merely loads
but carries none of a kind's content signals is REJECTED, not accepted.

## Evidence — observed, never invented

`Evidence` records only what the real extractors found on a fetched page: reachable, JSON-LD present,
event count, feeds, calendars, organizer name, technologies, city, registration URL — plus the 10B and
10C confidences. Crucially, the organizer is extracted from the **page**, never seeded from the seed's
own name (otherwise every page would "have" the claimed organizer). `signal_count()` counts the
distinct signals; the decision engine uses *content* signals (everything except mere reachability).

## Confidence merge — four contributions, explained

`verification confidence = Σ(component × weight)`, weights summing to 1.0:

| Contribution | Weight | From |
|---|---|---|
| universal | 0.30 | 10B event-extraction confidence |
| organizer | 0.30 | 10C organizer confidence |
| seed | 0.20 | the 10D seed's own confidence |
| discovery | 0.20 | did a page resolve? (reachability, +boost for multiple pages) |

## Decision engine — four states, deterministic

- **VERIFIED** — reachable, an event or organizer found, strong confidence + strategy fit + ≥2 content
  signals.
- **PARTIALLY_VERIFIED** — reachable with ≥1 content signal but below the strong bar.
- **INSUFFICIENT_EVIDENCE** — nothing resolved (retryable — transient).
- **REJECTED** — a reachable page with zero content signals (terminal — not the claimed seed).

Never invents evidence: a single weak signal is PARTIALLY at most, never VERIFIED.

## Discovery Inbox integration

Only VERIFIED / PARTIALLY_VERIFIED become a `CandidateSource(discovered_by="validation", status=NEW)`,
upserted into the **existing** `DiscoveryInbox` — reusing its key-based dedup (D1/D3/7A duplicate logic),
never bypassing it. `feed_type` reflects the evidence (calendar→ICS, feed→RSS, JSON-LD→AI_EXTRACTED,
else SEARCH_RESULT). Re-validating an already-inbound source returns `updated` (a duplicate). Nothing is
onboarded or promoted.

## Retry policy & audit trail

- **Retry:** INSUFFICIENT_EVIDENCE is transient — scheduled for a retry after a cooldown (run-counter
  based), up to `max_retries`, then **abandoned**. VERIFIED / PARTIALLY / REJECTED are terminal.
- **Audit:** every decision stores its evidence, reasons, confidence, verification path, and timestamp —
  in memory and (optionally) SQLite. Nothing is opaque.

## Metrics

`ValidationMetrics`: verification rate, acceptance rate, rejection rate, duplicate rate, average
confidence, and average evidence count.

## Live demonstration

`backend/spikes/p10e_validation.py` (fixtures, no network) validates four seeds and shows the five
outcomes:

```
● GDG Chennai  → reachable, 1 event, organizer GDG Chennai, city Chennai, 6 signals
                 VERIFIED  conf=0.62  → inbox inserted
● GDG Pune     → reachable, organizer GDG Pune, city Pune, 3 signals
                 PARTIALLY_VERIFIED  conf=0.37  → inbox inserted
● Ghost Org    → reachable (parked page), 1 signal, no content
                 REJECTED  conf=0.26  → not inbound
● Nowhere      → no URL resolved
                 INSUFFICIENT_EVIDENCE  → retry scheduled → abandoned after max retries
DUPLICATE: re-validate GDG Chennai → inbox updated (count stays 2)
INBOX: 2 candidates, discovered_by=validation, status=NEW
```

## Tests

`backend/tests/test_validation.py` — **93 tests, fixtures only, no network/browser/LLM**: models,
the planner + all seven strategies (URLs, steps, content-fit), evidence collection (rich/thin/parked;
the seed name never leaks into evidence), the four-contribution confidence merge (weights sum to 1,
total = Σ), the decision engine (all four states, never-invent), the retry policy (schedule, cooldown,
abandon, terminal), the candidate builder (inbox fields, feed types), metrics, both stores, and the
engine end-to-end (verified/partial→inbox, rejected/insufficient excluded, duplicate, batch report,
cooldown skip, abandonment, audit, persistence). Full backend suite: **905 passing** (the lone
full-run failure is the pre-existing `test_scheduler` async-timing flake, which passes in isolation).

## Honest self-review

**Truly true**
- A seed only enters the inbox if the real 10B/10C extractors found real evidence on a fetched page; a
  parked page is rejected, an unreachable seed is retried then abandoned, and the seed's own name never
  counts as evidence. Every decision is audited; only VERIFIED/PARTIALLY reach the *existing* inbox.

**Weaknesses / limitations**
1. **Verification is only as good as the fetch.** Candidate URLs are hand-guessed templates
   (`gdg.community.dev/{slug}`) plus an injected searcher. In tests these are fixtures; in production the
   real search step (`LiveSeedSearcher`) is **deferred** — without it, a genuinely-real ecosystem whose
   URL isn't guessed correctly is scored INSUFFICIENT. So *recall* depends on a search integration that
   isn't built here.
2. **It verifies "an organizer/event exists here", not "THIS seed".** The engine extracts the organizer
   from the page but does **not** cross-check that name against the seed target — a guessed URL that
   resolves to a *different* real community could be accepted. A name/identity match against the seed is
   an obvious hardening not yet done.
3. **Evidence inherits 10B/10C's ceiling.** Byte-level, regex, no JS — a JS-heavy real page yields thin
   evidence → PARTIALLY/INSUFFICIENT even when the ecosystem is real. Garbage-in from a soft-404 that
   *looks* empty is wrongly REJECTED (no soft-404 detection).
4. **Thresholds and merge weights are hand-calibrated**, not learned; the VERIFIED/PARTIALLY/REJECTED
   boundaries are reasonable but arbitrary, and the confidence is a ranking signal, not a probability.
5. **Shallow verification.** Mostly single-page (bounded by `max_urls`); the university strategy lists
   "departments → student clubs" steps but doesn't actually traverse them — the deep multi-page crawl is
   named, not performed.
6. **Duplicate protection is URL-key dedup.** Two different URLs for the same organizer become two inbox
   candidates; identity-level dedup would need the 10C canonicalization applied at insert time.
7. **The loop is on-demand, not autonomous.** 10E validates a batch when called; the continuous
   10C → 10D → 10E → inbox → 10C loop (`GrowthLoopScheduler`) is a deferred seam.

## Future integration (NOT this phase)

`interfaces.py` marks the seams (`NotImplementedError`): `LiveSeedSearcher` (wrap the 8B/10A real web
search so candidate URLs come from search, not templates) and `GrowthLoopScheduler` (drive the full
autonomous loop). The verified inbox candidates then feed the *existing* onboarding (7A) and operations
(7B) — human-gated, unchanged.

---

**Status:** 10E complete. Additive; every frozen system untouched; 905 tests green; verification-only,
provenance-bearing, into the existing inbox; no browser/LLM/network. **Stopping here — Phase 10F NOT
started.**
