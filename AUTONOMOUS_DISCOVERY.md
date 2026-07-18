# Autonomous Discovery — The Self-Improving Loop

EventScout discovers event sources (D1–D4), evaluates them into providers (7A), operates them in
production (7B), and learns from real performance to calibrate onboarding (7B learning). Phase 8A
closes the outermost loop: it feeds production reality **back into discovery itself**, so the system
learns *where to look next* and *how to look efficiently*. This document is the vision — what
"autonomous discovery" means here, and the guardrails that keep it safe.

Companion to **[DISCOVERY_OPTIMIZATION.md](DISCOVERY_OPTIMIZATION.md)** (the 8A build).

## The full loop

```
           ┌────────────────────────── 8A optimization (recommendations) ──────────────────────────┐
           │                                                                                       │
           ▼                                                                                       │
   Discovery (D1–D4) ──▶ Discovery Inbox ──▶ Onboarding (7A) ──▶ Production (7B) ──▶ real outcomes  │
        │  queries,          candidates          approve/reject      canary/health        │        │
        │  crawls, domains                                                                 │        │
        └───────────────────────────── historical DiscoveryRecords ◀──────────────────────┘        │
                                              │                                                     │
                                              ▼                                                     │
                     Coverage · Gaps · Query evolution · Domain trust · Budget · Strategy ──────────┘
                                    (which queries, which domains, where to expand)
```

Each earlier phase answered a local question. 8A answers the *global* one: **given everything we've
observed, how should discovery spend its next unit of effort?**

## What the system now knows about itself

By consuming discovery → onboarding → production outcomes, 8A can answer, from observed data alone:

- **Which queries earn their keep** — high-yield queries to boost, spam/zero-yield to retire,
  duplicates to merge.
- **Which domains deserve crawl budget** — trust-scored from approval, sandbox, production success,
  duplication, freshness, richness, stability.
- **Where coverage is thin** — cities with volume but missing technologies; whole dimensions
  (communities, universities) barely touched.
- **Which strategy fits each source** — never run AI on an RSS feed; use framework extraction on a
  SPA; keep searching where nothing has worked yet.
- **How efficient discovery is** — events per crawl, cost per discovery, discovery precision.

This is the difference between a crawler that runs a fixed playbook and a system that **watches its
own results and reallocates**.

## Bounded autonomy — recommend, don't act

The autonomy here is deliberately one step short of action. 8A produces a report; it changes
nothing. Three properties keep self-improvement from becoming self-modification:

1. **A hard action boundary.** The components that would *act* on the recommendations —
   `QueryApplier` (change the live query set), `BudgetEnforcer` (change crawl frequencies),
   `AdaptiveQueryGenerator` (invent new queries) — are unimplemented interfaces. 8A can propose
   retiring a query or stopping a domain; it cannot do it.
2. **Deterministic, explainable reasoning.** No LLM decides anything. Every recommendation traces to
   observed counts and weighted signals; an operator can always answer "why is this being
   recommended?" from the report alone.
3. **Observed-data-only.** The system never speculates about demand it hasn't seen. A gap is a *thin
   observed* area, not a guessed one; a query is scored on what it *produced*, not what it might.

The posture is the same one that has held across every phase: **the system learns and recommends; a
human turns the dial that changes behavior.**

## How the loop compounds

The value is in the feedback compounding over time:

- **Query evolution** trims the search set toward high-yield, keeping the expensive part of discovery
  lean as it scales.
- **Budget allocation** concentrates a fixed crawl budget on domains that have earned trust, and
  starves the dead weight — so more coverage per crawl.
- **Gap-driven expansion** points new queries at *observed* thin spots (a city rich in AI but empty
  of Rust), so growth is directed, not blind.
- **Strategy selection** stops wasteful re-discovery (running four strategies where one works),
  freeing budget for genuinely new sources.

Each turn of the loop makes the next discovery cycle cheaper and better-targeted — the definition of
a system that improves itself.

## Failure modes of self-optimization (and mitigations)

- **Optimizing into a rut** (only ever boosting what already works, never exploring) → gap analysis
  and coverage % explicitly push discovery toward *uncovered* areas, not just proven ones.
- **Acting on noise** → recommendations are observed-only and (in the honest self-review)
  small-sample-volatile; because nothing is applied automatically, a human filters before acting.
- **Curated-target blindness** → coverage is measured against hand-listed targets; "100% covered"
  means "of the known list," and the list is itself a maintained artifact.
- **Silent drift** → nothing is silent: coverage, gaps, query scores, trust, budget, and analytics
  are all in one inspectable report, persisted as history.

## The road ahead (gated)

8A is the last **recommend-only** phase. Phase 8B would let the system *act* on what it has learned:

- **Real search-engine integration** — run the boosted/created queries against a live engine
  (replacing D3's mock), under quota and rate control.
- **Adaptive query generation** — synthesize genuinely novel queries beyond the deterministic gap
  templates.
- **Budget enforcement** — push the crawl-budget plan into the real scheduler, changing crawl
  frequencies automatically.

Together these are autonomous web expansion — the system deciding *and executing* where to look
next. That is a materially larger grant of autonomy, and it stays gated until it earns trust,
because the whole design principle holds to the end: **EventScout improves itself without ever being
able to act on itself unsupervised.**

---

**Status:** With D1–D4 + 7A + 7B + 8A, EventScout observes the full lifecycle of its own discovery
and recommends how to make it better — deterministically, explainably, and entirely offline of
action. The loop is closed; the system proposes; a human disposes. **Autonomous action (Phase 8B) is
not started and requires explicit approval.**
